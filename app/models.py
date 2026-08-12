"""Typed models for everything that crosses the HTTP boundary or hits disk."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class Position(BaseModel):
    """A holding in a ticker.

    Size is given either as a dollar amount (`invested`) or a share count
    (`shares`); the other one is derived from `avg_cost`.
    """

    avg_cost: float = Field(gt=0)
    invested: float | None = Field(default=None, gt=0)
    shares: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def derive_missing_size(self) -> Position:
        if self.shares is None and self.invested is None:
            raise ValueError("A position needs either 'invested' or 'shares'")
        # `shares` wins when both are present, matching the original script.
        if self.shares is not None:
            self.invested = self.shares * self.avg_cost
        else:
            self.shares = self.invested / self.avg_cost
        return self


class WatchlistItem(BaseModel):
    ticker: str
    position: Position | None = None

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, v: str) -> str:
        ticker = v.strip().upper()
        if not ticker:
            raise ValueError("Ticker cannot be empty")
        return ticker


class Watchlist(BaseModel):
    watchlist: list[WatchlistItem] = Field(default_factory=list)


class LLMSettings(BaseModel):
    provider: Literal["anthropic", "openai", "openrouter"] = "anthropic"
    model: str = "openai/gpt-5.6-luna"
    api_key: str = ""


class PositionSnapshot(BaseModel):
    """A position valued against the current market price."""

    shares: float
    avg_cost: float
    invested: float
    current_value: float
    pnl: float
    pnl_pct: float
    # Percent the price must still move to reach break-even. Negative once
    # the position is profitable.
    to_breakeven: float


class Fundamentals(BaseModel):
    company: str
    sector: str = "N/A"
    industry: str = "N/A"
    market_cap: float | None = None
    pe: float | None = None
    forward_pe: float | None = None
    revenue: float | None = None
    revenue_growth: float | None = None
    gross_margin: float | None = None
    eps: float | None = None
    forward_eps: float | None = None
    beta: float | None = None
    target_price: float | None = None
    recommendation: str = "N/A"
    week52_high: float | None = None
    week52_low: float | None = None
    dist_from_high: float | None = None
    dist_from_low: float | None = None


class NewsItem(BaseModel):
    title: str
    url: str = "#"
    date: str = ""
    # Plain-text blurb from the provider. Empty when the entry has none, or
    # when the run predates this field — cached runs stay loadable.
    summary: str = ""


class Indicators(BaseModel):
    """Latest indicator readings.

    Numeric fields are optional: rolling windows return no value until they
    have enough history, so a recently listed ticker legitimately has no
    SMA200. `None` means "not enough data", never zero.
    """

    rsi: float | None = None
    rsi_signal: str
    macd: float | None = None
    macd_signal_line: float | None = None
    macd_signal: str
    bb_upper: float | None = None
    bb_lower: float | None = None
    bb_signal: str
    sma20: float | None = None
    sma50: float | None = None
    sma200: float | None = None
    above_sma20: bool | None = None
    above_sma50: bool | None = None
    above_sma200: bool | None = None
    volume_ratio: float = 1.0


class AnalysisResult(BaseModel):
    ticker: str
    price: float
    change_pct: float
    indicators: Indicators
    fundamentals: Fundamentals
    news: list[NewsItem] = Field(default_factory=list)
    position: PositionSnapshot | None = None
    # Weighted signal tally. `verdict` is derived from the two.
    bull_score: float
    bear_score: float
    verdict: Literal["ALCISTA", "BAJISTA", "NEUTRAL"]
    # Downsampled 1y close series, feeds the sparkline in the UI.
    price_series: list[float] = Field(default_factory=list)


class FailedTicker(BaseModel):
    ticker: str
    reason: str


class PortfolioSummary(BaseModel):
    invested: float
    current_value: float
    pnl: float
    pnl_pct: float


class AnalysisRun(BaseModel):
    """One full pass over the watchlist, as cached on disk."""

    generated_at: str
    results: list[AnalysisResult] = Field(default_factory=list)
    failures: list[FailedTicker] = Field(default_factory=list)
    portfolio: PortfolioSummary | None = None
    llm_analysis: str | None = None
