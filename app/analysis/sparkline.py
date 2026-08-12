"""Server-side sparkline geometry for `AnalysisResult.price_series`.

No JavaScript and no charting library: the path data is computed here and the
template emits a plain `<svg>`. The SVG itself is decorative (`aria-hidden`),
so this module also produces a sampled text table that the template renders
visually hidden — that table, not the drawing, is what a screen reader gets.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Fixed drawing box. The SVG keeps its default `preserveAspectRatio`, so CSS
# scales it uniformly via `aspect-ratio`; stretching it with
# `preserveAspectRatio="none"` would squash the endpoint dot and the cost label.
VIEW_WIDTH = 300.0
VIEW_HEIGHT = 76.0

# Rows kept in the visually-hidden equivalent table.
TABLE_POINTS = 12


@dataclass(frozen=True)
class SparkRow:
    """One row of the text equivalent: a position in the series and its close."""

    index: int
    value: float


@dataclass(frozen=True)
class Sparkline:
    line_path: str
    area_path: str
    end_x: float
    end_y: float
    view_width: float = VIEW_WIDTH
    view_height: float = VIEW_HEIGHT
    # y of the dashed average-cost rule, only when a position exists.
    cost_y: float | None = None
    cost_value: float | None = None
    # Plotted domain (padded, and widened to include avg_cost).
    domain_low: float = 0.0
    domain_high: float = 0.0
    # Real series statistics, for the caption and the text table.
    low: float = 0.0
    high: float = 0.0
    last: float = 0.0
    point_count: int = 0
    rows: list[SparkRow] = field(default_factory=list)


def _fmt(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _sample(values: list[float], wanted: int) -> list[SparkRow]:
    """Take roughly `wanted` evenly spaced points, always keeping the ends."""
    total = len(values)
    if total <= wanted:
        return [SparkRow(index=i + 1, value=v) for i, v in enumerate(values)]
    step = (total - 1) / (wanted - 1)
    seen: list[int] = []
    for i in range(wanted):
        idx = round(i * step)
        if idx not in seen:
            seen.append(idx)
    return [SparkRow(index=i + 1, value=values[i]) for i in seen]


def build_sparkline(values: list[float], avg_cost: float | None = None) -> Sparkline | None:
    """Build the sparkline geometry, or None when there is nothing to draw."""
    series = [float(v) for v in values if v is not None]
    if len(series) < 2:
        return None

    low, high = min(series), max(series)
    # The cost line has to stay inside the frame, so it widens the domain.
    domain_low, domain_high = low, high
    if avg_cost is not None:
        domain_low = min(domain_low, avg_cost)
        domain_high = max(domain_high, avg_cost)

    pad = (domain_high - domain_low) * 0.12 or max(abs(domain_high) * 0.02, 1.0)
    domain_low -= pad
    domain_high += pad
    span = domain_high - domain_low

    def y_of(value: float) -> float:
        return VIEW_HEIGHT - (value - domain_low) / span * VIEW_HEIGHT

    last_index = len(series) - 1
    points = [
        (i / last_index * VIEW_WIDTH, y_of(v)) for i, v in enumerate(series)
    ]
    line = "M " + " L ".join(f"{_fmt(x)} {_fmt(y)}" for x, y in points)
    area = f"{line} L {_fmt(VIEW_WIDTH)} {_fmt(VIEW_HEIGHT)} L 0 {_fmt(VIEW_HEIGHT)} Z"
    end_x, end_y = points[-1]

    return Sparkline(
        line_path=line,
        area_path=area,
        end_x=round(end_x, 2),
        end_y=round(end_y, 2),
        cost_y=round(y_of(avg_cost), 2) if avg_cost is not None else None,
        cost_value=avg_cost,
        domain_low=domain_low,
        domain_high=domain_high,
        low=low,
        high=high,
        last=series[-1],
        point_count=len(series),
        rows=_sample(series, TABLE_POINTS),
    )
