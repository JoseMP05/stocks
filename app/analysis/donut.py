"""Geometry for the allocation donut.

Same contract as `sparkline.py` and `dial.py`: coordinates are produced here,
the SVG markup lives in the template, and nothing needs JavaScript.

Kept generic on purpose — labelled values in, geometry out — so it can be
tested without any broker model in sight.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

VIEW_SIZE = 220.0
CENTER = 110.0
OUTER_R = 92.0
INNER_R = 58.0

# Slice separation, in degrees, taken out of each wedge. Real whitespace rather
# than a stroke, so wedges stay apart even where two hues sit close together.
GAP_DEG = 1.4

# Categorical hues are assigned in fixed order and never cycled, so the number
# of tones is the number of wedges the ring can carry. Anything past that folds
# into one residual wedge, which wears a neutral instead of a ninth hue.
TONES = 8
OTHER_TONE = 0
OTHER_LABEL = "Otros"


@dataclass(frozen=True)
class DonutSlice:
    label: str
    value: float
    share: float  # 0..1
    path: str
    tone: int  # 1..TONES, or OTHER_TONE for the residual wedge
    start_deg: float
    end_deg: float
    # Optional sub-labels naming what this wedge is made of. The geometry does
    # not care what they mean; it only has to keep them attached to the right
    # wedge, including through the fold into "Otros".
    members: tuple[str, ...] = ()


@dataclass(frozen=True)
class Donut:
    total: float
    slices: list[DonutSlice] = field(default_factory=list)
    view_size: float = VIEW_SIZE
    center: float = CENTER
    outer_r: float = OUTER_R
    inner_r: float = INNER_R
    # A single wedge covering the whole ring cannot be drawn as an arc: its
    # start and end points coincide, and the browser paints nothing at all.
    # The template checks this and emits a ring of two circles instead.
    full_circle: bool = False
    top_label: str = ""
    top_share: float = 0.0


def _point(degrees: float, radius: float) -> tuple[float, float]:
    """Polar to cartesian, with 0° at twelve o'clock and angles running clockwise."""
    radians = math.radians(degrees)
    return CENTER + radius * math.sin(radians), CENTER - radius * math.cos(radians)


def _fmt(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _sector(start: float, end: float) -> str:
    """An annular sector: out along the outer arc, back along the inner one."""
    large = 1 if (end - start) > 180.0 else 0
    ox1, oy1 = _point(start, OUTER_R)
    ox2, oy2 = _point(end, OUTER_R)
    ix2, iy2 = _point(end, INNER_R)
    ix1, iy1 = _point(start, INNER_R)
    return (
        f"M {_fmt(ox1)} {_fmt(oy1)} "
        f"A {OUTER_R} {OUTER_R} 0 {large} 1 {_fmt(ox2)} {_fmt(oy2)} "
        f"L {_fmt(ix2)} {_fmt(iy2)} "
        f"A {INNER_R} {INNER_R} 0 {large} 0 {_fmt(ix1)} {_fmt(iy1)} Z"
    )


def _full_annulus() -> str:
    """The whole ring as one path: two closed circles, cut with `evenodd`.

    A wedge covering 360° cannot be an arc — its start and end points coincide,
    so the browser paints nothing at all. That is not a corner case: any
    account holding a single asset class lands here on first render.
    """
    top_o, bottom_o = _point(0.0, OUTER_R), _point(180.0, OUTER_R)
    top_i, bottom_i = _point(0.0, INNER_R), _point(180.0, INNER_R)
    return (
        f"M {_fmt(top_o[0])} {_fmt(top_o[1])} "
        f"A {OUTER_R} {OUTER_R} 0 1 1 {_fmt(bottom_o[0])} {_fmt(bottom_o[1])} "
        f"A {OUTER_R} {OUTER_R} 0 1 1 {_fmt(top_o[0])} {_fmt(top_o[1])} Z "
        f"M {_fmt(top_i[0])} {_fmt(top_i[1])} "
        f"A {INNER_R} {INNER_R} 0 1 1 {_fmt(bottom_i[0])} {_fmt(bottom_i[1])} "
        f"A {INNER_R} {INNER_R} 0 1 1 {_fmt(top_i[0])} {_fmt(top_i[1])} Z"
    )


def build_donut(
    items: list[tuple[str, float]],
    max_slices: int = TONES,
    members: dict[str, list[str]] | None = None,
) -> Donut | None:
    """Build the ring for a set of labelled values, largest wedge first.

    `members` optionally names what each label is made of; the folded "Otros"
    wedge inherits the members of everything folded into it, in order.

    Returns None when there is nothing to draw — no items, or nothing positive
    among them. Mirrors `build_sparkline`, which returns None for a series too
    short to plot, so the template guard is the same shape either way.
    """
    positive = [(label, value) for label, value in items if value > 0]
    if not positive:
        return None

    by_label = members or {}
    ranked = sorted(positive, key=lambda pair: -pair[1])
    folded: dict[str, tuple[str, ...]] = {
        label: tuple(by_label.get(label, ())) for label, _ in ranked
    }

    if len(ranked) > max_slices:
        head = ranked[: max_slices - 1]
        tail = ranked[max_slices - 1:]
        tail_total = sum(value for _, value in tail)
        ranked = head + [(OTHER_LABEL, tail_total)]
        # The residual wedge is still answerable: it names the labels it
        # swallowed, or their own members when they had any.
        swallowed: list[str] = []
        for label, _ in tail:
            swallowed.extend(folded.get(label) or (label,))
        folded[OTHER_LABEL] = tuple(swallowed)

    total = sum(value for _, value in ranked)
    if total <= 0:
        return None

    top_label, top_value = ranked[0]

    if len(ranked) == 1:
        return Donut(
            total=total,
            slices=[
                DonutSlice(
                    label=top_label,
                    value=top_value,
                    share=1.0,
                    path=_full_annulus(),
                    tone=OTHER_TONE if top_label == OTHER_LABEL else 1,
                    start_deg=0.0,
                    end_deg=360.0,
                    members=folded.get(top_label, ()),
                )
            ],
            full_circle=True,
            top_label=top_label,
            top_share=1.0,
        )

    slices: list[DonutSlice] = []
    cursor = 0.0
    for index, (label, value) in enumerate(ranked):
        share = value / total
        sweep = share * 360.0
        # Take the gap out of the wedge, but never past the point where the
        # sweep would invert: a sliver thinner than the gap still has to render
        # as something, however thin.
        gap = min(GAP_DEG, sweep * 0.5)
        start = cursor + gap / 2.0
        end = cursor + sweep - gap / 2.0
        slices.append(
            DonutSlice(
                label=label,
                value=value,
                share=share,
                path=_sector(start, end),
                tone=OTHER_TONE if label == OTHER_LABEL else index + 1,
                start_deg=start,
                end_deg=end,
                members=folded.get(label, ()),
            )
        )
        cursor += sweep

    return Donut(
        total=total,
        slices=slices,
        top_label=top_label,
        top_share=top_value / total,
    )
