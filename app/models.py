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
    # Who last wrote this item's position. Only the XTB import sets "xtb"; it
    # is what lets a later import tell "the user typed this" apart from "a
    # previous import wrote this and the holding is now gone".
    #
    # This field must stay optional. `load_watchlist` returns an *empty*
    # Watchlist on any ValidationError, so a required field here would wipe
    # every real position the first time the app booted on an existing
    # config file — the same hazard AnalysisResult documents below, but
    # silent and total.
    source: Literal["manual", "xtb"] = "manual"
    # Paused tickers stay in the watchlist — with their position intact — but
    # are skipped by the analysis run. It is the non-destructive way to shrink
    # a run down to the tickers being studied right now.
    #
    # Defaulted for the same reason as `source`: a required field here would
    # make every pre-existing config file fail validation, and `load_watchlist`
    # answers a ValidationError with an empty watchlist.
    active: bool = True

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
    provider: Literal["anthropic", "openai", "openrouter"] = "openrouter"
    model: str = "openai/gpt-latest"
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
    # Downsampled companions to price_series, sampled at the same indices so
    # every layer lines up on the same x-grid. `None` marks a rolling-window
    # warm-up period (e.g. the first 49 points have no SMA50) — never zero.
    # All default to an empty list: a required field here would silently
    # invalidate the JSON cache via `load_last_run`'s ValidationError guard.
    bb_upper_series: list[float | None] = Field(default_factory=list)
    bb_lower_series: list[float | None] = Field(default_factory=list)
    sma20_series: list[float | None] = Field(default_factory=list)
    sma50_series: list[float | None] = Field(default_factory=list)
    volume_series: list[float | None] = Field(default_factory=list)


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


# ── XTB broker import ────────────────────────────────────────────────────────
#
# Everything below models an XTB account statement export. The broker's own
# vocabulary is kept (instrument, volume, position) rather than translated into
# the watchlist's, so a mismatch between what the report says and what we
# derived from it stays visible instead of being papered over at parse time.

CashBucket = Literal[
    "purchase", "sell", "deposit", "withdrawal", "dividend", "tax", "transfer", "other"
]


class XtbLot(BaseModel):
    """One individual position row — a single fill, not a whole holding.

    Several lots can sit under one instrument. They matter for two reasons:
    they carry the position IDs, and they are the only rows that report a
    current price (the aggregate row above them leaves that column blank).
    """

    position_id: str = ""
    side: str = "BUY"
    volume: float = 0.0
    open_price: float = 0.0
    current_price: float | None = None
    value: float = 0.0
    net_profit: float | None = None
    opened_at: str | None = None


class XtbOpenPosition(BaseModel):
    """One instrument the account still holds, folded from its report rows."""

    xtb_symbol: str  # as the broker writes it, e.g. "CRWV.US"
    yahoo_symbol: str = ""  # mapped for yfinance; "" when unmappable
    instrument: str = ""  # human name, e.g. "CoreWeave"
    asset_class: str = ""  # the report's Category column: STOCK or ETF
    product: str = ""
    volume: float = 0.0
    open_price: float = 0.0
    current_price: float | None = None
    value: float = 0.0
    net_profit: float | None = None
    net_profit_pct: float | None = None
    lots: list[XtbLot] = Field(default_factory=list)
    # Line of business, resolved after parsing. The report's own Category
    # column is asset class (STOCK/ETF), which does not answer "what kind of
    # business is this". None means "not looked up yet", not "unknown".
    sector: str | None = None

    @property
    def is_short(self) -> bool:
        """True when every lot is a sell.

        Shorts are excluded from the allocation ring and from the watchlist
        sync: negative exposure has no honest share of a 100% donut, and the
        watchlist's P&L maths assumes a long.
        """
        return bool(self.lots) and all(lot.side.upper() == "SELL" for lot in self.lots)


class XtbClosedPosition(BaseModel):
    """A round trip the account has already finished."""

    xtb_symbol: str
    instrument: str = ""
    asset_class: str = ""
    side: str = "BUY"
    volume: float = 0.0
    open_price: float = 0.0
    close_price: float = 0.0
    opened_at: str | None = None
    closed_at: str | None = None
    profit_loss: float = 0.0
    purchase_value: float | None = None
    sale_value: float | None = None
    commission: float = 0.0
    position_id: str = ""


