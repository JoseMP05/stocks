"""Geometry for the capital curve.

Same contract as the other chart modules: coordinates here, markup in the
template, no JavaScript.

All three series are amounts in the account currency, so they share one scale.
A second y-axis would let two of them be drawn at whatever relative height
flattered the story, which is exactly the reason not to have one.
"""

from __future__ import annotations

from dataclasses import dataclass, field

VIEW_WIDTH = 320.0
VIEW_HEIGHT = 120.0
PAD_X = 4.0
PAD_TOP = 8.0
PAD_BOTTOM = 14.0


@dataclass(frozen=True)
class CurveLine:
    key: str
    label: str
    path: str
    last_x: float
    last_y: float
    last_value: float


@dataclass(frozen=True)
class Curve:
    lines: list[CurveLine] = field(default_factory=list)
    dates: list[str] = field(default_factory=list)
    view_width: float = VIEW_WIDTH
    view_height: float = VIEW_HEIGHT
    zero_y: float = 0.0
    show_zero: bool = False
    first_date: str = ""
    last_date: str = ""


def _fmt(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def build_curve(
    dates: list[str], series: list[tuple[str, str, list[float]]]
) -> Curve | None:
    """Build one path per series over a shared x-grid and a shared y-scale.

    `series` is (key, label, values); every list must be as long as `dates`.
    Returns None for anything too short to draw a line through, mirroring
    `build_sparkline`.
    """
    if len(dates) < 2 or not series:
        return None
    if any(len(values) != len(dates) for _, _, values in series):
        return None

    everything = [value for _, _, values in series for value in values]
    low = min(everything)
    high = max(everything)
    # A flat series would divide by zero; give it a band so it draws mid-height.
    span = (high - low) or (abs(high) or 1.0)

    plot_height = VIEW_HEIGHT - PAD_TOP - PAD_BOTTOM
    plot_width = VIEW_WIDTH - PAD_X * 2
    step = plot_width / (len(dates) - 1)

    def y_for(value: float) -> float:
        return PAD_TOP + (high - value) / span * plot_height

    lines: list[CurveLine] = []
    for key, label, values in series:
        points = [
            (PAD_X + index * step, y_for(value)) for index, value in enumerate(values)
        ]
        path = "M " + " L ".join(f"{_fmt(x)} {_fmt(y)}" for x, y in points)
        last_x, last_y = points[-1]
        lines.append(
            CurveLine(
                key=key,
                label=label,
                path=path,
                last_x=last_x,
                last_y=last_y,
                last_value=values[-1],
            )
        )

    return Curve(
        lines=lines,
        dates=dates,
        zero_y=y_for(0.0),
        show_zero=low < 0.0 < high,
        first_date=dates[0],
        last_date=dates[-1],
    )
