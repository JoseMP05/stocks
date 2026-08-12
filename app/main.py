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


class PositionInputError(ValueError):
    """A position the user typed that we can't make sense of.

    Carries a message meant to be read by the person who typed it, not a
    validator dump. Raised instead of HTTPException because htmx discards the
    body of a 4xx: the message has to come back inside a 200 to be seen.
    """


def _blank(value: str | None) -> bool:
    return not value or not value.strip()


def _parse_position(
    avg_cost: str | None, invested: str | None, shares: str | None
) -> Position | None:
    """Build a Position from raw form fields, or None when left blank."""
    if _blank(avg_cost):
        # Size without a purchase price cannot be valued. Saying so beats
        # silently dropping what they typed.
        if not (_blank(invested) and _blank(shares)):
            raise PositionInputError(
                "Falta el precio promedio de compra para poder calcular la posición."
            )
        return None
    if _blank(invested) and _blank(shares):
        raise PositionInputError(
            "Indicá también el monto invertido o la cantidad de acciones: "
            "con el precio de compra solo no se puede calcular la posición."
        )
    try:
        return Position(
            avg_cost=float(avg_cost),
            invested=float(invested) if not _blank(invested) else None,
            shares=float(shares) if not _blank(shares) else None,
        )
    except (ValueError, ValidationError) as exc:
        raise PositionInputError(
            "Revisá los números de la posición: tienen que ser mayores a cero."
        ) from exc


def _watchlist_response(request: Request, error: str | None = None) -> HTMLResponse:
    """Render the watchlist, plus an out-of-band slot carrying any error.

    Always a 200: htmx does not swap 4xx responses, so an error returned as a
    status code disappears without a trace — which is exactly how the add form
    used to fail silently.
    """
    return templates.TemplateResponse(
        request=request,
        name="partials/watchlist_response.html",
        context={"watchlist": storage.load_watchlist().watchlist, "error": error},
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
    except PositionInputError as exc:
        return _watchlist_response(request, error=str(exc))
    except ValidationError:
        return _watchlist_response(request, error="Escribí un ticker válido, por ejemplo AAPL.")

    if any(w.ticker == item.ticker for w in storage.load_watchlist().watchlist):
        # add_ticker replaces, which would silently wipe an existing position.
        return _watchlist_response(
            request,
            error=f"{item.ticker} ya está en la watchlist. Editá su posición desde la tarjeta.",
        )
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
    try:
        item = WatchlistItem(
            ticker=ticker, position=_parse_position(avg_cost, invested, shares)
        )
    except PositionInputError as exc:
        return _watchlist_response(request, error=f"{ticker.upper()}: {exc}")
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
            context={"analysis": None, "error": str(exc), "results": run.results},
        )

    run.llm_analysis = analysis
    storage.save_last_run(run)
    return templates.TemplateResponse(
        request=request,
        name="partials/llm_panel.html",
        context={"analysis": analysis, "error": None, "results": run.results},
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
