"""FastAPI application: routes and HTMX partial rendering."""

from __future__ import annotations

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from app import storage
from app.analysis.market import run_analysis
from app.config import STATIC_DIR
from app.llm import get_provider
from app.llm.errors import LLMError
from app.llm.prompt import build_prompt
from app.models import LLMSettings, Position, WatchlistItem
from app.templating import templates

app = FastAPI(title="Análisis de Acciones")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def _parse_position(
    avg_cost: str | None, invested: str | None, shares: str | None
) -> Position | None:
    """Build a Position from raw form fields, or None when left blank."""
    if not avg_cost or not avg_cost.strip():
        return None
    try:
        return Position(
            avg_cost=float(avg_cost),
            invested=float(invested) if invested and invested.strip() else None,
            shares=float(shares) if shares and shares.strip() else None,
        )
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=422, detail=f"Posición inválida: {exc}") from exc


def _watchlist_response(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="partials/watchlist.html",
        context={"watchlist": storage.load_watchlist().watchlist},
    )


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "watchlist": storage.load_watchlist().watchlist,
            "run": storage.load_last_run(),
            "settings": storage.load_settings(),
        },
    )


# ── watchlist ────────────────────────────────────────────────────────────────

@app.post("/watchlist", response_class=HTMLResponse)
def create_ticker(
    request: Request,
    ticker: str = Form(...),
    avg_cost: str = Form(default=""),
    invested: str = Form(default=""),
    shares: str = Form(default=""),
) -> HTMLResponse:
    try:
        item = WatchlistItem(
            ticker=ticker, position=_parse_position(avg_cost, invested, shares)
        )
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=f"Ticker inválido: {exc}") from exc
    storage.add_ticker(item)
    return _watchlist_response(request)


@app.post("/watchlist/{ticker}", response_class=HTMLResponse)
def edit_ticker(
    request: Request,
    ticker: str,
    avg_cost: str = Form(default=""),
    invested: str = Form(default=""),
    shares: str = Form(default=""),
) -> HTMLResponse:
    item = WatchlistItem(
        ticker=ticker, position=_parse_position(avg_cost, invested, shares)
    )
    storage.update_ticker(ticker, item)
    return _watchlist_response(request)


@app.delete("/watchlist/{ticker}", response_class=HTMLResponse)
def delete_ticker(request: Request, ticker: str) -> HTMLResponse:
    storage.remove_ticker(ticker)
    return _watchlist_response(request)


# ── analysis ─────────────────────────────────────────────────────────────────

@app.post("/analyze", response_class=HTMLResponse)
def analyze(request: Request) -> HTMLResponse:
    """Run the full analysis.

    Declared `def` rather than `async def` on purpose: yfinance blocks on
    network I/O, so FastAPI runs this in its threadpool instead of stalling
    the event loop and freezing every other request.
    """
    watchlist = storage.load_watchlist().watchlist
    run = run_analysis(watchlist)
    storage.save_last_run(run)
    return templates.TemplateResponse(
        request=request, name="partials/results.html", context={"run": run}
    )


# ── LLM interpretation ───────────────────────────────────────────────────────

@app.post("/analyze/llm", response_class=HTMLResponse)
def analyze_llm(request: Request) -> HTMLResponse:
    """Interpret the last cached analysis run with the configured LLM.

    Declared `def` rather than `async def`: the provider SDKs block on
    network I/O, same reasoning as `/analyze` with yfinance.
    """
    run = storage.load_last_run()
    if run is None or not run.results:
        raise HTTPException(status_code=400, detail="Corré un análisis antes de interpretarlo con IA.")

    settings = storage.load_settings()
    provider = get_provider(settings)
    try:
        analysis = provider.analyze(build_prompt(run))
    except LLMError as exc:
        return templates.TemplateResponse(
            request=request,
            name="partials/llm_panel.html",
            context={"analysis": None, "error": str(exc)},
        )

    run.llm_analysis = analysis
    storage.save_last_run(run)
    return templates.TemplateResponse(
        request=request,
        name="partials/llm_panel.html",
        context={"analysis": analysis, "error": None},
    )


# ── settings ─────────────────────────────────────────────────────────────────

@app.get("/settings", response_class=HTMLResponse)
def get_settings(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="partials/settings.html",
        context={"settings": storage.load_settings(), "saved": False},
    )


@app.post("/settings", response_class=HTMLResponse)
def save_settings(
    request: Request,
    provider: str = Form(...),
    model: str = Form(...),
    api_key: str = Form(default=""),
) -> HTMLResponse:
    current = storage.load_settings()
    # Blank key in the form means "keep the one already saved" — the field
    # is rendered masked, so an empty submit must not wipe it.
    resolved_key = api_key.strip() or current.api_key
    try:
        settings = LLMSettings(provider=provider, model=model, api_key=resolved_key)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=f"Configuración inválida: {exc}") from exc
    storage.save_settings(settings)
    return templates.TemplateResponse(
        request=request,
        name="partials/settings.html",
        context={"settings": settings, "saved": True},
    )
