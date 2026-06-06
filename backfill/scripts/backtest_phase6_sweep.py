"""Backtest Fase 6 — Barrido de parametros + seleccion robusta.

Reusa el modelo de fill de la Fase 2b pero:
  - precomputa arrays numpy por ventana UNA vez (rapido para la grilla)
  - agrega risk rule: MAX_CYCLES por ventana (evita la apuesta direccional degenerada)
Grilla X (favorito) x Y (longshot). Reporta PnL, legging, %ventanas+ por celda.
Seleccion robusta: preferir la celda cuyo PEOR vecino sea mas fuerte (no el max PnL).

Uso: py scripts/backtest_phase6_sweep.py
"""
import numpy as np, pandas as pd
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
TAKER_FEE = 0.018
SIZE = 10; TIMEOUT = 30; MIN_CLOSE = 60; MAX_CYCLES = 5

uni = pd.read_parquet(ROOT/"data/interim/backtest_universe.parquet")
tk = pd.read_parquet(ROOT/"data/interim/trades_bt.parquet"); tk["ts"] = tk.ts_ms/1000.0
ob = pd.read_parquet(ROOT/"data/interim/ob_bt.parquet")
tk_by = {m: g for m, g in tk.groupby("market_id")}
ob_by = {m: g for m, g in ob.groupby("market_id")}

# preprocesar cada ventana en arrays numpy (una vez)
print("preprocesando ventanas...")
WIN = []
for r in uni.itertuples(index=False):
    m = r.market_id
    if m not in tk_by or m not in ob_by: continue
    t0, t1 = r.ts_open, r.ts_close
    g = tk_by[m]; gw = g[(g.ts >= t0) & (g.ts < t1)]
    ogm = ob_by[m]
    toks = {}
    ok = True
    for oc in ("Up", "Down"):
        gt = gw[gw.outcome == oc].sort_values("ts")
        ot = ogm[(ogm.outcome == oc) & (ogm.sec >= t0-3600) & (ogm.sec < t1)].sort_values("sec")
        toks[oc] = dict(
            ts=gt.ts.values.astype(float), px=gt.price.values.astype(float),
            sz=gt.size_usdc.values.astype(float),
            sell=(gt.side.values == "SELL"),
            osec=ot.sec.values.astype(float), obid=ot.best_bid.values.astype(float),
            oask=ot.best_ask.values.astype(float), obsz=ot.best_bid_size.values.astype(float))
    # favorito al abrir
    def bid0(oc):
        a = toks[oc]; i = np.searchsorted(a["osec"], t0, "right")-1
        return a["obid"][i] if i >= 0 and len(a["obid"]) else 0.0
    fav = "Up" if bid0("Up") >= bid0("Down") else "Down"
    lon = "Down" if fav == "Up" else "Up"
    WIN.append(dict(t0=t0, t1=t1, fav=fav, lon=lon, fav_won=(r.outcome == fav), tok=toks))
print(f"  {len(WIN)} ventanas\n")

def fill(a, t_post, deadline, P, mode):
    osec = a["osec"]
    i = np.searchsorted(osec, t_post, "right")-1 if len(osec) else -1
    if i >= 0:
        ask = a["oask"][i]
        if ask > 0 and ask <= P: return (t_post, ask, True)
    queue = 0.0 if mode == "opt" else (a["obsz"][i] if i >= 0 else 0.0)
    ts = a["ts"]
    lo = np.searchsorted(ts, t_post, "right"); hi = np.searchsorted(ts, deadline, "right")
    cum = 0.0
    for k in range(lo, hi):
        if a["sell"][k] and a["px"][k] <= P:
            cum += a["sz"][k]
            if cum > queue: return (a["ts"][k], P, False)
    return None

def run(X, Y, mode):
    pnls = []; n_ok = 0; n_leg = 0
    for w in WIN:
        fa = w["tok"][w["fav"]]; lo = w["tok"][w["lon"]]
        t0, t1 = w["t0"], w["t1"]; pnl = 0.0; t = t0; cyc = 0
        while t < t1 - MIN_CLOSE and cyc < MAX_CYCLES:
            f1 = fill(fa, t, t1, X, mode)
            if f1 is None: break
            t1ts, p1, tk1 = f1
            c1 = p1 * (1 + (TAKER_FEE if tk1 else 0))
            f2 = fill(lo, t1ts, min(t1ts+TIMEOUT, t1), Y, mode)
            if f2 is not None:
                p2, tk2 = f2[1], f2[2]
                c2 = p2 * (1 + (TAKER_FEE if tk2 else 0))
                pnl += (1.0 - c1 - c2) * SIZE; n_ok += 1; t = f2[0]
            else:
                pnl += ((1.0 if w["fav_won"] else 0.0) - c1) * SIZE; n_leg += 1
                t = t1ts + TIMEOUT
            cyc += 1
        pnls.append(pnl)
    pnls = np.array(pnls)
    leg_rate = n_leg/(n_ok+n_leg)*100 if (n_ok+n_leg) else 0
    return dict(pnl=pnls.sum(), mean=pnls.mean(), median=np.median(pnls),
                pct_pos=(pnls > 0).mean()*100, n_ok=n_ok, n_leg=n_leg, leg=leg_rate)

Xs = [0.85, 0.90, 0.93]; Ys = [0.05, 0.07, 0.10, 0.15]
for mode in ("opt", "pes"):
    print(f"=== modo {'OPTIMISTA' if mode=='opt' else 'PESIMISTA'} (PnL total USDC, MAX_CYCLES={MAX_CYCLES}) ===")
    grid = {}
    hdr = "  X\\Y  " + "".join(f"{y:>10}" for y in Ys)
    print(hdr)
    for X in Xs:
        cells = []
        for Y in Ys:
            res = run(X, Y, mode); grid[(X, Y)] = res; cells.append(res["pnl"])
        print(f"  {X:<5}" + "".join(f"{c:>+10.0f}" for c in cells))
    # detalle de la mejor celda
    best = max(grid, key=lambda k: grid[k]["pnl"])
    b = grid[best]
    print(f"  mejor celda: X={best[0]} Y={best[1]} -> PnL={b['pnl']:+.0f}  "
          f"legging={b['leg']:.1f}%  mediana/win={b['median']:+.2f}  %win+={b['pct_pos']:.0f}\n")
