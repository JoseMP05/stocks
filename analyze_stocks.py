#!/usr/bin/env python3
"""
Herramienta de Análisis de Acciones — Técnico & Fundamental
============================================================
Edita stocks_config.json para agregar/modificar acciones y posiciones.
Ejecuta este script para generar un reporte HTML actualizado.

Formato de stocks_config.json:
{
  "watchlist": [
    {
      "ticker": "AAPL",
      "position": {            <-- opcional, si tienes acciones
        "avg_cost": 150.00,    <-- precio promedio de compra
        "invested": 500        <-- dinero invertido en USD (o usa "shares": 3.33)
      }
    },
    {
      "ticker": "NVDA"         <-- sin posición = solo seguimiento
    }
  ]
}
"""

import sys
import os
import json
import warnings
from datetime import datetime

warnings.filterwarnings("ignore")

# ── dependencias ────────────────────────────────────────────────────────────
try:
    import yfinance as yf
    import pandas as pd
    import numpy as np
except ImportError as e:
    print(f"Error: falta librería → {e}")
    print("Ejecuta: pip install yfinance pandas numpy --break-system-packages")
    sys.exit(1)

# ── rutas ────────────────────────────────────────────────────────────────────
SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "stocks_config.json")
OUTPUT_DIR  = SCRIPT_DIR


# ════════════════════════════════════════════════════════════════════════════
#  CÁLCULO DE INDICADORES TÉCNICOS
# ════════════════════════════════════════════════════════════════════════════

def calc_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    delta = prices.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def calc_macd(prices: pd.Series, fast=12, slow=26, signal=9):
    ema_f  = prices.ewm(span=fast, adjust=False).mean()
    ema_s  = prices.ewm(span=slow, adjust=False).mean()
    macd   = ema_f - ema_s
    sig    = macd.ewm(span=signal, adjust=False).mean()
    return macd, sig, macd - sig


def calc_bollinger(prices: pd.Series, period=20, n_std=2):
    sma = prices.rolling(period).mean()
    std = prices.rolling(period).std()
    return sma + n_std * std, sma, sma - n_std * std


# ════════════════════════════════════════════════════════════════════════════
#  ANÁLISIS POR ACCIÓN
# ════════════════════════════════════════════════════════════════════════════

