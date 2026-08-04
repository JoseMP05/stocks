"""Technical indicators.

Ported unchanged from the original analyze_stocks.py so the numbers the web
app reports stay identical to the ones the script produced.
"""

import numpy as np
import pandas as pd


def calc_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    delta = prices.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def calc_macd(
    prices: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[pd.Series, pd.Series, pd.Series]:
    ema_fast = prices.ewm(span=fast, adjust=False).mean()
    ema_slow = prices.ewm(span=slow, adjust=False).mean()
    macd = ema_fast - ema_slow
    signal_line = macd.ewm(span=signal, adjust=False).mean()
    return macd, signal_line, macd - signal_line


def calc_bollinger(
    prices: pd.Series, period: int = 20, n_std: int = 2
) -> tuple[pd.Series, pd.Series, pd.Series]:
    sma = prices.rolling(period).mean()
    std = prices.rolling(period).std()
    return sma + n_std * std, sma, sma - n_std * std
