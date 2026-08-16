"""Metric tests, anchored on the report's own totals."""

from __future__ import annotations

import pytest

from app.models import XtbSnapshot
from app.xtb.metrics import allocations, build_capital_curve, build_metrics, build_realized
from app.xtb.parser import parse_workbook


def test_metrics_reconcile_with_the_reports_own_totals(workbook):
    """The broker computed these independently; disagreeing means we are wrong."""
    metrics = build_metrics(parse_workbook(workbook()))

    assert metrics.discrepancies == []
    assert metrics.open_value == pytest.approx(69.0)
    assert metrics.unrealized_pnl == pytest.approx(-1.0)
    assert metrics.realized_pnl == pytest.approx(2.0)
    assert metrics.cash_balance == pytest.approx(42.5)


def test_cash_flows_are_split_by_bucket(workbook):
    metrics = build_metrics(parse_workbook(workbook()))

    assert metrics.deposits == pytest.approx(100.0)
    assert metrics.withdrawals == pytest.approx(10.0)
    assert metrics.net_deposits == pytest.approx(90.0)
    assert metrics.dividends == pytest.approx(0.5)


def test_total_return_compares_the_account_against_what_was_put_in(workbook):
    metrics = build_metrics(parse_workbook(workbook()))

    # 69 still held + 42.50 in cash - 90 contributed
    assert metrics.total_return == pytest.approx(21.5)
    assert metrics.total_return_pct == pytest.approx(21.5 / 90 * 100)


def test_a_disagreement_is_recorded_rather_than_raised(workbook):
    """A wrong footer must surface as a note, not a failed import."""
    metrics = build_metrics(parse_workbook(workbook(cash_total=999.0)))

    assert any("Saldo de caja" in note for note in metrics.discrepancies)
    assert metrics.cash_balance == pytest.approx(42.5)  # our own sum still stands


def test_ratios_survive_an_empty_account():
    metrics = build_metrics(XtbSnapshot(imported_at="2026-01-01T00:00:00"))

    assert metrics.total_return_pct == 0.0
    assert metrics.unrealized_pnl_pct == 0.0
    assert metrics.top_holding_share == 0.0


def test_realized_record_groups_trades_by_instrument(workbook):
    records = build_realized(parse_workbook(workbook()))

    assert len(records) == 1
    ccc = records[0]
    assert ccc.symbol == "CCC.US"
    assert ccc.trades == 2
    assert ccc.wins == 1
    assert ccc.win_rate == pytest.approx(50.0)
    assert ccc.realized == pytest.approx(2.0)
    assert ccc.avg_holding_days == pytest.approx(30.0)


def test_capital_curve_ends_on_the_account_totals(workbook):
    """Realized comes off the closed trades, never joined by position id.

    A position closed in two chunks shares one id across both legs, so that
    join double-counts one and drops the other.
    """
    snapshot = parse_workbook(workbook())
    curve = build_capital_curve(snapshot)
    metrics = build_metrics(snapshot)

    assert curve[-1].net_deposits == pytest.approx(metrics.net_deposits)
    assert curve[-1].realized_pnl == pytest.approx(metrics.realized_pnl)
    # Cash moved into positions: 20 + 50 spent, 22 returned.
    assert curve[-1].invested == pytest.approx(48.0)


def test_allocations_group_by_the_requested_dimension(workbook):
    snapshot = parse_workbook(workbook())
    snapshot.open_positions[0].sector = "Technology"
    snapshot.open_positions[1].sector = "Technology"

    by_ticker = {a.label: a.value for a in allocations(snapshot, "ticker")}
    by_class = {a.label: a.value for a in allocations(snapshot, "class")}
    by_sector = {a.label: a.value for a in allocations(snapshot, "sector")}

    assert by_ticker == {"AAA": pytest.approx(24.0), "BBB.L": pytest.approx(45.0)}
    assert by_class == {"STOCK": pytest.approx(24.0), "ETF": pytest.approx(45.0)}
    assert by_sector == {"Technology": pytest.approx(69.0)}


def test_grouped_buckets_name_the_holdings_inside_them(workbook):
    """A sector share is only half an answer without the tickers behind it."""
    snapshot = parse_workbook(workbook())
    snapshot.open_positions[0].sector = "Technology"  # AAA, 24.0
    snapshot.open_positions[1].sector = "Technology"  # BBB.L, 45.0

    bucket = allocations(snapshot, "sector")[0]

    # Largest holding first, so the list reads in the order that matters.
    assert bucket.members == ["BBB.L", "AAA"]


def test_the_by_ticker_view_has_no_members(workbook):
    """There the label already is the holding; repeating it is noise."""
    snapshot = parse_workbook(workbook())

    assert all(bucket.members == [] for bucket in allocations(snapshot, "ticker"))


def test_allocations_fall_back_to_one_bucket_without_sector_data(workbook):
    snapshot = parse_workbook(workbook())

    assert [a.label for a in allocations(snapshot, "sector")] == ["Sin categoría"]