def analyze(ticker_cfg: dict) -> dict | None:
    ticker = ticker_cfg["ticker"].upper()
    print(f"  [{ticker}] Descargando datos...", end=" ", flush=True)

    try:
        stock = yf.Ticker(ticker)
        hist  = stock.history(period="1y")
        if hist.empty:
            print("sin datos.")
            return None
    except Exception as e:
        print(f"error: {e}")
        return None

    closes  = hist["Close"].squeeze()
    volumes = hist["Volume"].squeeze()
    price   = float(closes.iloc[-1])
    prev    = float(closes.iloc[-2])
    chg_pct = (price - prev) / prev * 100

    # ── indicadores ──────────────────────────────────────────────────────────
    rsi                     = calc_rsi(closes)
    macd_line, sig_line, _  = calc_macd(closes)
    bb_up, bb_mid, bb_low   = calc_bollinger(closes)

    sma20  = closes.rolling(20).mean()
    sma50  = closes.rolling(50).mean()
    sma200 = closes.rolling(200).mean()

    rsi_v    = float(rsi.iloc[-1])
    macd_v   = float(macd_line.iloc[-1])
    sig_v    = float(sig_line.iloc[-1])
    bb_up_v  = float(bb_up.iloc[-1])
    bb_low_v = float(bb_low.iloc[-1])
    sma20_v  = float(sma20.iloc[-1])
    sma50_v  = float(sma50.iloc[-1])
    sma200_v = float(sma200.iloc[-1])

    avg_vol  = float(volumes.rolling(20).mean().iloc[-1])
    vol_rat  = float(volumes.iloc[-1]) / avg_vol if avg_vol else 1.0

    # ── señales ───────────────────────────────────────────────────────────────
    bull = bear = 0.0

    if rsi_v < 30:
        rsi_sig = "SOBREVENTA — posible rebote"; bull += 1
    elif rsi_v > 70:
        rsi_sig = "SOBRECOMPRA — posible corrección"; bear += 1
    else:
        rsi_sig = "Zona neutral"

    if macd_v > sig_v:
        macd_sig = "ALCISTA — MACD sobre señal"; bull += 1
    else:
        macd_sig = "BAJISTA — MACD bajo señal"; bear += 1

    if price < bb_low_v:
        bb_sig = "Bajo banda inferior (sobreventa)"; bull += 1
    elif price > bb_up_v:
        bb_sig = "Sobre banda superior (sobrecompra)"; bear += 1
    else:
        bb_sig = "Dentro de bandas"

    above20  = price > sma20_v;  bull += 0.5 if above20  else 0; bear += 0.5 if not above20  else 0
    above50  = price > sma50_v;  bull += 0.5 if above50  else 0; bear += 0.5 if not above50  else 0
    above200 = price > sma200_v; bull += 1.0 if above200 else 0; bear += 1.0 if not above200 else 0

    if bull > bear + 1:
        overall = "ALCISTA"
    elif bear > bull + 1:
        overall = "BAJISTA"
    else:
        overall = "NEUTRAL"

    # ── fundamentales ─────────────────────────────────────────────────────────
    try:
        info = stock.info
    except Exception:
        info = {}

    w52h = info.get("fiftyTwoWeekHigh")
    w52l = info.get("fiftyTwoWeekLow")
    dist_high = (price - w52h) / w52h * 100 if w52h else None
    dist_low  = (price - w52l) / w52l * 100 if w52l else None

    fundamentals = {
        "company":      info.get("longName", ticker),
        "sector":       info.get("sector", "N/A"),
        "industry":     info.get("industry", "N/A"),
        "market_cap":   info.get("marketCap"),
        "pe":           info.get("trailingPE"),
        "fwd_pe":       info.get("forwardPE"),
        "revenue":      info.get("totalRevenue"),
        "rev_growth":   info.get("revenueGrowth"),
        "gross_margin": info.get("grossMargins"),
        "eps":          info.get("trailingEps"),
        "fwd_eps":      info.get("forwardEps"),
        "beta":         info.get("beta"),
        "target":       info.get("targetMeanPrice"),
        "recom":        info.get("recommendationKey", "N/A"),
        "w52h":         w52h,
        "w52l":         w52l,
        "dist_high":    dist_high,
        "dist_low":     dist_low,
    }

    # ── noticias ──────────────────────────────────────────────────────────────
    try:
        raw_news = stock.news or []
        news = []
        for n in raw_news[:5]:
            content = n.get("content", n)
            title   = content.get("title", "Sin título")
            url_obj = content.get("canonicalUrl", {})
            url     = url_obj.get("url", "#") if isinstance(url_obj, dict) else n.get("link", "#")
            pub     = content.get("pubDate", "")[:10]
            news.append({"title": title, "url": url, "date": pub})
    except Exception:
        news = []

    # ── posición personal ─────────────────────────────────────────────────────
    position = None
    pos_cfg  = ticker_cfg.get("position")
    if pos_cfg:
        avg_cost = float(pos_cfg.get("avg_cost", 0))
        if "shares" in pos_cfg:
            shares   = float(pos_cfg["shares"])
            invested = shares * avg_cost
        elif "invested" in pos_cfg:
            invested = float(pos_cfg["invested"])
            shares   = invested / avg_cost if avg_cost else 0
        else:
            shares = invested = 0

        current_val   = shares * price
        pnl           = current_val - invested
        pnl_pct       = pnl / invested * 100 if invested else 0
        to_breakeven  = (avg_cost - price) / price * 100  # >0 = necesita subir

        position = {
            "shares":      shares,
            "avg_cost":    avg_cost,
            "invested":    invested,
            "current_val": current_val,
            "pnl":         pnl,
            "pnl_pct":     pnl_pct,
            "to_breakeven": to_breakeven,
        }

    print("✓")
    return {
        "ticker":    ticker,
        "price":     price,
        "chg_pct":   chg_pct,
        "rsi":       rsi_v,  "rsi_sig":  rsi_sig,
        "macd_v":    macd_v, "macd_sig": macd_sig,
        "bb_up":     bb_up_v,"bb_low":   bb_low_v, "bb_sig": bb_sig,
        "sma20":     sma20_v,  "above20":  above20,
        "sma50":     sma50_v,  "above50":  above50,
        "sma200":    sma200_v, "above200": above200,
        "vol_rat":   vol_rat,
        "overall":   overall,
        "bull":      bull,
        "bear":      bear,
        "fundamentals": fundamentals,
        "news":      news,
        "position":  position,
    }


