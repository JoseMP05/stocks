# Análisis de Acciones

App web local para analizar una watchlist de acciones: indicadores técnicos (RSI, MACD, Bandas de Bollinger, SMA), fundamentals, noticias, seguimiento de posición personal (P&L) e interpretación opcional por IA.

## Requisitos

- Python 3.11+
- Una API key de Anthropic, OpenAI u OpenRouter (opcional — solo si vas a usar "Interpretar con IA")

## Instalación

```bash
python -m venv venv

# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
```

## Arranque

```bash
uvicorn app.main:app --reload --port 8420
```

Abrí `http://127.0.0.1:8420` en el navegador.

## Configuración de la watchlist

Se administra desde la propia UI (agregar/editar/borrar tickers y posición). Los datos quedan en `data/stocks_config.json` (gitignored, contiene precios de compra reales). `data/stocks_config.example.json` es la plantilla versionada.

## Interpretación con IA (opcional)

Desde el ⚙ de la UI configurás proveedor, modelo y API key:

- **Anthropic** — modelo sin prefijo (ej. `claude-sonnet-5`)
- **OpenAI** — modelo sin prefijo (ej. `gpt-4o`)
- **OpenRouter** — modelo con el prefijo del proveedor real (ej. `openai/gpt-4o`, `anthropic/claude-sonnet-5`)

La API key se puede setear también por variable de entorno (tiene prioridad sobre la guardada en la UI). Copiá `.env.example` a `.env` si preferís este camino:

```env
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
OPENROUTER_API_KEY=
```

El botón "Interpretar con IA" corre un único análisis sobre todo el portafolio cargado (no reanaliza precios, usa el último resultado cacheado).

## Estructura

```text
app/
├── main.py                # rutas FastAPI
├── analysis/               # indicadores + fetch de mercado (yfinance)
├── llm/                     # providers Anthropic / OpenAI / OpenRouter
├── templates/               # Jinja2 + partials HTMX
└── static/                  # css/js
data/                        # watchlist, settings y cache — todo gitignored salvo el .example
```

## To Do

- Integrar importación de acciones e historial desde XTB
- Pie chart de acciones
- Boton para desactivar ciertas acciones sin tener que removerlas
- Añadir bandas de bollinger y volumen al grafico
- Dockerizar proyecto
