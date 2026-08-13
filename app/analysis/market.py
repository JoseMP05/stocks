"""Market data retrieval and per-ticker analysis."""

from __future__ import annotations

import math
import warnings
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pandas as pd
import yfinance as yf

from app.config import MAX_FETCH_WORKERS, SPARKLINE_POINTS
from app.models import (
    AnalysisResult,
    AnalysisRun,
    FailedTicker,
    Fundamentals,
    Indicators,
    NewsItem,
    PortfolioSummary,
    Position,
    PositionSnapshot,
    WatchlistItem,
)

from .indicators import calc_bollinger, calc_macd, calc_rsi

warnings.filterwarnings("ignore")


class TickerDataError(Exception):
    """Raised when a ticker cannot be analyzed."""


def _clean(value) -> float | None:
    """Coerce a value to float, turning NaN/inf into None.

    Rolling windows produce NaN until they have enough history — a stock listed
    six months ago has no SMA200. NaN also cannot be serialized to valid JSON,
    so it never reaches the cache file.
    """
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) or math.isinf(f) else f


def _downsample(series: pd.Series, points: int = SPARKLINE_POINTS) -> list[float]:
    values = [v for v in (_clean(x) for x in series.tolist()) if v is not None]
    if len(values) <= points:
        return values
    # (n-1)/(points-1), not n/points: the latter's last sampled index is
    # `int((points-1) * n/points)`, which lands short of `n-1` (e.g. 248 of
    # 251 at n=252/points=80) — the chart would always lag the real last
    # close by a few sessions instead of ending on it.
    step = (len(values) - 1) / (points - 1)
    return [values[round(i * step)] for i in range(points)]


def _sample_indices(n: int, points: int = SPARKLINE_POINTS) -> list[int]:
    """Positions for a shared x-grid, using the same step arithmetic as `_downsample`.

    Bollinger, the SMAs and volume all need to land on the exact same x
    position as `price_series` — sampling each series independently (and
    dropping its own NaNs first, like `_downsample` does) would shift their
    warm-up periods relative to each other and misalign every layer.
    """
    if n <= points:
        return list(range(n))
    step = (n - 1) / (points - 1)
    return [round(i * step) for i in range(points)]


def _downsample_at(series: pd.Series, indices: list[int]) -> list[float | None]:
    """Sample a series at fixed positions, keeping `None` for NaN warm-up runs."""
    values = series.tolist()
    return [_clean(values[i]) for i in indices]