# ════════════════════════════════════════════════════════════════════════════
#  GENERACIÓN DE HTML
# ════════════════════════════════════════════════════════════════════════════

def _color(val, good_high=True):
    """Verde si es bueno, rojo si es malo."""
    if val is None: return "#8b949e"
    return "#26d97f" if val else "#f85149"

def _num(n, prefix="$", suffix="", dec=2, mult=1):
    if n is None or n == "N/A": return "N/A"
    try:
        v = float(n) * mult
        if suffix == "%" and mult == 100:
            return f"{v:.{dec}f}%"
        if abs(v) >= 1e12: return f"{prefix}{v/1e12:.2f}T{suffix}"
        if abs(v) >= 1e9:  return f"{prefix}{v/1e9:.2f}B{suffix}"
        if abs(v) >= 1e6:  return f"{prefix}{v/1e6:.2f}M{suffix}"
        return f"{prefix}{v:,.{dec}f}{suffix}"
    except Exception:
        return str(n)

def _sig_color(signal: str) -> str:
    s = signal.upper()
    if "ALCISTA" in s or "SOBREVENTA" in s or "REBOTE" in s: return "#26d97f"
    if "BAJISTA" in s or "SOBRECOMPRA" in s or "CAÍDA" in s: return "#f85149"
    return "#e3b341"

def _rec_label(key: str) -> str:
    m = {"buy": "✅ Comprar", "strong_buy": "✅ Compra fuerte",
         "hold": "⚠️ Mantener", "sell": "🔴 Vender", "strong_sell": "🔴 Venta fuerte"}
    return m.get(str(key).lower(), str(key).capitalize())


