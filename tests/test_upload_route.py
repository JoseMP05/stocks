"""Route tests.

The recurring assertion is the status code: htmx discards the body of a 4xx, so
every failure here has to arrive as a 200 carrying its message, or the user sees
nothing at all.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app import storage
from app.config import MAX_UPLOAD_BYTES
from app.main import app
from app.models import Position, Watchlist, WatchlistItem


@pytest.fixture
def client(isolated_data, monkeypatch):
    # No network in tests: the sector lookup falls back to its bucket.
    monkeypatch.setattr("app.xtb.sectors._fetch_sector", lambda symbol: "")
    return TestClient(app)


def upload(client, workbook, **data):
    return client.post(
        "/xtb/upload",
        files={"file": ("report.xlsx", workbook(), "application/octet-stream")},
        data=data,
    )


def test_a_successful_upload_persists_and_renders(client, workbook):
    response = upload(client, workbook)

    assert response.status_code == 200
    assert "donut-slice" in response.text
    assert storage.load_xtb_snapshot() is not None


def test_the_snapshot_survives_a_reload(client, workbook):
    upload(client, workbook)
    page = client.get("/")

    assert page.status_code == 200
    assert "donut-slice" in page.text


def test_wrong_extension_returns_200_with_the_message(client):
    response = client.post(
        "/xtb/upload", files={"file": ("notes.pdf", b"%PDF-1.4", "application/pdf")}
    )

    assert response.status_code == 200
    assert ".xlsx" in response.text
    assert storage.load_xtb_snapshot() is None


def test_corrupt_file_returns_200_with_the_message(client):
    response = client.post(
        "/xtb/upload", files={"file": ("report.xlsx", b"not a zip", "application/octet-stream")}
    )

    assert response.status_code == 200
    assert "No se pudo abrir el archivo" in response.text


def test_oversized_upload_returns_200_with_the_message(client):
    response = client.post(
        "/xtb/upload",
        files={"file": ("report.xlsx", b"x" * (MAX_UPLOAD_BYTES + 1), "application/octet-stream")},
    )

    assert response.status_code == 200
    assert "supera los" in response.text


def test_sync_unchecked_leaves_the_watchlist_alone(client, workbook):
    storage.save_watchlist(
        Watchlist(watchlist=[WatchlistItem(ticker="AAA", position=Position(avg_cost=99.0, shares=1.0))])
    )
    before = json.dumps(storage.load_watchlist().model_dump(), sort_keys=True)

    upload(client, workbook)

    assert json.dumps(storage.load_watchlist().model_dump(), sort_keys=True) == before


def test_sync_checked_rewrites_positions_and_reports_the_diff(client, workbook):
    storage.save_watchlist(
        Watchlist(watchlist=[WatchlistItem(ticker="AAA", position=Position(avg_cost=99.0, shares=1.0))])
    )

    response = upload(client, workbook, sync_watchlist="1")
    aaa = next(i for i in storage.load_watchlist().watchlist if i.ticker == "AAA")

    assert aaa.position.avg_cost == pytest.approx(10.0)
    assert "Qué cambió en la watchlist" in response.text
    # The rail is refreshed in the same response, so it cannot show stale values.
    assert 'id="watchlist" hx-swap-oob="true"' in response.text


def test_undo_restores_the_pre_sync_watchlist(client, workbook):
    storage.save_watchlist(
        Watchlist(watchlist=[WatchlistItem(ticker="AAA", position=Position(avg_cost=99.0, shares=1.0))])
    )
    upload(client, workbook, sync_watchlist="1")

    response = client.post("/xtb/sync/undo")
    aaa = next(i for i in storage.load_watchlist().watchlist if i.ticker == "AAA")

    assert response.status_code == 200
    assert aaa.position.avg_cost == pytest.approx(99.0)


def test_undo_without_a_backup_says_so(client):
    response = client.post("/xtb/sync/undo")

    assert response.status_code == 200
    assert "No hay una copia previa" in response.text
