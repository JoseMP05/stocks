"""Pausing a ticker.

A paused ticker is the non-destructive alternative to deleting one: it stays on
disk, position and all, and only stops being analyzed. So the assertions here
are as much about what pausing must *not* touch — the position, the source, the
next XTB import — as about the ticker dropping out of the run.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app import storage
from app.analysis.market import run_analysis
from app.main import app
from app.models import Position, Watchlist, WatchlistItem
from app.xtb.sync import build_sync_plan
from app.xtb.parser import parse_workbook


@pytest.fixture
def client(isolated_data):
    return TestClient(app)


def seed(*items: WatchlistItem) -> None:
    storage.save_watchlist(Watchlist(watchlist=list(items)))


def stored(ticker: str) -> WatchlistItem:
    return next(w for w in storage.load_watchlist().watchlist if w.ticker == ticker)


def test_a_watchlist_written_before_active_existed_loads_as_active():
    raw = {"watchlist": [{"ticker": "AAA", "position": {"avg_cost": 10.0, "shares": 2.0}}]}

    assert Watchlist.model_validate(raw).watchlist[0].active is True


def test_pausing_keeps_the_position_and_the_source(client):
    seed(
        WatchlistItem(
            ticker="AAA", position=Position(avg_cost=10.0, shares=2.0), source="xtb"
        )
    )

    response = client.post("/watchlist/AAA/active", data={"active": "0"})

    assert response.status_code == 200
    item = stored("AAA")
    assert item.active is False
    assert item.position.avg_cost == pytest.approx(10.0)
    assert item.source == "xtb"


def test_the_toggle_sends_the_desired_state_not_a_flip(client):
    """Two pause requests leave the ticker paused, not back where it started."""
    seed(WatchlistItem(ticker="AAA"))

    client.post("/watchlist/AAA/active", data={"active": "0"})
    client.post("/watchlist/AAA/active", data={"active": "0"})

    assert stored("AAA").active is False

    client.post("/watchlist/AAA/active", data={"active": "1"})

    assert stored("AAA").active is True


def test_a_paused_ticker_is_written_to_disk(client):
    seed(WatchlistItem(ticker="AAA"))

    client.post("/watchlist/AAA/active", data={"active": "0"})

    # `save_watchlist` drops None fields; False is not None and must survive.
    raw = json.loads(storage.WATCHLIST_FILE.read_text(encoding="utf-8"))
    assert raw["watchlist"][0]["active"] is False


def test_editing_a_position_does_not_resurrect_a_paused_ticker(client):
    seed(WatchlistItem(ticker="AAA", source="xtb", active=False))

    response = client.post("/watchlist/AAA", data={"avg_cost": "12", "shares": "3"})

    assert response.status_code == 200
    item = stored("AAA")
    assert item.active is False
    assert item.source == "xtb"
    assert item.position.shares == pytest.approx(3.0)


def test_a_paused_ticker_is_never_fetched(monkeypatch):
    fetched: list[str] = []

    def spy(item: WatchlistItem):
        fetched.append(item.ticker)
        raise Exception("no network in tests")

    monkeypatch.setattr("app.analysis.market.analyze_ticker", spy)

    run = run_analysis(
        [WatchlistItem(ticker="AAA", active=False), WatchlistItem(ticker="BBB")]
    )

    assert fetched == ["BBB"]
    # A pause is not a failure either: AAA must not show up in the error list.
    assert [f.ticker for f in run.failures] == ["BBB"]


def test_an_all_paused_watchlist_runs_empty(monkeypatch):
    monkeypatch.setattr(
        "app.analysis.market.analyze_ticker",
        lambda item: pytest.fail("paused tickers must not be analyzed"),
    )

    run = run_analysis([WatchlistItem(ticker="AAA", active=False)])

    assert run.results == []
    assert run.portfolio is None


def test_an_import_updates_a_paused_holding_without_reactivating_it(workbook):
    snapshot = parse_workbook(workbook(), source_file="report.xlsx")
    current = Watchlist(
        watchlist=[
            WatchlistItem(
                ticker="AAA", position=Position(avg_cost=1.0, shares=1.0), active=False
            )
        ]
    )

    plan = build_sync_plan(current, snapshot)

    item = next(w for w in plan.watchlist.watchlist if w.ticker == "AAA")
    assert item.position.avg_cost == pytest.approx(10.0)  # broker's number wins
    assert item.active is False


def test_a_ticker_the_broker_no_longer_reports_stays_paused(workbook):
    snapshot = parse_workbook(workbook(), source_file="report.xlsx")
    current = Watchlist(
        watchlist=[
            WatchlistItem(
                ticker="OLD",
                position=Position(avg_cost=5.0, shares=3.0),
                source="xtb",
                active=False,
            )
        ]
    )

    plan = build_sync_plan(current, snapshot)

    item = next(w for w in plan.watchlist.watchlist if w.ticker == "OLD")
    assert item.position is None  # demoted to watch-only
    assert item.active is False
