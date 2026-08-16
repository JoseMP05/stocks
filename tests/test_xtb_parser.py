"""Parser tests.

The open-positions dedup and the totals-row skipping are the highest-risk logic
in the import: both fail silently and both produce numbers that look plausible.
"""

from __future__ import annotations

import pytest

from app.xtb.parser import XtbParseError, excel_serial_to_iso, parse_workbook
from tests.conftest import _lot


def test_open_positions_keeps_aggregates_and_drops_lot_rows(workbook):
    """The one that matters: five rows in, two holdings out, nothing doubled."""
    snapshot = parse_workbook(workbook())

    assert len(snapshot.open_positions) == 2
    assert sum(p.value for p in snapshot.open_positions) == pytest.approx(69.0)
    # 138.0 would mean every instrument was counted twice.
    assert sum(p.value for p in snapshot.open_positions) != pytest.approx(138.0)


def test_current_price_is_taken_from_the_lot_rows(workbook):
    """The aggregate row leaves Current price blank; only the lots have it."""
    snapshot = parse_workbook(workbook())
    aaa = next(p for p in snapshot.open_positions if p.xtb_symbol == "AAA.US")

    assert aaa.current_price == pytest.approx(12.0)


def test_multi_lot_holding_folds_into_one_position(workbook):
    snapshot = parse_workbook(workbook())
    bbb = next(p for p in snapshot.open_positions if p.xtb_symbol == "BBB.UK")

    assert len(bbb.lots) == 2
    assert bbb.volume == pytest.approx(1.0)  # the aggregate's volume, not 0.6 + 0.4 doubled
    assert {lot.position_id for lot in bbb.lots} == {"1002", "1003"}


def test_lot_rows_without_an_aggregate_are_still_captured(workbook):
    """A holding with no summary row is synthesised rather than dropped."""
    snapshot = parse_workbook(
        workbook(
            open_rows=[
                _lot("1002", "BBB.UK", "BUY", 0.6, 27.0, 45.0, 50.0),
                _lot("1003", "BBB.UK", "BUY", 0.4, 18.0, 45.0, 60.0),
            ]
        )
    )

    assert len(snapshot.open_positions) == 1
    holding = snapshot.open_positions[0]
    assert holding.value == pytest.approx(45.0)
    assert holding.volume == pytest.approx(1.0)
    # Volume-weighted: (0.6 * 50 + 0.4 * 60) / 1.0
    assert holding.open_price == pytest.approx(54.0)


def test_header_is_found_when_the_preamble_grows(workbook):
    """Column names locate the header; a row count would shift every field."""
    snapshot = parse_workbook(workbook(extra_preamble=3))

    assert len(snapshot.open_positions) == 2
    assert snapshot.reported.open_value == pytest.approx(69.0)


def test_closed_positions_skips_the_profit_loss_footer(workbook):
    snapshot = parse_workbook(workbook())

    assert len(snapshot.closed_positions) == 2
    assert snapshot.reported.realized_pnl == pytest.approx(2.0)


def test_cash_operations_skips_the_total_footer(workbook):
    snapshot = parse_workbook(workbook())

    assert len(snapshot.cash_operations) == 7
    assert snapshot.reported.cash_balance == pytest.approx(42.5)
    assert all(op.type != "Total" for op in snapshot.cash_operations)


def test_cash_buckets_are_normalised(workbook):
    snapshot = parse_workbook(workbook())
    buckets = [op.bucket for op in snapshot.cash_operations]

    assert buckets.count("purchase") == 2
    assert buckets.count("sell") == 2
    assert buckets.count("deposit") == 1
    assert buckets.count("withdrawal") == 1
    assert buckets.count("dividend") == 1


def test_unknown_cash_type_lands_in_other_and_warns(workbook):
    from tests.conftest import DEFAULT_CASH, _cash

    snapshot = parse_workbook(
        workbook(cash_rows=[*DEFAULT_CASH, _cash("Interest credit", "", 1.0)])
    )
    odd = next(op for op in snapshot.cash_operations if op.type == "Interest credit")

    assert odd.bucket == "other"
    assert any("Interest credit" in warning for warning in snapshot.warnings)


def test_ticker_suffixes_map_to_the_data_provider(workbook):
    snapshot = parse_workbook(workbook())
    mapped = {p.xtb_symbol: p.yahoo_symbol for p in snapshot.open_positions}

    assert mapped["AAA.US"] == "AAA"
    assert mapped["BBB.UK"] == "BBB.L"


def test_excel_serial_converts_from_the_1899_epoch():
    # Excel counts from 1899-12-30, absorbing the phantom 1900 leap day. The
    # expected value here matches openpyxl's own conversion of a date-formatted
    # cell, which is the other shape the same timestamp arrives in.
    assert excel_serial_to_iso(46175.5) == "2026-06-02T12:00:00"
    assert excel_serial_to_iso(None) is None
    assert excel_serial_to_iso("") is None


def test_position_ids_survive_as_integer_strings(workbook):
    """They arrive as floats; str() would give '2001.0', which matches nothing."""
    snapshot = parse_workbook(workbook())

    assert {t.position_id for t in snapshot.closed_positions} == {"2001", "2002"}


def test_missing_sheet_is_reported_by_name(workbook):
    with pytest.raises(XtbParseError, match="Cash Operations"):
        parse_workbook(workbook(sheets=("Open Positions", "Closed Positions")))


def test_garbage_bytes_raise_a_readable_error():
    with pytest.raises(XtbParseError):
        parse_workbook(b"this is not a spreadsheet")


def test_unrecognisable_header_names_the_missing_columns():
    """All three sheets present, none of them shaped like an XTB export."""
    from io import BytesIO

    from openpyxl import Workbook

    book = Workbook()
    book.remove(book.active)
    for name in ("Open Positions", "Closed Positions", "Cash Operations"):
        book.create_sheet(name).append(["nothing", "useful"])
    buffer = BytesIO()
    book.save(buffer)

    with pytest.raises(XtbParseError, match="faltan las columnas"):
        parse_workbook(buffer.getvalue())
