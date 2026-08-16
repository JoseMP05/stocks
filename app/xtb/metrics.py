"""Headline figures derived from a parsed XTB snapshot.

`build_metrics` checks its own arithmetic. The report carries three totals the
broker computed independently — realized P&L, the cash balance, and the open
value — and they are the only outside evidence that the nested open-position
rows were folded correctly and the footer rows were skipped. A mismatch is
recorded and shown rather than raised: it means the numbers deserve a second
look, not that the import failed.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from app.models import (
    Allocation,
    XtbCapitalPoint,
    XtbMetrics,
    XtbRealized,
    XtbSnapshot,
)

# How far our arithmetic may drift from the report's own totals before it is
# worth mentioning. The report rounds to cents, and summing ~100 rounded rows
# accumulates a little noise.
TOLERANCE = 0.02

UNCATEGORIZED = "Sin categoría"


def _pct(part: float, whole: float) -> float:
    return (part / whole * 100.0) if whole else 0.0


def _check(
    label: str, computed: float, reported: float | None, into: list[str]
) -> None:
    if reported is None or abs(computed - reported) <= TOLERANCE:
        return
    into.append(
        f"{label}: calculamos {computed:,.2f} y el reporte dice {reported:,.2f}."
    )


def build_metrics(snapshot: XtbSnapshot) -> XtbMetrics:
    """Derive every headline number, then reconcile against the report."""
    longs = [p for p in snapshot.open_positions if not p.is_short]

    open_value = sum(p.value for p in snapshot.open_positions)
    open_cost = sum(p.volume * p.open_price for p in longs)
    unrealized = sum(
        p.net_profit if p.net_profit is not None else p.value - p.volume * p.open_price
        for p in snapshot.open_positions
    )
    realized = sum(c.profit_loss for c in snapshot.closed_positions)

    by_bucket: dict[str, float] = defaultdict(float)
    for operation in snapshot.cash_operations:
        by_bucket[operation.bucket] += operation.amount

    deposits = by_bucket["deposit"]
    withdrawals = abs(by_bucket["withdrawal"])
    net_deposits = deposits - withdrawals
    # Every movement, transfers included — this is the account's actual cash,
    # which is what the report's own Total row measures.
    cash_balance = sum(operation.amount for operation in snapshot.cash_operations)

    # What the account is worth versus what was put in. The only figure here
    # that answers "did this make money", rather than "is this position up".
    total_return = open_value + cash_balance - net_deposits

    top = max(longs, key=lambda p: p.value, default=None)

    discrepancies: list[str] = []
    _check("Valor abierto", open_value, snapshot.reported.open_value, discrepancies)
    _check("P&L no realizado", unrealized, snapshot.reported.open_profit, discrepancies)
    _check("P&L realizado", realized, snapshot.reported.realized_pnl, discrepancies)
    _check("Saldo de caja", cash_balance, snapshot.reported.cash_balance, discrepancies)

    return XtbMetrics(
        currency=snapshot.currency,
        open_value=open_value,
        open_cost=open_cost,
        unrealized_pnl=unrealized,
        unrealized_pnl_pct=_pct(unrealized, open_cost),
        realized_pnl=realized,
        deposits=deposits,
        withdrawals=withdrawals,
        net_deposits=net_deposits,
        dividends=by_bucket["dividend"],
        withholding_tax=by_bucket["tax"],
        cash_balance=cash_balance,
        total_return=total_return,
        total_return_pct=_pct(total_return, net_deposits) if net_deposits > 0 else 0.0,
        holdings_count=len(longs),
        top_holding=top.xtb_symbol if top else "",
        top_holding_share=_pct(top.value, open_value) if top else 0.0,
        discrepancies=discrepancies,
    )


# ── closed-trade record ──────────────────────────────────────────────────────

def _holding_days(opened: str | None, closed: str | None) -> float | None:
    if not opened or not closed:
        return None
    try:
        delta = datetime.fromisoformat(closed) - datetime.fromisoformat(opened)
    except ValueError:
        return None
    return max(delta.total_seconds() / 86400.0, 0.0)


def build_realized(snapshot: XtbSnapshot) -> list[XtbRealized]:
    """Group finished trades by instrument, worst result last.

    This is the only view in the dashboard that describes behaviour rather than
    the current snapshot: what was actually sold, how often it worked, and how
    long positions were held.
    """
    grouped: dict[str, list] = defaultdict(list)
    names: dict[str, str] = {}
    for trade in snapshot.closed_positions:
        grouped[trade.xtb_symbol].append(trade)
        if trade.instrument:
            names.setdefault(trade.xtb_symbol, trade.instrument)

    records: list[XtbRealized] = []
    for symbol, trades in grouped.items():
        spans = [
            days
            for days in (_holding_days(t.opened_at, t.closed_at) for t in trades)
            if days is not None
        ]
        records.append(
            XtbRealized(
                symbol=symbol,
                instrument=names.get(symbol, ""),
                realized=sum(t.profit_loss for t in trades),
                trades=len(trades),
                wins=sum(1 for t in trades if t.profit_loss > 0),
                avg_holding_days=(sum(spans) / len(spans)) if spans else None,
            )
        )

    records.sort(key=lambda r: r.realized, reverse=True)
    return records


# ── capital curve ────────────────────────────────────────────────────────────

def build_capital_curve(snapshot: XtbSnapshot) -> list[XtbCapitalPoint]:
    """Cumulative cash story, one point per day with activity.

    Every series here comes from the cash ledger, so all three are exact. The
    market value of the holdings over time is deliberately absent: the export
    carries no historical valuations, and a curve invented from today's prices
    would look authoritative while being a guess.

    `invested` is net cash moved into positions — purchases less sale proceeds.
    It sits below the cost of what is still held by exactly the realized P&L,
    because a profitable sale returns more cash than it originally consumed.

    Realized profit is read straight off the closed positions rather than
    joined to the sell operations by position ID. A position closed in two
    chunks produces two closed rows and two sell operations sharing one ID, so
    that join both double-counts one leg and drops the other. Summing the
    closed rows is exact by construction.
    """
    # date -> [net deposit delta, invested delta, realized delta]
    deltas: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])

    for operation in snapshot.cash_operations:
        if not operation.at:
            continue
        day = operation.at[:10]
        if operation.bucket in {"deposit", "withdrawal"}:
            deltas[day][0] += operation.amount
        elif operation.bucket in {"purchase", "sell"}:
            # Purchases are negative and sales positive, so negating gives
            # cash moved *into* positions.
            deltas[day][1] -= operation.amount

    for trade in snapshot.closed_positions:
        if not trade.closed_at:
            continue
        deltas[trade.closed_at[:10]][2] += trade.profit_loss

    if not deltas:
        return []

    net_deposits = invested = realized = 0.0
    curve: list[XtbCapitalPoint] = []
    for day in sorted(deltas):
        deposit_delta, invested_delta, realized_delta = deltas[day]
        net_deposits += deposit_delta
        invested += invested_delta
        realized += realized_delta
        curve.append(
            XtbCapitalPoint(
                date=day,
                net_deposits=round(net_deposits, 2),
                invested=round(invested, 2),
                realized_pnl=round(realized, 2),
            )
        )

    return curve


# ── allocation ───────────────────────────────────────────────────────────────

def allocations(snapshot: XtbSnapshot, mode: str) -> list[Allocation]:
    """Break the open portfolio down by ticker, sector or asset class.

    A grouped bucket also carries the holdings inside it: "Industrials 16%"
    is only half an answer until you can see it is NOC, TE and SPCX. The
    by-ticker view leaves that empty, since there the label is the holding.

    Short positions are excluded: negative exposure has no honest share of a
    ring that adds up to 100%.
    """
    totals: dict[str, float] = defaultdict(float)
    members: dict[str, list[tuple[str, float]]] = defaultdict(list)
    grouped = mode in {"sector", "class"}

    for position in snapshot.open_positions:
        if position.is_short or position.value <= 0:
            continue
        symbol = position.yahoo_symbol or position.xtb_symbol
        if mode == "sector":
            label = position.sector or UNCATEGORIZED
        elif mode == "class":
            label = position.asset_class or UNCATEGORIZED
        else:
            label = symbol
        totals[label] += position.value
        if grouped:
            members[label].append((symbol, position.value))

    return [
        Allocation(
            label=label,
            value=value,
            members=[
                symbol
                for symbol, _ in sorted(members[label], key=lambda pair: -pair[1])
            ],
        )
        for label, value in sorted(totals.items(), key=lambda pair: -pair[1])
    ]
