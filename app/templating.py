"""Jinja2 environment and the display filters the templates rely on.

These replace the string-formatting helpers that used to live inside
analyze_stocks.py's build_html().

The numeric filters return `Markup` because units ($, %, ×, B/M/T) are
rendered in a muted `<span class="u">` rather than baked into the number, the
way a real instrument screen-prints its units next to the readout. Everything
they interpolate is a float they formatted themselves, so nothing
user-controlled reaches the output unescaped; the one exception is the
caller-supplied `suffix` of `num`, which is escaped explicitly.
"""

from __future__ import annotations

import re

from fastapi.templating import Jinja2Templates
from markupsafe import Markup, escape

from app.analysis.dial import build_dial
from app.analysis.sparkline import build_sparkline
from app.config import TEMPLATES_DIR
from app.glossary import GLOSSARY
from app.markdown import render_analysis

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

MINUS = "−"  # U+2212, not a hyphen: it aligns with digits in tabular figures
DASH = "—"  # shown when a value is missing

_UNSAFE_IDENT = re.compile(r"[^a-zA-Z0-9]+")


def _unit(text: str) -> str:
    return f'<span class="u">{text}</span>'


def slug(value: str | None) -> str:
    """Reduce a string to a token safe inside an id or a CSS custom ident.

    Tickers like `BRK.B` would otherwise produce an invalid `anchor-name`.
    """
    cleaned = _UNSAFE_IDENT.sub("-", str(value or "")).strip("-").lower()
    return cleaned or "x"


def money(value: float | None, decimals: int = 2) -> Markup:
    """Format a dollar amount, abbreviating large magnitudes."""
    if value is None:
        return Markup(DASH)
    sign = MINUS if value < 0 else ""
    magnitude = abs(value)
    for threshold, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M")):
        if magnitude >= threshold:
            return Markup(
                f"{sign}{_unit('$')}{magnitude / threshold:,.2f}{_unit(suffix)}"
            )
    return Markup(f"{sign}{_unit('$')}{magnitude:,.{decimals}f}")


def money_text(value: float | None, decimals: int = 2) -> str:
    """Plain-text dollar formatting for contexts `money`'s `<span>` unit
    markup can't reach — SVG `<text>` isn't an HTML integration point, so an
    embedded `<span>` there is inert markup, not a styled unit.
    """
    if value is None:
        return DASH
    sign = MINUS if value < 0 else ""
    return f"{sign}${abs(value):,.{decimals}f}"


def num(value: float | None, decimals: int = 2, suffix: str = "") -> Markup:
    if value is None:
        return Markup(DASH)
    sign = MINUS if value < 0 else ""
    tail = _unit(str(escape(suffix))) if suffix else ""
    return Markup(f"{sign}{abs(value):,.{decimals}f}{tail}")


def pct(value: float | None, decimals: int = 2, signed: bool = False) -> Markup:
    """Format a value already expressed in percentage points."""
    if value is None:
        return Markup(DASH)
    if signed:
        sign = "+" if value >= 0 else MINUS
    else:
        sign = MINUS if value < 0 else ""
    return Markup(f"{sign}{abs(value):,.{decimals}f}{_unit('%')}")


def ratio_pct(value: float | None, decimals: int = 1) -> Markup:
    """Format a 0–1 ratio as a percentage."""
    if value is None:
        return Markup(DASH)
    sign = MINUS if value < 0 else ""
    return Markup(f"{sign}{abs(value) * 100:,.{decimals}f}{_unit('%')}")


def signed_money(value: float | None, decimals: int = 2) -> Markup:
    if value is None:
        return Markup(DASH)
    sign = "+" if value >= 0 else MINUS
    return Markup(f"{sign}{_unit('$')}{abs(value):,.{decimals}f}")


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


def direction_word(value: float | None) -> str:
    """The direction spelled out, so colour is never the only carrier."""
    if value is None or value == 0:
        return "sin cambio"
    return "sube" if value > 0 else "baja"


templates.env.filters.update(
    money=money,
    money_text=money_text,
    num=num,
    pct=pct,
    ratio_pct=ratio_pct,
    signed_money=signed_money,
    recommendation=recommendation,
    direction=direction,
    direction_word=direction_word,
    slug=slug,
)

templates.env.globals.update(
    glossary=GLOSSARY,
    build_dial=build_dial,
    build_sparkline=build_sparkline,
    render_analysis=render_analysis,
)
