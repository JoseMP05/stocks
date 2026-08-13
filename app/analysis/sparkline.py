"""Server-side sparkline geometry for `AnalysisResult.price_series`.

No JavaScript and no charting library: the path data is computed here and the
template emits a plain `<svg>`. The SVG itself is decorative (`aria-hidden`),
so this module also produces a sampled text table that the template renders
visually hidden — that table, not the drawing, is what a screen reader gets.

Bollinger bands, SMA20/SMA50 and a volume lane are optional add-ons: every
extra kwarg to `build_sparkline()` defaults to `None`, and with nothing
passed the output is byte-identical to the close-only sparkline this module
used to draw. That matters for old cached runs, whose `AnalysisResult` has
those series as empty lists.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

# Fixed drawing box. The SVG keeps its default `preserveAspectRatio`, so CSS
# scales it uniformly via `aspect-ratio`; stretching it with
# `preserveAspectRatio="none"` would squash the endpoint dot and the cost label.
PLOT_WIDTH = 300.0  # the line/bands/SMAs/volume all scale their x to this
AXIS_WIDTH = 38.0  # blank gutter to the right of the plot, for axis labels —
# only added to view_width when there's a band or SMA value to print there,
# same "grow only when needed" rule the volume lane already follows below.
PRICE_HEIGHT = 76.0  # price + bands + SMAs lane
LANE_GAP = 6.0
VOLUME_HEIGHT = 28.0  # own 0-based scale, drawn only when volume data exists
VIEW_HEIGHT_WITH_VOLUME = PRICE_HEIGHT + LANE_GAP + VOLUME_HEIGHT  # 110.0
AXIS_LABEL_GAP = 7.0  # minimum vertical spacing between stacked axis labels

# Rows kept in the visually-hidden equivalent table.
TABLE_POINTS = 12


@dataclass(frozen=True)
class SparkRow:
    """One row of the text equivalent: a position in the series and its close."""

    index: int
    value: float
    bb_upper: float | None = None
    bb_lower: float | None = None
    volume: float | None = None


@dataclass(frozen=True)
class PriceLabel:
    """A Y-axis readout pinned to a series' last known value, e.g. where the
    Bollinger upper band or SMA20 currently sits."""

    y: float
    value: float


@dataclass(frozen=True)
class VolumeBar:
    """One bar in the volume lane, in the sparkline's own coordinate space."""

    x: float
    y: float
    width: float
    height: float


@dataclass(frozen=True)
class Sparkline:
    line_path: str
    area_path: str
    end_x: float
    end_y: float
    # Total viewBox width: PLOT_WIDTH alone, or with the axis gutter added.
    view_width: float = PLOT_WIDTH
    # Total viewBox height: PRICE_HEIGHT alone, or with the volume lane added.
    view_height: float = PRICE_HEIGHT
    # Where the plotted line/bands/volume end and the axis gutter begins —
    # the cost line and the axis labels both anchor off this, not view_width,
    # so neither ever draws inside the gutter (or drifts if it's absent).
    plot_width: float = PLOT_WIDTH
    # y of the dashed average-cost rule, only when a position exists.
    cost_y: float | None = None
    cost_value: float | None = None
    # Plotted domain (padded, and widened to include avg_cost and any bands).
    domain_low: float = 0.0
    domain_high: float = 0.0
    # Real series statistics, for the caption and the text table.
    low: float = 0.0
    high: float = 0.0
    last: float = 0.0
    point_count: int = 0
    rows: list[SparkRow] = field(default_factory=list)
    # Optional layers. The `has_*` flags gate both the SVG paint and the CSS
    # `:has()` toggles, so a layer with no usable data never renders an empty
    # (but still hit-testable/legend-entried) element.
    band_path: str = ""
    sma20_path: str = ""
    sma50_path: str = ""
    volume_bars: list[VolumeBar] = field(default_factory=list)
    has_bands: bool = False
    has_smas: bool = False
    has_volume: bool = False
    # Y-axis readouts for each layer's last known value, or None once the
    # layer has no data at all (never drawn) — not to be confused with a
    # layer that's merely toggled off, which is a pure CSS concern.
    bb_upper_label: PriceLabel | None = None
    bb_lower_label: PriceLabel | None = None
    sma20_label: PriceLabel | None = None
    sma50_label: PriceLabel | None = None


