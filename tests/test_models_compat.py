"""Backwards compatibility of the on-disk schemas.

`load_watchlist` returns an *empty* Watchlist on any ValidationError, so a
required new field does not degrade — it erases every position the user owns,
silently, on the next boot. That failure mode is why these tests exist.
"""

from __future__ import annotations

import json

import pytest

from app import storage
from app.models import Watchlist, WatchlistItem


def test_a_watchlist_written_before_source_existed_still_loads():
    raw = {"watchlist": [{"ticker": "AAA", "position": {"avg_cost": 10.0, "shares": 2.0}}]}
    loaded = Watchlist.model_validate(raw)

    assert loaded.watchlist[0].ticker == "AAA"
    assert loaded.watchlist[0].source == "manual"


def test_an_old_config_file_survives_a_round_trip(isolated_data):
    from app.config import WATCHLIST_FILE

    WATCHLIST_FILE.write_text(
        json.dumps({"watchlist": [{"ticker": "AAA", "position": {"avg_cost": 10.0, "invested": 20.0}}]}),
        encoding="utf-8",
    )

    loaded = storage.load_watchlist()

    # An empty list here would mean the positions were wiped, not degraded.
    assert [item.ticker for item in loaded.watchlist] == ["AAA"]
    assert loaded.watchlist[0].position.shares == pytest.approx(2.0)


def test_an_unreadable_snapshot_degrades_to_none(isolated_data):
    from app.config import XTB_SNAPSHOT_FILE

    XTB_SNAPSHOT_FILE.write_text('{"unexpected": true}', encoding="utf-8")

    assert storage.load_xtb_snapshot() is None


def test_source_is_written_out(isolated_data):
    storage.save_watchlist(Watchlist(watchlist=[WatchlistItem(ticker="AAA", source="xtb")]))

    raw = json.loads(storage.WATCHLIST_FILE.read_text(encoding="utf-8"))

    assert raw["watchlist"][0]["source"] == "xtb"
