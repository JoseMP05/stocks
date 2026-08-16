"""Sync policy tests.

`build_sync_plan` is pure, so the policy is checked here without a filesystem —
which is the point of keeping the deciding and the writing apart.
"""

from __future__ import annotations

import pytest

from app.models import Position, Watchlist, WatchlistItem
from app.xtb.parser import parse_workbook
from app.xtb.sync import build_sync_plan
from tests.conftest import _aggregate, _lot


def plan_for(workbook, current: Watchlist, **kwargs):
    return build_sync_plan(current, parse_workbook(workbook(**kwargs)))


def test_new_holdings_are_added(workbook):
    plan = plan_for(workbook, Watchlist())
    tickers = {item.ticker for item in plan.watchlist.watchlist}

    assert tickers == {"AAA", "BBB.L"}
    assert {c.ticker for c in plan.of("added")} == {"AAA", "BBB.L"}
    assert all(item.source == "xtb" for item in plan.watchlist.watchlist)


def test_a_hand_typed_position_is_corrected_by_the_broker(workbook):
    """The whole reason the feature exists: manual entries drift."""
    current = Watchlist(
        watchlist=[
            WatchlistItem(ticker="AAA", position=Position(avg_cost=99.0, shares=1.0))
        ]
    )
    plan = plan_for(workbook, current)
    aaa = next(i for i in plan.watchlist.watchlist if i.ticker == "AAA")

    assert aaa.position.avg_cost == pytest.approx(10.0)
    assert aaa.position.shares == pytest.approx(2.0)
    assert "antes 99" in next(c for c in plan.of("updated")).detail


def test_a_watch_only_ticker_is_left_alone(workbook):
    """No position is a real choice, not missing data."""
    current = Watchlist(watchlist=[WatchlistItem(ticker="ZZZ")])
    plan = plan_for(workbook, current)
    zzz = next(i for i in plan.watchlist.watchlist if i.ticker == "ZZZ")

    assert zzz.position is None
    assert zzz.source == "manual"
    assert [c.ticker for c in plan.of("unchanged")] == ["ZZZ"]


def test_a_manual_position_absent_from_the_report_is_untouched(workbook):
    """It might be held at another broker. Not ours to overwrite."""
    current = Watchlist(
        watchlist=[
            WatchlistItem(
                ticker="ZZZ", position=Position(avg_cost=5.0, shares=3.0), source="manual"
            )
        ]
    )
    plan = plan_for(workbook, current)
    zzz = next(i for i in plan.watchlist.watchlist if i.ticker == "ZZZ")

    assert zzz.position is not None
    assert zzz.position.avg_cost == pytest.approx(5.0)


def test_a_previously_synced_holding_that_is_gone_is_demoted_not_deleted(workbook):
    """Sold at the broker. Keep watching it; stop claiming a position."""
    current = Watchlist(
        watchlist=[
            WatchlistItem(
                ticker="OLD", position=Position(avg_cost=5.0, shares=3.0), source="xtb"
            )
        ]
    )
    plan = plan_for(workbook, current)
    tickers = [i.ticker for i in plan.watchlist.watchlist]
    old = next(i for i in plan.watchlist.watchlist if i.ticker == "OLD")

    assert "OLD" in tickers  # never removed
    assert old.position is None
    assert old.source == "manual"
    assert [c.ticker for c in plan.of("demoted")] == ["OLD"]


def test_short_positions_are_skipped_with_a_reason(workbook):
    """`_value_position` computes P&L assuming a long; a short would be wrong."""
    rows = [
        _aggregate("Short", "SSS.US", "STOCK", 1.0, 10.0, 12.0, 2.0),
        _lot("9001", "SSS.US", "SELL", 1.0, 10.0, 10.0, 12.0),
    ]
    plan = plan_for(workbook, Watchlist(), open_rows=rows)

    assert plan.watchlist.watchlist == []
    assert "corta" in plan.of("skipped")[0].detail


def test_unmappable_symbols_are_skipped_and_named(workbook):
    rows = [
        _aggregate("Odd", "ODD.ZZ", "STOCK", 1.0, 10.0, 9.0, 1.0),
        _lot("9002", "ODD.ZZ", "BUY", 1.0, 10.0, 10.0, 9.0),
    ]
    # An unknown suffix is passed through untouched, so it still syncs — what
    # must never happen is a silently mangled ticker.
    plan = plan_for(workbook, Watchlist(), open_rows=rows)

    assert [i.ticker for i in plan.watchlist.watchlist] == ["ODD.ZZ"]


def test_a_holding_with_no_price_is_skipped_rather_than_crashing(workbook):
    """Position() rejects a non-positive avg_cost; the plan must not raise."""
    rows = [
        _aggregate("Broken", "BRK.US", "STOCK", 1.0, 10.0, 0.0, 0.0),
        _lot("9003", "BRK.US", "BUY", 1.0, 10.0, 10.0, 0.0),
    ]
    plan = plan_for(workbook, Watchlist(), open_rows=rows)

    assert plan.watchlist.watchlist == []
    assert plan.of("skipped")[0].ticker == "BRK"


def test_invested_is_derived_from_shares_and_cost(workbook):
    plan = plan_for(workbook, Watchlist())
    aaa = next(i for i in plan.watchlist.watchlist if i.ticker == "AAA")

    # Not the report's Value column (24.0) — that is market value, not cost.
    assert aaa.position.invested == pytest.approx(20.0)