class XtbCashOperation(BaseModel):
    """One line of the cash ledger.

    `type` keeps the broker's own label verbatim; `bucket` is our normalised
    reading of it. Both are stored so an unrecognised label stays inspectable
    instead of vanishing into "other".
    """

    type: str
    bucket: CashBucket = "other"
    xtb_symbol: str = ""
    asset_class: str = ""
    amount: float = 0.0
    at: str | None = None
    comment: str = ""
    position_id: str = ""


class XtbReportedTotals(BaseModel):
    """The report's own summary and footer figures.

    Never used as data. They exist so `build_metrics` can check its arithmetic
    against numbers the broker computed independently — which is the only
    outside check we have that the nested open-positions rows were folded
    correctly and the footer rows were skipped.
    """

    open_value: float | None = None
    open_profit: float | None = None
    realized_pnl: float | None = None
    cash_balance: float | None = None


class XtbSnapshot(BaseModel):
    """One parsed XTB export, as cached on disk.

    Every field is defaulted so an older snapshot keeps loading after this
    model grows — same reasoning as AnalysisResult's series fields.
    """

    imported_at: str
    source_file: str = ""
    account: str = ""
    currency: str = "USD"
    generated_at: str | None = None
    open_positions: list[XtbOpenPosition] = Field(default_factory=list)
    closed_positions: list[XtbClosedPosition] = Field(default_factory=list)
    cash_operations: list[XtbCashOperation] = Field(default_factory=list)
    reported: XtbReportedTotals = Field(default_factory=XtbReportedTotals)
    # Things worth telling the user that are not errors: an unmapped symbol, an
    # unrecognised cash-operation type, a non-USD account.
    warnings: list[str] = Field(default_factory=list)


class XtbMetrics(BaseModel):
    """Headline account figures derived from a snapshot."""

    currency: str = "USD"
    open_value: float = 0.0
    open_cost: float = 0.0
    unrealized_pnl: float = 0.0
    unrealized_pnl_pct: float = 0.0
    realized_pnl: float = 0.0
    deposits: float = 0.0
    withdrawals: float = 0.0
    net_deposits: float = 0.0
    dividends: float = 0.0
    withholding_tax: float = 0.0
    cash_balance: float = 0.0
    # What the account is worth versus what was put into it. The only figure
    # here that answers "did this make money", as opposed to "is this position
    # up".
    total_return: float = 0.0
    total_return_pct: float = 0.0
    holdings_count: int = 0
    top_holding: str = ""
    top_holding_share: float = 0.0
    # Populated when our arithmetic disagrees with the report's own totals.
    # Surfaced in the UI rather than raised: a mismatch means the numbers need
    # a second look, not that the import failed.
    discrepancies: list[str] = Field(default_factory=list)


class XtbRealized(BaseModel):
    """Closed-trade record for one instrument."""

    symbol: str
    instrument: str = ""
    realized: float = 0.0
    trades: int = 0
    wins: int = 0
    avg_holding_days: float | None = None

    @property
    def win_rate(self) -> float:
        return (self.wins / self.trades * 100.0) if self.trades else 0.0


class XtbCapitalPoint(BaseModel):
    """One day on the capital curve.

    Every series here is derived from the cash ledger alone, so all three are
    exact. Market value over time is deliberately absent: the export carries no
    historical valuations, and inventing them would make the chart a guess.
    """

    date: str
    net_deposits: float = 0.0
    invested: float = 0.0  # cumulative purchases net of sales, at cost
    realized_pnl: float = 0.0


class Allocation(BaseModel):
    """One slice of the portfolio, before it becomes geometry."""

    label: str
    value: float
    # Which holdings ended up in this bucket, largest first. Empty when the
    # label already names one holding, as it does in the by-ticker view —
    # repeating it there would be noise, not information.
    members: list[str] = Field(default_factory=list)
