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

## Docker

Con `docker compose` (recomendado — crea el volumen de datos automáticamente):

```bash
docker compose up -d
```

O corriendo la imagen publicada en Docker Hub directamente:

```bash
docker run -d --name analisis \
  -p 8420:8420 \
  -v analisis-data:/app/data \
  -e OPENROUTER_API_KEY=sk-or-... \
  <dockerhub-user>/stocks:latest
```

Abrí `http://127.0.0.1:8420`. La watchlist arranca vacía — se carga desde la propia UI, igual que en instalación local. Los datos (`data/`) persisten en el volumen `analisis-data` entre reinicios y actualizaciones de la imagen.

La API key también se puede pasar por variable de entorno (`-e OPENROUTER_API_KEY=...`, o `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` según el proveedor elegido en el ⚙) — tiene prioridad sobre la guardada desde la UI.

## Configuración de la watchlist

Se administra desde la propia UI (agregar/editar/borrar tickers y posición). Los datos quedan en `data/stocks_config.json` (gitignored, contiene precios de compra reales). `data/stocks_config.example.json` es la plantilla versionada.

### Pausar una acción

Cada tarjeta de la watchlist tiene un botón **Pausar**. Una acción en pausa
sigue en la lista con su posición intacta, pero queda afuera del análisis: no se
descargan sus datos, no entra en el total del portafolio ni en el prompt del
LLM. Sirve para concentrar una corrida en las acciones nuevas que estás mirando
sin borrar las que ya venís siguiendo. **Activar** la vuelve a incluir.

## Interpretación con IA (opcional)

Desde el ⚙ de la UI configurás proveedor, modelo y API key. Por defecto viene configurado **OpenRouter**, que cubre modelos de todos los proveedores con una sola key:

- **OpenRouter** (default) — modelo con el prefijo del proveedor real (ej. `openai/gpt-latest`, `anthropic/claude-sonnet-5`)
- **Anthropic** — modelo sin prefijo (ej. `claude-sonnet-5`)
- **OpenAI** — modelo sin prefijo (ej. `gpt-4o`)

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
├── analysis/               # indicadores, fetch de mercado (yfinance) y geometría SVG
├── xtb/                     # parser del reporte de XTB, métricas y sync de watchlist
├── llm/                     # providers Anthropic / OpenAI / OpenRouter
├── templates/               # Jinja2 + partials HTMX
└── static/                  # css/js
data/                        # watchlist, settings y cache — todo gitignored salvo el .example
tests/                       # pytest sobre workbooks sintéticos
```

Los gráficos son SVG generados en el servidor (`analysis/sparkline.py`,
`dial.py`, `donut.py`, `curve.py`) — no hay librería de charts ni JavaScript
propio más allá de htmx.

## Importación desde XTB

En XTB: **Cuenta → Historial de la cuenta → Exportar a Excel**. Subí ese `.xlsx`
desde el panel *Portafolio XTB* y la app arma un dashboard con:

- Valor abierto, P&L realizado y no realizado, capital aportado, saldo en
  efectivo, dividendos y retenciones, más el **retorno real de la cuenta**
  (lo que vale hoy contra lo que pusiste).
- Un donut de reparto con tres vistas: **por acción**, **por sector** y **por
  tipo de activo**. El sector no viene en el reporte — XTB solo informa
  `STOCK`/`ETF` — así que se toma de los fundamentals ya cacheados en
  `data/last_results.json`, y si falta, del proveedor de datos.
- Ganancia realizada por ticker, con tasa de acierto y días promedio de tenencia.
- Curva de capital aportado contra capital puesto en posiciones. Las tres
  series salen del movimiento de efectivo, así que son exactas; el valor de
  mercado histórico no está porque el reporte no lo trae.

### Sincronización con la watchlist

Con la casilla *Actualizar la watchlist* marcada (viene marcada), el broker pasa
a ser la fuente de verdad de los tickers que reporta:

| Situación | Qué pasa |
| --- | --- |
| Posición del broker que no está en la watchlist | se agrega |
| Posición del broker que ya estaba | se actualiza con el precio y volumen reales |
| Ticker cargado a mano que el broker no reporta | queda intacto |
| Ticker que vino de una importación previa y ya no está | queda en seguimiento, sin posición |
| Posición corta, o símbolo sin precio | se omite y se informa |
| Ticker en pausa | se actualiza, pero sigue en pausa |

**Nunca se borra un ticker.** Antes de cada escritura se guarda
`data/stocks_config.backup.json`, el panel lista exactamente qué cambió, y hay un
botón **Deshacer** que restaura el estado anterior.

Los archivos generados (`data/xtb_portfolio.json`, el backup y cualquier
`.xlsx`) están en `.gitignore`: son datos de tu cuenta y no se commitean.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

Corren sobre workbooks sintéticos generados en memoria — sin red y sin datos
reales.

## To Do

- RAG de contenido sobre finanzas y entrega de resultados
- El Llm está teniendo en cuenta las noticias?
- Curva de valor de mercado histórico (requiere precios diarios de cada ticker
  que se haya tenido alguna vez)
