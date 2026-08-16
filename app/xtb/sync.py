"""Folding an imported portfolio into the watchlist.

The policy, in one line: **the broker is authoritative for the tickers it
reports, everything else is left alone, and nothing is ever deleted.**

Overwriting hand-typed positions is the point of the feature — a manually kept
watchlist drifts, and the broker's own numbers are the correction. Deleting is
a different matter. A ticker with no position is a legitimate watch-only entry,
and removing one is a click the user can make themselves; putting it back after
an import silently dropped it is not. So a holding that has disappeared from the
broker is demoted to watch-only rather than removed.

`build_sync_plan` is pure and does the deciding; `apply_sync` is the thin shell
that touches disk. Splitting them is what makes the policy testable without a
filesystem.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from app import storage
from app.models import Position, Watchlist, WatchlistItem, XtbOpenPosition, XtbSnapshot

Action = Literal["added", "updated", "demoted", "skipped", "unchanged"]


@dataclass(frozen=True)
class SyncChange:
    ticker: str
    action: Action
    detail: str = ""


@dataclass
class SyncPlan:
    watchlist: Watchlist
    changes: list[SyncChange] = field(default_factory=list)

    @property
    def touched(self) -> bool:
        return any(c.action in {"added", "updated", "demoted"} for c in self.changes)

    def of(self, action: Action) -> list[SyncChange]:
        return [c for c in self.changes if c.action == action]


def _position_for(holding: XtbOpenPosition) -> Position:
    """Broker holding to watchlist position.

    `invested` is deliberately not passed. `Position.derive_missing_size`
    computes it from shares × avg_cost and documents that shares wins when both
    are given, so supplying the report's Value column — which is current market
    value, not cost — would be discarded anyway.
    """
    return Position(avg_cost=holding.open_price, shares=holding.volume)


def build_sync_plan(current: Watchlist, snapshot: XtbSnapshot) -> SyncPlan:
    """Decide what the watchlist should become. Touches nothing."""
    holdings: dict[str, XtbOpenPosition] = {}
    changes: list[SyncChange] = []

    for holding in snapshot.open_positions:
        if not holding.yahoo_symbol:
            changes.append(
                SyncChange(
                    ticker=holding.xtb_symbol,
                    action="skipped",
                    detail="sin equivalente en el proveedor de datos",
                )
            )
            continue
        if holding.is_short:
            changes.append(
                SyncChange(
                    ticker=holding.yahoo_symbol,
                    action="skipped",
                    detail="posición corta: el P&L de la watchlist asume una posición larga",
                )
            )
            continue
        if holding.open_price <= 0 or holding.volume <= 0:
            changes.append(
                SyncChange(
                    ticker=holding.yahoo_symbol,
                    action="skipped",
                    detail="el reporte no trae precio de apertura o volumen",
                )
            )
            continue
        holdings[holding.yahoo_symbol] = holding

    items: list[WatchlistItem] = []
    seen: set[str] = set()

    for item in current.watchlist:
        holding = holdings.get(item.ticker)
        if holding is not None:
            seen.add(item.ticker)
            before = item.position.avg_cost if item.position else None
            items.append(
                WatchlistItem(
                    ticker=item.ticker,
                    position=_position_for(holding),
                    source="xtb",
                )
            )
            detail = f"precio de compra {holding.open_price:,.2f}"
            if before is not None and abs(before - holding.open_price) > 0.005:
                detail += f" (antes {before:,.2f})"
            changes.append(SyncChange(ticker=item.ticker, action="updated", detail=detail))
            continue

        if item.source == "xtb" and item.position is not None:
            # Held through a previous import, gone from this one. Almost
            # certainly sold — keep watching it, stop claiming a position.
            items.append(WatchlistItem(ticker=item.ticker, position=None, source="manual"))
            changes.append(
                SyncChange(
                    ticker=item.ticker,
                    action="demoted",
                    detail="ya no figura en el broker: queda en seguimiento, sin posición",
                )
            )
            continue

        items.append(item)
        changes.append(SyncChange(ticker=item.ticker, action="unchanged"))

    for symbol, holding in holdings.items():
        if symbol in seen:
            continue
        items.append(
            WatchlistItem(ticker=symbol, position=_position_for(holding), source="xtb")
        )
        changes.append(
            SyncChange(
                ticker=symbol,
                action="added",
                detail=f"{holding.volume:g} @ {holding.open_price:,.2f}",
            )
        )

    return SyncPlan(watchlist=Watchlist(watchlist=items), changes=changes)


def apply_sync(snapshot: XtbSnapshot) -> SyncPlan:
    """Write the plan to disk, keeping the previous watchlist recoverable.

    The backup is taken even when nothing changes: it costs one small file and
    it is the difference between "undo" being a button and being a support
    request.
    """
    plan = build_sync_plan(storage.load_watchlist(), snapshot)
    storage.backup_watchlist()
    storage.save_watchlist(plan.watchlist)
    return plan