def _build_indicators(
    closes: pd.Series, volumes: pd.Series, price: float
) -> tuple[Indicators, float, float, dict[str, pd.Series]]:
    """Compute indicators and the weighted bull/bear tally.

    Returns the indicators plus the bull and bear scores. Indicators that are
    still NaN (not enough history) are skipped rather than scored — comparing
    against NaN always yields False, which the original script silently counted
    as a bearish signal.
    """
    rsi_series = calc_rsi(closes)
    macd_series, signal_series, _ = calc_macd(closes)
    bb_upper, bb_middle, bb_lower = calc_bollinger(closes)
    sma20_series = closes.rolling(20).mean()
    sma50_series = closes.rolling(50).mean()
    sma200_series = closes.rolling(200).mean()

    rsi = _clean(rsi_series.iloc[-1])
    macd = _clean(macd_series.iloc[-1])
    macd_signal_line = _clean(signal_series.iloc[-1])
    upper = _clean(bb_upper.iloc[-1])
    lower = _clean(bb_lower.iloc[-1])
    sma20 = _clean(sma20_series.iloc[-1])
    sma50 = _clean(sma50_series.iloc[-1])
    sma200 = _clean(sma200_series.iloc[-1])

    avg_volume = _clean(volumes.rolling(20).mean().iloc[-1])
    last_volume = _clean(volumes.iloc[-1])
    volume_ratio = last_volume / avg_volume if avg_volume and last_volume else 1.0

    bull = bear = 0.0

    if rsi is None:
        rsi_signal = "Sin datos suficientes"
    elif rsi < 30:
        rsi_signal = "SOBREVENTA — posible rebote"
        bull += 1
    elif rsi > 70:
        rsi_signal = "SOBRECOMPRA — posible corrección"
        bear += 1
    else:
        rsi_signal = "Zona neutral"

    if macd is None or macd_signal_line is None:
        macd_signal = "Sin datos suficientes"
    elif macd > macd_signal_line:
        macd_signal = "ALCISTA — MACD sobre señal"
        bull += 1
    else:
        macd_signal = "BAJISTA — MACD bajo señal"
        bear += 1

    if upper is None or lower is None:
        bb_signal = "Sin datos suficientes"
    elif price < lower:
        bb_signal = "Bajo banda inferior (sobreventa)"
        bull += 1
    elif price > upper:
        bb_signal = "Sobre banda superior (sobrecompra)"
        bear += 1
    else:
        bb_signal = "Dentro de bandas"

    def score_sma(sma: float | None, weight: float) -> bool | None:
        nonlocal bull, bear
        if sma is None:
            return None
        above = price > sma
        if above:
            bull += weight
        else:
            bear += weight
        return above

    above_sma20 = score_sma(sma20, 0.5)
    above_sma50 = score_sma(sma50, 0.5)
    above_sma200 = score_sma(sma200, 1.0)

    indicators = Indicators(
        rsi=rsi,
        rsi_signal=rsi_signal,
        macd=macd,
        macd_signal_line=macd_signal_line,
        macd_signal=macd_signal,
        bb_upper=upper,
        bb_lower=lower,
        bb_signal=bb_signal,
        sma20=sma20,
        sma50=sma50,
        sma200=sma200,
        above_sma20=above_sma20,
        above_sma50=above_sma50,
        above_sma200=above_sma200,
        volume_ratio=volume_ratio,
    )
    series = {
        "bb_upper": bb_upper,
        "bb_lower": bb_lower,
        "sma20": sma20_series,
        "sma50": sma50_series,
    }
    return indicators, bull, bear, series


def _build_fundamentals(info: dict, ticker: str, price: float) -> Fundamentals:
    high = _clean(info.get("fiftyTwoWeekHigh"))
    low = _clean(info.get("fiftyTwoWeekLow"))
    return Fundamentals(
        company=info.get("longName") or ticker,
        sector=info.get("sector") or "N/A",
        industry=info.get("industry") or "N/A",
        market_cap=_clean(info.get("marketCap")),
        pe=_clean(info.get("trailingPE")),
        forward_pe=_clean(info.get("forwardPE")),
        revenue=_clean(info.get("totalRevenue")),
        revenue_growth=_clean(info.get("revenueGrowth")),
        gross_margin=_clean(info.get("grossMargins")),
        eps=_clean(info.get("trailingEps")),
        forward_eps=_clean(info.get("forwardEps")),
        beta=_clean(info.get("beta")),
        target_price=_clean(info.get("targetMeanPrice")),
        recommendation=info.get("recommendationKey") or "N/A",
        week52_high=high,
        week52_low=low,
        dist_from_high=(price - high) / high * 100 if high else None,
        dist_from_low=(price - low) / low * 100 if low else None,
    )


def _build_news(raw_news: list) -> list[NewsItem]:
    """Normalize yfinance news entries.

    yfinance has shipped two shapes for this payload: a flat dict and one
    wrapped in a `content` key. Handle both so a schema change upstream
    degrades to an empty headline instead of a crash.
    """
    items: list[NewsItem] = []
    for entry in raw_news[:5]:
        content = entry.get("content", entry)
        url_obj = content.get("canonicalUrl", {})
        url = url_obj.get("url") if isinstance(url_obj, dict) else None
        # `summary` is plain text; the sibling `description` field carries
        # provider HTML, so it is deliberately not used here.
        summary = (content.get("summary") or "").strip()
        if len(summary) > 320:
            summary = summary[:317].rstrip() + "…"
        items.append(
            NewsItem(
                title=content.get("title") or "Sin título",
                url=url or entry.get("link") or "#",
                date=(content.get("pubDate") or "")[:10],
                summary=summary,
            )
        )
    return items