def build_html(results: list) -> str:
    now      = datetime.now().strftime("%d de %B de %Y — %H:%M")
    n_stocks = len([r for r in results if r])

    # portafolio global
    tot_inv = tot_cur = 0.0
    for r in results:
        if r and r["position"]:
            tot_inv += r["position"]["invested"]
            tot_cur += r["position"]["current_val"]
    tot_pnl     = tot_cur - tot_inv
    tot_pnl_pct = tot_pnl / tot_inv * 100 if tot_inv else 0
    port_col    = "#26d97f" if tot_pnl >= 0 else "#f85149"
    port_sign   = "+" if tot_pnl >= 0 else ""

    # ── portfolio card ────────────────────────────────────────────────────────
    portfolio_html = ""
    if tot_inv > 0:
        portfolio_html = f"""
    <div class="card port-card">
      <div class="card-title">💼 Mi Portafolio</div>
      <div class="port-grid">
        <div class="kpi"><div class="kpi-l">Total invertido</div><div class="kpi-v">${tot_inv:,.2f}</div></div>
        <div class="kpi"><div class="kpi-l">Valor actual</div><div class="kpi-v">${tot_cur:,.2f}</div></div>
        <div class="kpi"><div class="kpi-l">Ganancia / Pérdida</div>
          <div class="kpi-v" style="color:{port_col}">{port_sign}${tot_pnl:,.2f}</div></div>
        <div class="kpi"><div class="kpi-l">Rendimiento</div>
          <div class="kpi-v" style="color:{port_col}">{port_sign}{tot_pnl_pct:.2f}%</div></div>
      </div>
    </div>"""

    # ── tarjetas por acción ───────────────────────────────────────────────────
    cards_html = ""
    for r in results:
        if not r: continue
        f   = r["fundamentals"]
        dch = r["chg_pct"]
        dch_col  = "#26d97f" if dch >= 0 else "#f85149"
        dch_sign = "+" if dch >= 0 else ""
        ov_col   = _sig_color(r["overall"])

        # posición
        pos_html = ""
        if r["position"]:
            p  = r["position"]
            pc = "#26d97f" if p["pnl"] >= 0 else "#f85149"
            ps = "+" if p["pnl"] >= 0 else ""
            be = p["to_breakeven"]
            if be > 0:
                be_txt = f"Necesita subir <b>{be:.1f}%</b> para recuperar inversión"
                be_col = "#e3b341"
            else:
                be_txt = f"Break-even superado en <b>{abs(be):.1f}%</b>"
                be_col = "#26d97f"

            pos_html = f"""
        <div class="sub-card pos-block">
          <div class="sub-title">📊 Mi Posición</div>
          <div class="pos-grid">
            <div class="pos-kpi"><div class="kpi-l">Acciones</div><div class="kpi-v">{p['shares']:.4f}</div></div>
            <div class="pos-kpi"><div class="kpi-l">Precio promedio</div><div class="kpi-v">${p['avg_cost']:.2f}</div></div>
            <div class="pos-kpi"><div class="kpi-l">Invertido</div><div class="kpi-v">${p['invested']:,.2f}</div></div>
            <div class="pos-kpi"><div class="kpi-l">Valor actual</div><div class="kpi-v">${p['current_val']:,.2f}</div></div>
            <div class="pos-kpi"><div class="kpi-l">P&L</div>
              <div class="kpi-v" style="color:{pc}">{ps}${p['pnl']:,.2f} ({ps}{p['pnl_pct']:.1f}%)</div></div>
            <div class="pos-kpi full"><div class="kpi-l" style="color:{be_col}">{be_txt}</div></div>
          </div>
        </div>"""

        # señales técnicas
        sma20_col  = "#26d97f" if r["above20"]  else "#f85149"
        sma50_col  = "#26d97f" if r["above50"]  else "#f85149"
        sma200_col = "#26d97f" if r["above200"] else "#f85149"
        sma20_txt  = ("▲ sobre" if r["above20"]  else "▼ bajo") + f" SMA20 (${r['sma20']:.2f})"
        sma50_txt  = ("▲ sobre" if r["above50"]  else "▼ bajo") + f" SMA50 (${r['sma50']:.2f})"
        sma200_txt = ("▲ sobre" if r["above200"] else "▼ bajo") + f" SMA200 (${r['sma200']:.2f})"
        rsi_col    = _sig_color(r["rsi_sig"])
        macd_col   = _sig_color(r["macd_sig"])
        bb_col     = _sig_color(r["bb_sig"])
        vol_col    = "#26d97f" if r["vol_rat"] > 1.5 else ("#e3b341" if r["vol_rat"] > 1.0 else "#8b949e")

        # fundamentales: target de analistas
        tgt = f["target"]
        if tgt and r["price"]:
            upside     = (float(tgt) - r["price"]) / r["price"] * 100
            tgt_col    = "#26d97f" if upside > 0 else "#f85149"
            tgt_sign   = "+" if upside > 0 else ""
            tgt_html   = f"${float(tgt):.2f} <span style='color:{tgt_col}'>({tgt_sign}{upside:.1f}% potencial)</span>"
        else:
            tgt_html = "N/A"

        rev_growth = f["rev_growth"]
        rev_growth_str = f"{float(rev_growth)*100:.1f}%" if rev_growth is not None else "N/A"
        gross_margin = f["gross_margin"]
        gross_str = f"{float(gross_margin)*100:.1f}%" if gross_margin is not None else "N/A"

        dh = f"({f['dist_high']:.1f}% del máx)" if f["dist_high"] is not None else ""
        dl = f"(+{f['dist_low']:.1f}% del mín)" if f["dist_low"] is not None else ""

        # noticias
        news_rows = ""
        for n in r["news"]:
            news_rows += f'<div class="news-row"><a href="{n["url"]}" target="_blank">{n["title"]}</a><span class="news-d">{n["date"]}</span></div>'
        if not news_rows:
            news_rows = '<div class="news-row" style="color:#8b949e">Sin noticias recientes disponibles</div>'

        # barra visual de bull vs bear
        total_signals = r["bull"] + r["bear"]
        bull_pct = r["bull"] / total_signals * 100 if total_signals else 50
        bear_pct = 100 - bull_pct

        cards_html += f"""
    <div class="card stock-card">
      <!-- encabezado -->
      <div class="stock-head">
        <div>
          <div class="s-ticker">{r['ticker']}</div>
          <div class="s-name">{f['company']}</div>
          <div class="s-meta">{f['sector']} · {f['industry']}</div>
        </div>
        <div class="s-right">
          <div class="s-price">${r['price']:.2f}</div>
          <div class="s-chg" style="color:{dch_col}">{dch_sign}{dch:.2f}% hoy</div>
          <div class="badge" style="background:{ov_col}20;color:{ov_col};border:1px solid {ov_col}40">{r['overall']}</div>
        </div>
      </div>

      <!-- barra bull/bear -->
      <div class="signal-bar">
        <div class="sb-label"><span style="color:#26d97f">▲ Alcistas {r['bull']:.1f}</span></div>
        <div class="sb-track">
          <div class="sb-bull" style="width:{bull_pct:.0f}%"></div>
          <div class="sb-bear" style="width:{bear_pct:.0f}%"></div>
        </div>
        <div class="sb-label right"><span style="color:#f85149">Bajistas {r['bear']:.1f} ▼</span></div>
      </div>

      {pos_html}

      <!-- técnico + fundamental -->
      <div class="two-col">
        <div>
          <div class="sub-title">📈 Análisis Técnico</div>
          <div class="ind-row"><span class="ind-n">RSI (14)</span><span class="ind-v" style="color:{rsi_col}">{r['rsi']:.1f} — {r['rsi_sig']}</span></div>
          <div class="ind-row"><span class="ind-n">MACD</span><span class="ind-v" style="color:{macd_col}">{r['macd_sig']}</span></div>
          <div class="ind-row"><span class="ind-n">Bollinger</span><span class="ind-v" style="color:{bb_col}">{r['bb_sig']}</span></div>
          <div class="ind-row"><span class="ind-n">SMA 20</span><span class="ind-v" style="color:{sma20_col}">{sma20_txt}</span></div>
          <div class="ind-row"><span class="ind-n">SMA 50</span><span class="ind-v" style="color:{sma50_col}">{sma50_txt}</span></div>
          <div class="ind-row"><span class="ind-n">SMA 200</span><span class="ind-v" style="color:{sma200_col}">{sma200_txt}</span></div>
          <div class="ind-row"><span class="ind-n">Volumen</span><span class="ind-v" style="color:{vol_col}">{r['vol_rat']:.1f}× promedio 20d</span></div>
        </div>
        <div>
          <div class="sub-title">🏢 Fundamentos</div>
          <div class="ind-row"><span class="ind-n">Cap. mercado</span><span class="ind-v">{_num(f['market_cap'])}</span></div>
          <div class="ind-row"><span class="ind-n">P/E Trailing</span><span class="ind-v">{_num(f['pe'],'','×')}</span></div>
          <div class="ind-row"><span class="ind-n">P/E Forward</span><span class="ind-v">{_num(f['fwd_pe'],'','×')}</span></div>
          <div class="ind-row"><span class="ind-n">Revenue</span><span class="ind-v">{_num(f['revenue'])}</span></div>
          <div class="ind-row"><span class="ind-n">Crec. revenue</span><span class="ind-v">{rev_growth_str}</span></div>
          <div class="ind-row"><span class="ind-n">Margen bruto</span><span class="ind-v">{gross_str}</span></div>
          <div class="ind-row"><span class="ind-n">EPS (TTM)</span><span class="ind-v">{_num(f['eps'])}</span></div>
          <div class="ind-row"><span class="ind-n">Beta</span><span class="ind-v">{_num(f['beta'],'','×')}</span></div>
          <div class="ind-row"><span class="ind-n">Máx. 52 sem.</span><span class="ind-v">{_num(f['w52h'])} <small style="color:#8b949e">{dh}</small></span></div>
          <div class="ind-row"><span class="ind-n">Mín. 52 sem.</span><span class="ind-v">{_num(f['w52l'])} <small style="color:#8b949e">{dl}</small></span></div>
          <div class="ind-row"><span class="ind-n">Target analistas</span><span class="ind-v">{tgt_html}</span></div>
          <div class="ind-row"><span class="ind-n">Recomendación</span><span class="ind-v">{_rec_label(f['recom'])}</span></div>
        </div>
      </div>

      <!-- noticias -->
      <div class="sub-title" style="margin-top:16px">📰 Noticias recientes</div>
      <div class="news-box">{news_rows}</div>
    </div>"""

    # ── CSS + HTML completo ───────────────────────────────────────────────────
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Análisis de Acciones</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0d1117;color:#e6edf3;padding:24px 20px;min-height:100vh}}
h1{{font-size:1.5rem;font-weight:800;margin-bottom:2px}}
.subtitle{{color:#8b949e;font-size:.85rem;margin-bottom:22px}}

.card{{background:#161b22;border:1px solid #30363d;border-radius:14px;padding:22px;margin-bottom:20px}}
.card-title{{font-size:.85rem;font-weight:600;color:#8b949e;text-transform:uppercase;letter-spacing:.8px;margin-bottom:14px}}

/* portafolio */
.port-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}}
.kpi{{text-align:center}}
.kpi-l{{font-size:.72rem;color:#8b949e;margin-bottom:4px}}
.kpi-v{{font-size:1.25rem;font-weight:700}}

/* acción */
.stock-card{{}}
.stock-head{{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:14px}}
.s-ticker{{font-size:1.9rem;font-weight:800;letter-spacing:-1px}}
.s-name{{font-size:.88rem;color:#8b949e;margin-top:2px}}
.s-meta{{font-size:.72rem;color:#6e7681;margin-top:3px}}
.s-right{{text-align:right}}
.s-price{{font-size:1.9rem;font-weight:700}}
.s-chg{{font-size:.85rem;margin-top:2px}}
.badge{{display:inline-block;padding:3px 10px;border-radius:20px;font-size:.72rem;font-weight:700;letter-spacing:.6px;margin-top:7px}}

/* barra bull/bear */
.signal-bar{{display:flex;align-items:center;gap:10px;margin-bottom:16px}}
.sb-label{{font-size:.72rem;min-width:90px}}
.sb-label.right{{text-align:right}}
.sb-track{{flex:1;height:6px;border-radius:4px;display:flex;overflow:hidden;background:#21262d}}
.sb-bull{{background:#26d97f;height:100%;transition:width .4s}}
.sb-bear{{background:#f85149;height:100%;transition:width .4s}}

/* posición */
.sub-card{{background:#0d1117;border:1px solid #21262d;border-radius:10px;padding:14px;margin-bottom:16px}}
.pos-block{{}}
.sub-title{{font-size:.75rem;font-weight:600;color:#8b949e;text-transform:uppercase;letter-spacing:.7px;margin-bottom:10px}}
.pos-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}}
.pos-kpi{{}}
.pos-kpi.full{{grid-column:1/-1}}

/* dos columnas técnico + fundamental */
.two-col{{display:grid;grid-template-columns:1fr 1fr;gap:24px;margin-top:6px}}

/* indicadores */
.ind-row{{display:flex;justify-content:space-between;align-items:baseline;padding:6px 0;border-bottom:1px solid #21262d;gap:8px}}
.ind-row:last-child{{border-bottom:none}}
.ind-n{{font-size:.76rem;color:#8b949e;white-space:nowrap;flex-shrink:0}}
.ind-v{{font-size:.76rem;text-align:right}}

/* noticias */
.news-box{{background:#0d1117;border-radius:8px;padding:12px;margin-top:6px}}
.news-row{{display:flex;justify-content:space-between;align-items:baseline;gap:12px;padding:7px 0;border-bottom:1px solid #21262d}}
.news-row:last-child{{border-bottom:none;padding-bottom:0}}
.news-row a{{font-size:.79rem;color:#58a6ff;text-decoration:none;line-height:1.4}}
.news-row a:hover{{text-decoration:underline}}
.news-d{{font-size:.7rem;color:#6e7681;white-space:nowrap;flex-shrink:0}}

.footer{{text-align:center;color:#6e7681;font-size:.72rem;margin-top:20px;padding-top:14px;border-top:1px solid #21262d}}

@media(max-width:650px){{
  .port-grid{{grid-template-columns:repeat(2,1fr)}}
  .pos-grid{{grid-template-columns:repeat(2,1fr)}}
  .two-col{{grid-template-columns:1fr}}
  .signal-bar .sb-label{{min-width:60px;font-size:.65rem}}
}}
</style>
</head>
<body>
<h1>📊 Análisis de Acciones</h1>
<div class="subtitle">Generado el {now} · {n_stocks} acción{'es' if n_stocks != 1 else ''} analizadas</div>

{portfolio_html}
{cards_html}

<div class="footer">
  Datos: Yahoo Finance · Solo informativo · No es asesoría financiera
</div>
</body>
</html>"""


# ════════════════════════════════════════════════════════════════════════════
#  MAIN
# ════════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 50)
    print("  Herramienta de Análisis de Acciones")
    print("=" * 50)

    if not os.path.exists(CONFIG_FILE):
        print(f"\n❌ No encontré {CONFIG_FILE}")
        print("Crea el archivo con el formato del ejemplo en la cabecera de este script.")
        sys.exit(1)

    with open(CONFIG_FILE, encoding="utf-8") as f:
        config = json.load(f)

    watchlist = config.get("watchlist", [])
    if not watchlist:
        print("La lista de acciones está vacía. Edita stocks_config.json.")
        sys.exit(0)

    print(f"\nAnalizando {len(watchlist)} acción(es)...")
    results = [analyze(item) for item in watchlist]

    print("\nGenerando reporte...")
    html = build_html(results)

    ts          = datetime.now().strftime("%Y%m%d_%H%M")
    output_path = os.path.join(OUTPUT_DIR, f"stock_report_{ts}.html")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\n✅ Reporte: {output_path}\n")
    print(f"{'TICKER':<8} {'PRECIO':>8} {'HOY':>8}  SEÑAL")
    print("-" * 40)
    for r in results:
        if not r: continue
        sign = "+" if r["chg_pct"] >= 0 else ""
        print(f"{r['ticker']:<8} ${r['price']:>7.2f}  {sign}{r['chg_pct']:>5.2f}%  {r['overall']}")
        if r["position"]:
            p = r["position"]
            ps = "+" if p["pnl"] >= 0 else ""
            print(f"{'':8} {'Posición:':>8} ${p['current_val']:.2f}  P&L {ps}${p['pnl']:.2f} ({ps}{p['pnl_pct']:.1f}%)")
    print()

    return output_path


if __name__ == "__main__":
    main()
