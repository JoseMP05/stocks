"""Render the model's Markdown answer into safe, navigable HTML.

The answer is long-form and highly structured — one top-level section per
ticker — so rendering also extracts an outline the UI turns into a jump index.

Model output is untrusted text. `html=False` makes markdown-it escape any raw
HTML rather than pass it through, and markdown-it's default link validator
already rejects `javascript:`, `vbscript:` and `file:` URLs, so no separate
sanitiser is needed.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from markdown_it import MarkdownIt

# The panel's own <h2> owns level 2, so every heading the model emits is
# pushed down one level to keep the document outline legal.
HEADING_SHIFT = 1
MAX_HEADING_LEVEL = 6


@dataclass(frozen=True)
class Section:
    """One top-level section of the answer, for the jump index."""

    title: str
    anchor: str
    # Set when the heading names a ticker we actually track, which lets the
    # index show that ticker's reading beside the link.
    ticker: str | None = None


@dataclass(frozen=True)
class RenderedAnalysis:
    html: str = ""
    sections: list[Section] = field(default_factory=list)


def _slug(text: str, taken: set[str]) -> str:
    """A stable, unique, CSS-safe anchor for a heading."""
    normalized = unicodedata.normalize("NFKD", text)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    base = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_only).strip("-").lower()
    # Namespaced so these can never collide with the glossary popover ids.
    base = f"llm-{base or 'seccion'}"
    anchor, n = base, 2
    while anchor in taken:
        anchor, n = f"{base}-{n}", n + 1
    taken.add(anchor)
    return anchor


def _find_ticker(title: str, tickers: set[str]) -> str | None:
    """Match a heading like `## 3. GOOGL — Alphabet` to a tracked ticker.

    Word-boundary matching only, so `NU` does not match inside `NUEVO`. Returns
    None when nothing matches, which is the normal case for the summary and
    conclusion sections.
    """
    for candidate in sorted(tickers, key=len, reverse=True):
        if re.search(rf"(?<![A-Za-z0-9.]){re.escape(candidate)}(?![A-Za-z0-9])", title):
            return candidate
    return None


def _build_parser() -> MarkdownIt:
    md = MarkdownIt("commonmark", {"html": False, "linkify": False})
    # Models reach for these two often enough to be worth enabling; everything
    # else stays at CommonMark.
    md.enable("table")
    md.enable("strikethrough")
    return md


def render_analysis(text: str | None, tickers: set[str] | None = None) -> RenderedAnalysis:
    """Render Markdown to HTML and extract the top-level outline."""
    if not text or not text.strip():
        return RenderedAnalysis()

    md = _build_parser()
    tokens = md.parse(text)

    levels = [int(t.tag[1]) for t in tokens if t.type == "heading_open"]
    # The outline follows whichever level the answer uses as its top heading,
    # so it works whether the model starts at `#` or `##`.
    top_level = min(levels) if levels else 0

    sections: list[Section] = []
    taken: set[str] = set()
    known = {t.upper() for t in (tickers or set())}

    for index, token in enumerate(tokens):
        if token.type != "heading_open":
            continue
        original = int(token.tag[1])
        shifted = min(original + HEADING_SHIFT, MAX_HEADING_LEVEL)
        token.tag = f"h{shifted}"
        # heading_open is always followed by its inline content, then the close.
        title = tokens[index + 1].content.strip()
        anchor = _slug(title, taken)
        token.attrSet("id", anchor)
        token.attrSet("tabindex", "-1")
        tokens[index + 2].tag = f"h{shifted}"

        if original == top_level:
            sections.append(
                Section(title=title, anchor=anchor, ticker=_find_ticker(title, known))
            )

    html = md.renderer.render(tokens, md.options, {})
    return RenderedAnalysis(html=html, sections=sections)
