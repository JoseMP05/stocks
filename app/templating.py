"""Jinja2 environment and the display filters the templates rely on.

These replace the string-formatting helpers that used to live inside
analyze_stocks.py's build_html().
"""

from __future__ import annotations

from fastapi.templating import Jinja2Templates

from app.config import TEMPLATES_DIR

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def money(value: float | None, decimals: int = 2) -> str:
    """Format a dollar amount, abbreviating large magnitudes."""
    if value is None:
        return "—"
    magnitude = abs(value)
    for threshold, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M")):
        if magnitude >= threshold:
            return f"${value / threshold:,.2f}{suffix}"
    return f"${value:,.{decimals}f}"


def num(value: float | None, decimals: int = 2, suffix: str = "") -> str:
    if value is None:
        return "—"
    return f"{value:,.{decimals}f}{suffix}"


def pct(value: float | None, decimals: int = 2, signed: bool = False) -> str:
    """Format a value already expressed in percentage points."""
    if value is None:
        return "—"
    sign = "+" if signed and value >= 0 else ""
    return f"{sign}{value:,.{decimals}f}%"


def ratio_pct(value: float | None, decimals: int = 1) -> str:
    """Format a 0–1 ratio as a percentage."""
    if value is None:
        return "—"
    return f"{value * 100:,.{decimals}f}%"


def signed_money(value: float | None, decimals: int = 2) -> str:
    if value is None:
        return "—"
    sign = "+" if value >= 0 else "−"
    return f"{sign}${abs(value):,.{decimals}f}"


def recommendation(key: str) -> str:
    labels = {
        "buy": "Comprar",
        "strong_buy": "Compra fuerte",
        "hold": "Mantener",
        "sell": "Vender",
        "strong_sell": "Venta fuerte",
        "underperform": "Rendimiento inferior",
        "outperform": "Rendimiento superior",
    }
    return labels.get(str(key).lower(), str(key).replace("_", " ").capitalize())


def direction(value: float | None) -> str:
    """Map a number to a CSS state class: up, down or flat."""
    if value is None:
        return "flat"
    if value > 0:
        return "up"
    if value < 0:
        return "down"
    return "flat"


templates.env.filters.update(
    money=money,
    num=num,
    pct=pct,
    ratio_pct=ratio_pct,
    signed_money=signed_money,
    recommendation=recommendation,
    direction=direction,
)