def _fmt(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _aligned(series: list[float | None] | None, n: int) -> list[float | None] | None:
    """Accept a companion series only when it lines up 1:1 with the price grid.

    A run predating these fields caches an empty list; a mismatched length
    would otherwise misalign every point. Either case degrades silently to
    "layer not drawn" rather than raising.
    """
    if not series or len(series) != n:
        return None
    return series


def _segmented_line(xs: list[float], ys: list[float | None]) -> str:
    """One or more `M .. L ..` fragments, breaking wherever the series is `None`.

    A single blind path (treating `None` as 0) would plunge an SMA to the
    bottom of the frame during its warm-up period instead of simply not
    being drawn yet.
    """
    parts: list[str] = []
    current: list[str] = []
    for x, y in zip(xs, ys):
        if y is None:
            if len(current) >= 2:
                parts.append("M " + " L ".join(current))
            current = []
            continue
        current.append(f"{_fmt(x)} {_fmt(y)}")
    if len(current) >= 2:
        parts.append("M " + " L ".join(current))
    return " ".join(parts)


def _segmented_band(
    xs: list[float], uppers: list[float | None], lowers: list[float | None]
) -> str:
    """Closed fill polygon(s): upper bound left-to-right, lower bound back.

    Split into one polygon per contiguous run where both bounds are known,
    same reasoning as `_segmented_line`.
    """
    parts: list[str] = []
    run: list[int] = []

    def flush() -> None:
        if len(run) < 2:
            return
        top = " L ".join(f"{_fmt(xs[i])} {_fmt(uppers[i])}" for i in run)
        bottom = " L ".join(f"{_fmt(xs[i])} {_fmt(lowers[i])}" for i in reversed(run))
        parts.append(f"M {top} L {bottom} Z")

    for i, (u, l) in enumerate(zip(uppers, lowers)):
        if u is None or l is None:
            flush()
            run.clear()
        else:
            run.append(i)
    flush()
    return " ".join(parts)


def _last_label(
    values: list[float | None] | None, y_of: Callable[[float], float]
) -> PriceLabel | None:
    """The Y-axis readout for a series: its most recent non-`None` value.

    Warm-up `None`s sit at the *start* of these series, never the end, but
    scanning from the back rather than assuming `values[-1]` keeps this safe
    even if that ever changes.
    """
    if not values:
        return None
    for v in reversed(values):
        if v is not None:
            return PriceLabel(y=round(y_of(v), 2), value=v)
    return None


def _declutter(labels: dict[str, PriceLabel]) -> dict[str, PriceLabel]:
    """Nudge vertically stacked axis labels apart so converging values (e.g.
    SMA20 and SMA50 crossing) print legibly instead of on top of each other.

    Cascades downward in ascending-y order (top of the price lane first) —
    simple and enough for at most 4 labels, not a general layout solver.
    """
    ordered = sorted(labels.items(), key=lambda kv: kv[1].y)
    result: dict[str, PriceLabel] = {}
    floor: float | None = None
    for key, label in ordered:
        y = label.y if floor is None else max(label.y, floor)
        result[key] = PriceLabel(y=round(y, 2), value=label.value)
        floor = y + AXIS_LABEL_GAP
    return result


def _sample(
    values: list[float],
    wanted: int,
    bb_upper: list[float | None] | None,
    bb_lower: list[float | None] | None,
    volume: list[float | None] | None,
) -> list[SparkRow]:
    """Take roughly `wanted` evenly spaced points, always keeping the ends."""
    total = len(values)
    if total <= wanted:
        idxs = list(range(total))
    else:
        step = (total - 1) / (wanted - 1)
        seen: list[int] = []
        for i in range(wanted):
            idx = round(i * step)
            if idx not in seen:
                seen.append(idx)
        idxs = seen

    def at(series: list[float | None] | None, i: int) -> float | None:
        return series[i] if series is not None else None

    return [
        SparkRow(
            index=i + 1,
            value=values[i],
            bb_upper=at(bb_upper, i),
            bb_lower=at(bb_lower, i),
            volume=at(volume, i),
        )
        for i in idxs
    ]


def build_sparkline(
    values: list[float],
    avg_cost: float | None = None,
    bb_upper: list[float | None] | None = None,
    bb_lower: list[float | None] | None = None,
    sma20: list[float | None] | None = None,
    sma50: list[float | None] | None = None,
    volume: list[float | None] | None = None,
) -> Sparkline | None:
    """Build the sparkline geometry, or None when there is nothing to draw."""
    series = [float(v) for v in values if v is not None]
    if len(series) < 2:
        return None

    n = len(series)
    bb_upper = _aligned(bb_upper, n)
    bb_lower = _aligned(bb_lower, n)
    sma20 = _aligned(sma20, n)
    sma50 = _aligned(sma50, n)
    volume = _aligned(volume, n)

    has_bands = bb_upper is not None and bb_lower is not None
    has_smas = sma20 is not None or sma50 is not None
    has_volume = volume is not None and any(v for v in volume if v)

    low, high = min(series), max(series)
    # The cost line and the bands both have to stay inside the frame, so
    # both widen the domain.
    domain_low, domain_high = low, high
    if avg_cost is not None:
        domain_low = min(domain_low, avg_cost)
        domain_high = max(domain_high, avg_cost)
    if has_bands:
        band_values = [v for v in (*bb_upper, *bb_lower) if v is not None]
        if band_values:
            domain_low = min(domain_low, min(band_values))
            domain_high = max(domain_high, max(band_values))

    pad = (domain_high - domain_low) * 0.12 or max(abs(domain_high) * 0.02, 1.0)
    domain_low -= pad
    domain_high += pad
    span = domain_high - domain_low

    def y_of(value: float) -> float:
        return PRICE_HEIGHT - (value - domain_low) / span * PRICE_HEIGHT

    last_index = n - 1
    xs = [i / last_index * PLOT_WIDTH for i in range(n)]
    points = [(x, y_of(v)) for x, v in zip(xs, series)]
    line = "M " + " L ".join(f"{_fmt(x)} {_fmt(y)}" for x, y in points)
    area = f"{line} L {_fmt(PLOT_WIDTH)} {_fmt(PRICE_HEIGHT)} L 0 {_fmt(PRICE_HEIGHT)} Z"
    end_x, end_y = points[-1]

    band_path = ""
    if has_bands:
        upper_y = [y_of(v) if v is not None else None for v in bb_upper]
        lower_y = [y_of(v) if v is not None else None for v in bb_lower]
        band_path = _segmented_band(xs, upper_y, lower_y)

    sma20_path = ""
    if sma20 is not None:
        sma20_y = [y_of(v) if v is not None else None for v in sma20]
        sma20_path = _segmented_line(xs, sma20_y)

    sma50_path = ""
    if sma50 is not None:
        sma50_y = [y_of(v) if v is not None else None for v in sma50]
        sma50_path = _segmented_line(xs, sma50_y)

    raw_labels: dict[str, PriceLabel] = {}
    if has_bands:
        upper_label = _last_label(bb_upper, y_of)
        lower_label = _last_label(bb_lower, y_of)
        if upper_label is not None:
            raw_labels["bb_upper"] = upper_label
        if lower_label is not None:
            raw_labels["bb_lower"] = lower_label
    if (label := _last_label(sma20, y_of)) is not None:
        raw_labels["sma20"] = label
    if (label := _last_label(sma50, y_of)) is not None:
        raw_labels["sma50"] = label
    labels = _declutter(raw_labels)
    bb_upper_label = labels.get("bb_upper")
    bb_lower_label = labels.get("bb_lower")
    sma20_label = labels.get("sma20")
    sma50_label = labels.get("sma50")
    # The axis gutter only earns its keep when there's something to print in
    # it — an old cached run with none of these series stays exactly as
    # narrow as the close-only sparkline it used to be.
    view_width = PLOT_WIDTH + AXIS_WIDTH if raw_labels else PLOT_WIDTH

    volume_bars: list[VolumeBar] = []
    # Keep the price lane at its usual height when there is no volume data —
    # only cached runs from before this feature hit this path, and there is
    # no data to fill a taller frame with, so it stays 76 rather than 110
    # with a blank lower third.
    view_height = VIEW_HEIGHT_WITH_VOLUME if has_volume else PRICE_HEIGHT
    if has_volume:
        clean_volumes = [v for v in volume if v is not None and v > 0]
        max_volume = max(clean_volumes) if clean_volumes else 0.0
        bar_width = PLOT_WIDTH / n
        lane_top = PRICE_HEIGHT + LANE_GAP
        for i, v in enumerate(volume):
            if not v or not max_volume:
                continue
            h = v / max_volume * VOLUME_HEIGHT
            volume_bars.append(
                VolumeBar(
                    x=round(i * bar_width, 2),
                    y=round(lane_top + VOLUME_HEIGHT - h, 2),
                    width=round(max(bar_width - 0.6, 0.4), 2),
                    height=round(h, 2),
                )
            )

    return Sparkline(
        line_path=line,
        area_path=area,
        end_x=round(end_x, 2),
        end_y=round(end_y, 2),
        view_width=view_width,
        view_height=view_height,
        plot_width=PLOT_WIDTH,
        cost_y=round(y_of(avg_cost), 2) if avg_cost is not None else None,
        cost_value=avg_cost,
        domain_low=domain_low,
        domain_high=domain_high,
        low=low,
        high=high,
        last=series[-1],
        point_count=n,
        rows=_sample(series, TABLE_POINTS, bb_upper, bb_lower, volume),
        band_path=band_path,
        sma20_path=sma20_path,
        sma50_path=sma50_path,
        volume_bars=volume_bars,
        has_bands=has_bands,
        has_smas=has_smas,
        has_volume=has_volume,
        bb_upper_label=bb_upper_label,
        bb_lower_label=bb_lower_label,
        sma20_label=sma20_label,
        sma50_label=sma50_label,
    )