def _value_position(position: Position, price: float) -> PositionSnapshot:
    current_value = position.shares * price
    pnl = current_value - position.invested
    return PositionSnapshot(
        shares=position.shares,
        avg_cost=position.avg_cost,
        invested=position.invested,
        current_value=current_value,
        pnl=pnl,
        pnl_pct=pnl / position.invested * 100 if position.invested else 0.0,
        to_breakeven=(position.avg_cost - price) / price * 100,
    )


def analyze_ticker(item: WatchlistItem) -> AnalysisResult:
    """Download one year of history for a ticker and analyze it."""
    ticker = item.ticker
    stock = yf.Ticker(ticker)

    try:
        history = stock.history(period="1y")
    except Exception as exc:  # network, rate limit, upstream schema change
        raise TickerDataError(f"No se pudieron descargar datos: {exc}") from exc

    # Yahoo emits a row for the session in progress with a Volume but a NaN
    # Close. Left in, it poisons every rolling window and the last price
    # itself, so the whole report comes out as NaN.
    history = history.dropna(subset=["Close"])

    if history.empty or len(history) < 2:
        raise TickerDataError("Yahoo Finance no devolvió histórico para este ticker")

    closes = history["Close"].squeeze()
    volumes = history["Volume"].squeeze()
    price = float(closes.iloc[-1])
    previous = float(closes.iloc[-2])

    indicators, bull, bear, series = _build_indicators(closes, volumes, price)

    if bull > bear + 1:
        verdict = "ALCISTA"
    elif bear > bull + 1:
        verdict = "BAJISTA"
    else:
        verdict = "NEUTRAL"

    try:
        info = stock.info or {}
    except Exception:
        info = {}

    try:
        news = _build_news(stock.news or [])
    except Exception:
        news = []

    indices = _sample_indices(len(closes))

    return AnalysisResult(
        ticker=ticker,
        price=price,
        change_pct=(price - previous) / previous * 100 if previous else 0.0,
        indicators=indicators,
        fundamentals=_build_fundamentals(info, ticker, price),
        news=news,
        position=_value_position(item.position, price) if item.position else None,
        bull_score=bull,
        bear_score=bear,
        verdict=verdict,
        price_series=_downsample(closes),
        bb_upper_series=_downsample_at(series["bb_upper"], indices),
        bb_lower_series=_downsample_at(series["bb_lower"], indices),
        sma20_series=_downsample_at(series["sma20"], indices),
        sma50_series=_downsample_at(series["sma50"], indices),
        volume_series=_downsample_at(volumes, indices),
    )


def _summarize_portfolio(results: list[AnalysisResult]) -> PortfolioSummary | None:
    invested = sum(r.position.invested for r in results if r.position)
    if not invested:
        return None
    current = sum(r.position.current_value for r in results if r.position)
    pnl = current - invested
    return PortfolioSummary(
        invested=invested,
        current_value=current,
        pnl=pnl,
        pnl_pct=pnl / invested * 100,
    )


def run_analysis(items: list[WatchlistItem]) -> AnalysisRun:
    """Analyze the whole watchlist, fetching tickers concurrently.

    yfinance blocks on network I/O, so a thread pool turns a sequential wait
    into a near-constant one. Watchlist order is preserved in the output.
    """
    results: list[AnalysisResult] = []
    failures: list[FailedTicker] = []

    if items:
        workers = min(MAX_FETCH_WORKERS, len(items))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [(item, pool.submit(analyze_ticker, item)) for item in items]
            for item, future in futures:
                try:
                    results.append(future.result())
                except TickerDataError as exc:
                    failures.append(FailedTicker(ticker=item.ticker, reason=str(exc)))
                except Exception as exc:
                    failures.append(
                        FailedTicker(ticker=item.ticker, reason=f"Error inesperado: {exc}")
                    )

    return AnalysisRun(
        generated_at=datetime.now().isoformat(timespec="seconds"),
        results=results,
        failures=failures,
        portfolio=_summarize_portfolio(results),
    )
