"""Geometry for the signal dial, the app's signature instrument.

The scale is not invented: it mirrors the scoring in `market.py` exactly.
The verdict there comes from `bull - bear` (ALCISTA above +1, BAJISTA below
-1, NEUTRAL in between), and the largest tally either side can reach is 5.0
(RSI 1 + MACD 1 + Bollinger 1 + SMA20 0.5 + SMA50 0.5 + SMA200 1.0). Scores
move in 0.5 steps, so the dial gets a tick every 0.5.

Only coordinates are produced here; the SVG markup lives in the template.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

# Pivot, radius and viewBox of the dial face. Keeping the viewBox origin at
# 0 0 matters: a non-zero min-y would shift `transform-origin` in CSS and
# drop the needle pivot somewhere other than the hub.
PIVOT_X = 110.0
PIVOT_Y = 88.0
RADIUS = 74.0
VIEW_WIDTH = 220.0
VIEW_HEIGHT = 96.0

SWEEP = 70.0  # degrees either side of vertical
SCALE_MAX = 5.0  # max |bull - bear| the scoring can produce
THRESHOLD = 1.0  # |net| <= 1 stays NEUTRAL
STEP = 0.5  # scoring granularity
LABELLED = (-5.0, -1.0, 0.0, 1.0, 5.0)

MINUS = "−"  # true minus sign, not a hyphen


@dataclass(frozen=True)
class DialTick:
    """One scale mark, plus its label when the mark is a labelled major."""

    x1: float
    y1: float
    x2: float
    y2: float
    major: bool
    threshold: bool
    label: str | None = None
    label_x: float = 0.0
    label_y: float = 0.0


@dataclass(frozen=True)
class Dial:
    net: float
    angle: float
    verdict_direction: str
    net_label: str
    pivot_x: float = PIVOT_X
    pivot_y: float = PIVOT_Y
    view_width: float = VIEW_WIDTH
    view_height: float = VIEW_HEIGHT
    needle_x: float = 0.0
    needle_y: float = 0.0
    hub_radius: float = 4.5
    arc_full: str = ""
    arc_neutral: str = ""
    ticks: list[DialTick] = field(default_factory=list)


def angle_for(net: float) -> float:
    """Map a net signal to a needle angle, clamped to the dial's sweep."""
    return max(-1.0, min(1.0, net / SCALE_MAX)) * SWEEP


def _point(degrees: float, radius: float) -> tuple[float, float]:
    rad = math.radians(degrees)
    return PIVOT_X + radius * math.sin(rad), PIVOT_Y - radius * math.cos(rad)


def _fmt(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _arc(net_from: float, net_to: float, radius: float) -> str:
    x1, y1 = _point(angle_for(net_from), radius)
    x2, y2 = _point(angle_for(net_to), radius)
    return f"M {_fmt(x1)} {_fmt(y1)} A {radius} {radius} 0 0 1 {_fmt(x2)} {_fmt(y2)}"


def _build_ticks() -> list[DialTick]:
    ticks: list[DialTick] = []
    count = int(SCALE_MAX / STEP)
    for i in range(-count, count + 1):
        value = i * STEP
        major = value in LABELLED
        degrees = angle_for(value)
        inner = RADIUS - (9.0 if major else 4.0)
        x1, y1 = _point(degrees, inner)
        x2, y2 = _point(degrees, RADIUS)
        label = None
        label_x = label_y = 0.0
        if major:
            label_x, label_y = _point(degrees, RADIUS - 17.0)
            label = "0" if value == 0 else f"{value:+.0f}".replace("-", MINUS)
        ticks.append(
            DialTick(
                x1=x1,
                y1=y1,
                x2=x2,
                y2=y2,
                major=major,
                threshold=abs(value) == THRESHOLD,
                label=label,
                label_x=label_x,
                label_y=label_y,
            )
        )
    return ticks


def build_dial(bull: float, bear: float) -> Dial:
    """Build the dial geometry for one bull/bear tally."""
    net = bull - bear
    degrees = angle_for(net)
    # Stops short of the numerals at RADIUS - 17: at RADIUS - 20 the tip
    # collided with the "0" whenever the net signal sat near the centre.
    needle_x, needle_y = _point(0.0, RADIUS - 27.0)

    if net > THRESHOLD:
        direction = "up"
    elif net < -THRESHOLD:
        direction = "down"
    else:
        direction = "flat"

    return Dial(
        net=net,
        angle=round(degrees, 2),
        verdict_direction=direction,
        net_label=f"{net:+.1f}".replace("-", MINUS),
        needle_x=needle_x,
        needle_y=needle_y,
        arc_full=_arc(-SCALE_MAX, SCALE_MAX, RADIUS),
        arc_neutral=_arc(-THRESHOLD, THRESHOLD, RADIUS),
        ticks=_build_ticks(),
    )
