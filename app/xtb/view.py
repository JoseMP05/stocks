"""Assembles everything the dashboard template needs from a snapshot.

Built in Python rather than exposed as Jinja globals the way `build_sparkline`
is. The sparkline is called per ticker inside a loop over cached results, so it
has to be reachable from the template; the dashboard is one figure whose data
has to be grouped and ranked first, and doing that in a template would spread
the arithmetic across two languages.

Both the upload route and the page load render from the same builder, so a
restored snapshot looks identical to a freshly imported one.
"""

from __future__ import annotations

from app.analysis.curve import build_curve
from app.analysis.donut import build_donut
from app.models import XtbSnapshot
from app.xtb.metrics import allocations, build_capital_curve, build_metrics, build_realized

# Ring modes, in the order their radio buttons appear. "ticker" leads because
# it is the breakdown that needs no outside data to be correct.
MODES: list[tuple[str, str]] = [
    ("ticker", "Por acción"),
    ("sector", "Por sector"),
    ("class", "Por tipo de activo"),
]

CURVE_SERIES: list[tuple[str, str]] = [
    ("deposits", "Capital aportado"),
    ("invested", "Puesto en posiciones"),
    ("realized", "Ganancia realizada"),
]


def build_view(snapshot: XtbSnapshot) -> dict:
    """One dict with the metrics, the three rings, the trade record and the curve."""
    donuts = {}
    for mode, _ in MODES:
        buckets = allocations(snapshot, mode)
        donuts[mode] = build_donut(
            [(a.label, a.value) for a in buckets],
            members={a.label: a.members for a in buckets if a.members},
        )

    points = build_capital_curve(snapshot)
    curve = build_curve(
        [point.date for point in points],
        [
            ("deposits", "Capital aportado", [p.net_deposits for p in points]),
            ("invested", "Puesto en posiciones", [p.invested for p in points]),
            ("realized", "Ganancia realizada", [p.realized_pnl for p in points]),
        ],
    )

    realized = build_realized(snapshot)
    # Bar lengths are relative to the biggest move in either direction, so a
    # single large winner cannot make every loss look negligible.
    scale = max((abs(record.realized) for record in realized), default=0.0)

    return {
        "snapshot": snapshot,
        "metrics": build_metrics(snapshot),
        "modes": MODES,
        "donuts": donuts,
        "curve": curve,
        # The same points the curve was built from, for its accessible table.
        "curve_points": points,
        "realized": realized,
        "realized_scale": scale,
    }
