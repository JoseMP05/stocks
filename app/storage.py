"""Persistence for the watchlist, LLM settings and the cached analysis run."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from pydantic import ValidationError

from app.config import (
    RESULTS_CACHE_FILE,
    SETTINGS_FILE,
    WATCHLIST_BACKUP_FILE,
    WATCHLIST_FILE,
    XTB_SNAPSHOT_FILE,
)
from app.models import AnalysisRun, LLMSettings, Watchlist, WatchlistItem, XtbSnapshot


def _write_json(path: Path, payload: dict) -> None:
    """Write JSON atomically.

    A crash mid-write would otherwise leave a truncated watchlist behind —
    losing the user's positions. Write to a temp file in the same directory,
    then replace, which is atomic on every platform we care about.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    except Exception:
        Path(tmp_path).unlink(missing_ok=True)
        raise


def _read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except (json.JSONDecodeError, OSError):
        return None


# ── watchlist ────────────────────────────────────────────────────────────────

def load_watchlist() -> Watchlist:
    raw = _read_json(WATCHLIST_FILE)
    if raw is None:
        return Watchlist()
    try:
        return Watchlist.model_validate(raw)
    except ValidationError:
        return Watchlist()


def save_watchlist(watchlist: Watchlist) -> None:
    _write_json(WATCHLIST_FILE, watchlist.model_dump(exclude_none=True))


def add_ticker(item: WatchlistItem) -> Watchlist:
    """Add a ticker, or replace it if it is already tracked."""
    watchlist = load_watchlist()
    watchlist.watchlist = [w for w in watchlist.watchlist if w.ticker != item.ticker]
    watchlist.watchlist.append(item)
    save_watchlist(watchlist)
    return watchlist


def update_ticker(ticker: str, item: WatchlistItem) -> Watchlist:
    watchlist = load_watchlist()
    watchlist.watchlist = [item if w.ticker == ticker.upper() else w for w in watchlist.watchlist]
    save_watchlist(watchlist)
    return watchlist


def set_ticker_active(ticker: str, active: bool) -> Watchlist:
    """Pause or resume a ticker, leaving everything else about it untouched."""
    watchlist = load_watchlist()
    for item in watchlist.watchlist:
        if item.ticker == ticker.upper():
            item.active = active
    save_watchlist(watchlist)
    return watchlist


def remove_ticker(ticker: str) -> Watchlist:
    watchlist = load_watchlist()
    watchlist.watchlist = [w for w in watchlist.watchlist if w.ticker != ticker.upper()]
    save_watchlist(watchlist)
    return watchlist


# ── LLM settings ─────────────────────────────────────────────────────────────

def load_settings() -> LLMSettings:
    raw = _read_json(SETTINGS_FILE)
    if raw is None:
        return LLMSettings()
    try:
        return LLMSettings.model_validate(raw)
    except ValidationError:
        return LLMSettings()


def save_settings(settings: LLMSettings) -> None:
    _write_json(SETTINGS_FILE, settings.model_dump())


# ── cached analysis run ──────────────────────────────────────────────────────

def load_last_run() -> AnalysisRun | None:
    raw = _read_json(RESULTS_CACHE_FILE)
    if raw is None:
        return None
    try:
        return AnalysisRun.model_validate(raw)
    except ValidationError:
        # A stale cache from an older schema is not worth recovering.
        return None


def save_last_run(run: AnalysisRun) -> None:
    _write_json(RESULTS_CACHE_FILE, run.model_dump())


# ── XTB snapshot ─────────────────────────────────────────────────────────────

def load_xtb_snapshot() -> XtbSnapshot | None:
    raw = _read_json(XTB_SNAPSHOT_FILE)
    if raw is None:
        return None
    try:
        return XtbSnapshot.model_validate(raw)
    except ValidationError:
        # Same posture as the analysis cache: a snapshot from an older schema
        # is re-createable by uploading the file again.
        return None


def save_xtb_snapshot(snapshot: XtbSnapshot) -> None:
    _write_json(XTB_SNAPSHOT_FILE, snapshot.model_dump())


# ── watchlist backup ─────────────────────────────────────────────────────────
#
# An XTB import overwrites positions the user typed by hand. That is the point
# of the feature, but it means one upload can silently replace real financial
# data, so the previous state is kept where a single click can bring it back.

def backup_watchlist() -> bool:
    """Snapshot the current watchlist. False when there is nothing to back up."""
    raw = _read_json(WATCHLIST_FILE)
    if raw is None:
        return False
    _write_json(WATCHLIST_BACKUP_FILE, raw)
    return True


def has_watchlist_backup() -> bool:
    return WATCHLIST_BACKUP_FILE.exists()


def restore_watchlist_backup() -> bool:
    """Put the backup back. False when there is none, or it no longer parses."""
    raw = _read_json(WATCHLIST_BACKUP_FILE)
    if raw is None:
        return False
    try:
        watchlist = Watchlist.model_validate(raw)
    except ValidationError:
        return False
    save_watchlist(watchlist)
    return True
