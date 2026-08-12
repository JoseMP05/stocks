"""Builds the interpretation prompt from a full analysis run."""

from __future__ import annotations

import json

from app.models import AnalysisResult, AnalysisRun

_INSTRUCTIONS = """\
Sos un analista financiero. A continuación recibís, en JSON, el resultado de \
un análisis técnico y fundamental de un portafolio completo de acciones.

Escribí un análisis en español que cubra:
1. Lectura conjunta de lo técnico y lo fundamental para cada acción.
2. Coherencia o divergencia entre ambas lecturas.
3. Riesgos concretos, principales amenazas operativas, financieras o de mercado \
tanto por acción como del portafolio en su conjunto.
4. Si hay una posición personal (campo "position"), comentá su situación \
puntual: ganancia/pérdida y qué tan lejos está del punto de equilibrio.
5. Ecosistema y Negocios Adyacentes: Explicá qué sectores, proveedores o \
competidores cercanos se ven directamente impactados por el desempeño de esta empresa.

Tono y audiencia:
- Usa un tono profesional pero comprensible para un inversor individual. Explica de manera sencilla \
y breve los terminos que puedan sonar extraños.
- Tu audiencia puede ser un inversor en aprendizaje.

Cerrá siempre con un disclaimer explícito de que esto no es asesoría \
financiera.

Datos del portafolio:
"""


def build_prompt(run: AnalysisRun) -> str:
    payload = [_ticker_payload(result) for result in run.results]
    return _INSTRUCTIONS + json.dumps(payload, ensure_ascii=False)


def _ticker_payload(result: AnalysisResult) -> dict:
    return {
        "ticker": result.ticker,
        "price": result.price,
        "change_pct": result.change_pct,
        "verdict": result.verdict,
        "indicators": result.indicators.model_dump(exclude_none=True),
        "fundamentals": result.fundamentals.model_dump(exclude_none=True),
        "news": [item.title for item in result.news],
        "position": result.position.model_dump() if result.position else None,
    }
