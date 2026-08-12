"""Plain-language explanations for every metric the UI puts on screen.

The audience includes people who are still learning to invest, so each entry
says what the number measures and how to read it, not just what the acronym
stands for. Exposed to templates as the `glossary` Jinja global and consumed
through the `partials/_glossary.html` macro.

Copy is Spanish because the whole UI is; keys and code stay English-neutral.
"""

from __future__ import annotations

from typing import TypedDict


class GlossaryEntry(TypedDict):
    term: str
    short: str
    body: str


GLOSSARY: dict[str, GlossaryEntry] = {
    "rsi": {
        "term": "RSI (14)",
        "short": "Fuerza relativa del precio en las últimas 14 sesiones.",
        "body": (
            "Mide qué tan fuerte viene subiendo o bajando el precio en las últimas "
            "14 sesiones, en una escala de 0 a 100. Por debajo de 30 se considera "
            "sobreventa (cayó mucho y podría rebotar) y por encima de 70 sobrecompra "
            "(subió mucho y podría corregir). Entre 30 y 70 no dice nada: es zona neutral."
        ),
    },
    "macd": {
        "term": "MACD",
        "short": "Compara dos promedios del precio para detectar cambios de tendencia.",
        "body": (
            "Compara un promedio rápido del precio contra uno lento y grafica la "
            "diferencia junto a su propia línea de señal. Cuando el MACD queda por "
            "encima de la señal, el impulso reciente es alcista; cuando queda por "
            "debajo, es bajista. Sirve para ver cambios de tendencia, no para predecir "
            "cuánto va a moverse el precio."
        ),
    },
    "bollinger": {
        "term": "Bandas de Bollinger",
        "short": "Un canal estadístico alrededor del precio promedio.",
        "body": (
            "Dibujan un canal alrededor del promedio de las últimas 20 sesiones, "
            "ancho según qué tan volátil está la acción. Un precio dentro de las bandas "
            "es movimiento normal; por debajo de la banda inferior sugiere sobreventa y "
            "por encima de la superior, sobrecompra. Salirse de las bandas no es una "
            "orden de compra o venta, solo un aviso de que el movimiento fue inusual."
        ),
    },
    "sma": {
        "term": "Media móvil (SMA)",
        "short": "El precio promedio de los últimos N días.",
        "body": (
            "Es el precio promedio de cierre de los últimos 20, 50 o 200 días. Se usa "
            "como referencia de tendencia: si el precio actual está por encima de la "
            "media, la tendencia de ese plazo es favorable; si está por debajo, es "
            "adversa. La de 200 días pesa más porque describe la tendencia de largo plazo."
        ),
    },
    "volumen_relativo": {
        "term": "Volumen relativo",
        "short": "Cuántas veces el volumen habitual se negoció hoy.",
        "body": (
            "Compara la cantidad de acciones negociadas hoy contra el promedio de los "
            "últimos 20 días. Un valor de 1× es actividad normal; 2× significa el doble "
            "de lo habitual. Un volumen alto le da más credibilidad al movimiento del "
            "precio, porque indica que participó mucha gente y no unos pocos."
        ),
    },
    "senal_neta": {
        "term": "Señal neta",
        "short": "Diferencia entre los puntos alcistas y los bajistas.",
        "body": (
            "Es la resta entre los puntos alcistas y los bajistas que suman todos los "
            "indicadores técnicos, en una escala de −5 a +5. Por encima de +1 el "
            "resultado se llama ALCISTA y por debajo de −1, BAJISTA; entre ambos "
            "límites queda NEUTRAL. Resume la foto técnica en un solo número, pero no "
            "toma en cuenta los fundamentos de la empresa."
        ),
    },
    "market_cap": {
        "term": "Capitalización de mercado",
        "short": "Cuánto vale la empresa entera en bolsa.",
        "body": (
            "Es el precio de la acción multiplicado por todas las acciones existentes: "
            "lo que costaría comprar la empresa completa al precio de hoy. Sirve para "
            "dimensionar el tamaño del negocio y comparar empresas entre sí. Las "
            "compañías más grandes suelen moverse menos que las pequeñas."
        ),
    },
    "pe_trailing": {
        "term": "P/E trailing",
        "short": "Cuántos años de ganancias pasadas cuesta la acción.",
        "body": (
            "Divide el precio de la acción por la ganancia por acción de los últimos "
            "doce meses. Un P/E de 25× significa que pagás 25 dólares por cada dólar "
            "que la empresa ganó en el último año. Solo tiene sentido comparado contra "
            "empresas del mismo sector o contra la historia de la propia acción."
        ),
    },
    "pe_forward": {
        "term": "P/E forward",
        "short": "Lo mismo, pero sobre las ganancias que se esperan.",
        "body": (
            "Igual que el P/E trailing, pero usando la ganancia estimada para el año "
            "que viene en lugar de la ya reportada. Si es bastante menor que el "
            "trailing, el mercado espera que las ganancias crezcan. Es una proyección "
            "de analistas, así que puede fallar."
        ),
    },
    "revenue": {
        "term": "Revenue (ingresos)",
        "short": "Todo lo que la empresa facturó, antes de costos.",
        "body": (
            "Es el total facturado por la empresa en el período, antes de descontar "
            "cualquier costo o impuesto. No es ganancia: una compañía puede tener "
            "ingresos enormes y aun así perder dinero. Se mira junto al margen para "
            "saber cuánto de esa facturación queda realmente."
        ),
    },
    "revenue_growth": {
        "term": "Crecimiento de revenue",
        "short": "Cuánto crecieron los ingresos frente al año anterior.",
        "body": (
            "Compara la facturación actual contra la del mismo período del año "
            "anterior. Un crecimiento alto y sostenido suele justificar múltiplos "
            "caros como un P/E elevado. Un crecimiento negativo indica que el negocio "
            "se está achicando."
        ),
    },
    "gross_margin": {
        "term": "Margen bruto",
        "short": "Qué porcentaje de cada venta sobrevive al costo de producirla.",
        "body": (
            "De cada dólar facturado, es el porcentaje que queda después de pagar el "
            "costo directo de producir el producto o servicio. Un margen alto indica "
            "un negocio con poder de fijar precios; uno bajo, un negocio de volumen. "
            "Compará siempre dentro del mismo sector: el software y el retail juegan "
            "en escalas distintas."
        ),
    },
    "eps": {
        "term": "EPS (ganancia por acción)",
        "short": "La ganancia de la empresa dividida entre sus acciones.",
        "body": (
            "Reparte la ganancia neta de los últimos doce meses entre todas las "
            "acciones en circulación. Muestra cuánto gana la empresa por cada acción "
            "que tenés. Un EPS negativo significa que la compañía está perdiendo dinero."
        ),
    },
    "beta": {
        "term": "Beta",
        "short": "Cuánto se mueve la acción cuando se mueve el mercado.",
        "body": (
            "Mide la sensibilidad de la acción frente al mercado general. Una beta de "
            "1× se mueve igual que el índice; 2× amplifica al doble tanto las subidas "
            "como las caídas, y menos de 1× amortigua. Es una medida de riesgo por "
            "volatilidad, no de calidad de la empresa."
        ),
    },
    "week52": {
        "term": "Rango de 52 semanas",
        "short": "El máximo y el mínimo del último año.",
        "body": (
            "Marca el precio más alto y el más bajo de los últimos doce meses, y a qué "
            "distancia está la cotización actual de cada extremo. Ubica el precio de "
            "hoy dentro de su historia reciente. Estar cerca del máximo no significa "
            "que sea caro, ni cerca del mínimo que sea barato."
        ),
    },
    "target_price": {
        "term": "Precio objetivo",
        "short": "El promedio de lo que esperan los analistas a 12 meses.",
        "body": (
            "Es el promedio de los precios que los analistas que siguen la acción "
            "esperan a doce meses vista. La diferencia contra el precio actual se "
            "muestra como potencial de subida o bajada. Son opiniones, se revisan "
            "seguido y suelen pecar de optimistas."
        ),
    },
    "recomendacion": {
        "term": "Recomendación de analistas",
        "short": "El consenso de los analistas que cubren la acción.",
        "body": (
            "Resume en una palabra el consenso de las casas de análisis: comprar, "
            "mantener o vender. Es útil como termómetro de expectativas del mercado, "
            "no como instrucción. Las recomendaciones tienden a agruparse en "
            "«mantener» y a cambiar tarde."
        ),
    },
    "costo_promedio": {
        "term": "Costo promedio",
        "short": "Lo que te costó en promedio cada acción que tenés.",
        "body": (
            "Es el precio medio que pagaste por cada acción, sumando todas tus "
            "compras. Es la línea de referencia de tu posición: por encima estás en "
            "ganancia y por debajo, en pérdida. En el gráfico aparece como la línea "
            "punteada «mi costo»."
        ),
    },
    "pnl": {
        "term": "P&L (ganancia o pérdida)",
        "short": "Cuánto ganaste o perdiste, todavía sin vender.",
        "body": (
            "Es la diferencia entre lo que vale hoy tu posición y lo que invertiste en "
            "ella. Mientras no vendas es una ganancia o pérdida no realizada: cambia "
            "todos los días con el precio. El porcentaje mide el rendimiento sobre lo "
            "invertido, no sobre el total de tu cartera."
        ),
    },
    "breakeven": {
        "term": "Break-even",
        "short": "El punto donde no ganás ni perdés.",
        "body": (
            "Es el precio al que tu posición vale exactamente lo que invertiste, o "
            "sea tu costo promedio. El porcentaje indica cuánto debería moverse el "
            "precio para llegar ahí. Si ya lo superaste, muestra cuánto margen tenés "
            "por encima antes de volver a estar en pérdida."
        ),
    },
}
