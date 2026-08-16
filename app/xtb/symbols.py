"""XTB instrument symbols to yfinance symbols.

XTB namespaces instruments by venue suffix; Yahoo uses its own conventions.
The translation is best-effort by design. A symbol we get wrong has to degrade
to "no sector, no technical analysis" while the holding stays visible in the
portfolio — never to a crashed import, and never to a silently wrong ticker.
"""

from __future__ import annotations

# Venue suffix translation. US instruments drop the suffix entirely; everywhere
# else Yahoo has its own.
XTB_SUFFIX_TO_YAHOO: dict[str, str] = {
    "US": "",
    "UK": ".L",
    "NL": ".AS",
    "DE": ".DE",
    "ES": ".MC",
    "FR": ".PA",
    "IT": ".MI",
    "CH": ".SW",
    "PT": ".LS",
    "BE": ".BR",
    "NO": ".OL",
    "SE": ".ST",
    "DK": ".CO",
    "FI": ".HE",
    "CZ": ".PR",
    "HU": ".BD",
}

# XTB appends a digit when a base symbol is already taken on its own book, so
# stripping the suffix is not always enough. Verified case: TE1.US is T1 Energy,
# which trades on Nasdaq as TE — "TE1" resolves to nothing at all.
SYMBOL_OVERRIDES: dict[str, str] = {
    "TE1.US": "TE",
}


def to_yahoo(xtb_symbol: str) -> str:
    """Translate a broker symbol. Returns "" only for empty input.

    An unknown suffix is handed back untouched rather than guessed at. Yahoo
    failing on a symbol we passed through is recoverable and shows up in the
    failure list; a symbol we quietly mangled looks like real data and does not.
    """
    symbol = (xtb_symbol or "").strip().upper()
    if not symbol:
        return ""

    override = SYMBOL_OVERRIDES.get(symbol)
    if override is not None:
        return override

    base, _, suffix = symbol.rpartition(".")
    if not base:  # no dot at all — already bare
        return symbol

    mapped = XTB_SUFFIX_TO_YAHOO.get(suffix)
    if mapped is None:
        return symbol
    return f"{base}{mapped}"
