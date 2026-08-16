"""Line of business for each holding.

The report's own Category column is asset class — STOCK or ETF — which does not
answer "what kind of business am I invested in". That has to come from the
market data provider.

Two tiers, cheapest first:

1. The cached analysis run. `Fundamentals.sector` is already filled in for every
   ticker the watchlist has analysed, so on an account whose holdings have been
   analysed at least once this costs nothing and touches no network.
2. A yfinance lookup, for whatever tier 1 missed.

There is deliberately no third cache of its own. `last_results.json` already is
the cache, and the Analizar button already refreshes it; a second store with its
own expiry would add an invalidation story for no benefit.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from app import storage
from app.config import MAX_FETCH_WORKERS
from app.models import XtbSnapshot

UNCATEGORIZED = "Sin categoría"


def _from_last_run() -> dict[str, str]:
    run = storage.load_last_run()
    if run is None:
        return {}
    return {
        result.ticker: result.fundamentals.sector
        for result in run.results
        if result.fundamentals.sector and result.fundamentals.sector != "N/A"
    }


def _fetch_sector(symbol: str) -> str:
    """One provider lookup. Never raises.

    Same posture as the fundamentals and news fetches in `market.py`: a symbol
    the provider does not know is a blank in the chart, not a failed import.
    """
    try:
        import yfinance as yf

        info = yf.Ticker(symbol).info or {}
    except Exception:
        return ""
    sector = info.get("sector")
    return sector if isinstance(sector, str) and sector else ""


def resolve_sectors(symbols: list[str], *, allow_fetch: bool = True) -> dict[str, str]:
    """Map symbols to sectors, going to the network only for what is missing."""
    wanted = sorted({symbol for symbol in symbols if symbol})
    if not wanted:
        return {}

    known = _from_last_run()
    resolved = {symbol: known[symbol] for symbol in wanted if symbol in known}

    missing = [symbol for symbol in wanted if symbol not in resolved]
    if missing and allow_fetch:
        workers = min(MAX_FETCH_WORKERS, len(missing))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for symbol, sector in zip(missing, pool.map(_fetch_sector, missing)):
                if sector:
                    resolved[symbol] = sector

    return resolved


def enrich(snapshot: XtbSnapshot, *, allow_fetch: bool = True) -> XtbSnapshot:
    """Fill in each open position's sector. Unknowns fall into one bucket."""
    sectors = resolve_sectors(
        [position.yahoo_symbol for position in snapshot.open_positions],
        allow_fetch=allow_fetch,
    )
    for position in snapshot.open_positions:
        position.sector = sectors.get(position.yahoo_symbol) or UNCATEGORIZED
    return snapshot
