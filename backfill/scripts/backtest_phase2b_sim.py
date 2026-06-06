"""Backtest Fases 2b+3+4 — Simulador event-driven + modelo de fill + estrategia.

Estrategia de dos patas (interpretacion coherente):
  leg1 = comprar el FAVORITO (token de mayor bid) a precio X (limit)
  leg2 = tras fill de leg1, comprar el LONGSHOT a precio Y (limit), deadline = t1+timeout
  ambos llenan -> set completo, paga 1.00, profit = 1 - costo
  leg2 no llena en timeout -> RISK RULE: aguantar leg1 hasta resolucion (legging)
  repetir ciclos hasta min_sec_before_close.

Modelo de fill (L1, banda explicita):
  - marketable: si ask(token) <= P al postear -> fill TAKER a ask (fee 1.8%)
  - pasivo: descansa a P. Llena cuando vol tomador-SELL acumulado a precio<=P
    supera queue_ahead. PESIMISTA queue_ahead=best_bid_size al postear; OPTIMISTA=0.
    fill pasivo a precio P, fee maker 0.
ANTI-LOOKAHEAD: en t solo se usan eventos con ts<=t (por construccion del replay).

Uso: py scripts/backtest_phase2b_sim.py [X Y size timeout min_close]
"""
import sys, numpy as np, pandas as pd
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

UNI = ROOT/"data/interim/backtest_universe.parquet"
TK  = ROOT/"data/interim/trades_bt.parquet"
OB  = ROOT/"data/interim/ob_bt.parquet"
TAKER_FEE = 0.018

# parametros (base)
X = float(sys.argv[1]) if len(sys.argv)>1 else 0.90   # precio favorito
Y = float(sys.argv[2]) if len(sys.argv)>2 else 0.07   # precio longshot
SIZE = float(sys.argv[3]) if len(sys.argv)>3 else 10  # shares por pata
TIMEOUT = float(sys.argv[4]) if len(sys.argv)>4 else 30   # seg para leg2
MIN_CLOSE = float(sys.argv[5]) if len(sys.argv)>5 else 60  # no postear si falta < esto

print(f"Params: X(fav)={X} Y(long)={Y} size={SIZE} timeout={TIMEOUT}s min_close={MIN_CLOSE}s")

uni = pd.read_parquet(UNI)
tk = pd.read_parquet(TK)
ob = pd.read_parquet(OB)
tk["ts"] = tk.ts_ms/1000.0
# indexar por market
tk_by = {m: g for m, g in tk.groupby("market_id")}
ob_by = {m: g for m, g in ob.groupby("market_id")}

def book_arrays(g):
    """por token (outcome): arrays sec, bid, ask, bidsize ordenados."""
    out = {}
    for oc, gg in g.groupby("outcome"):
        gg = gg.sort_values("sec")
        out[oc] = (gg.sec.values, gg.best_bid.values, gg.best_ask.values,
                   gg.best_bid_size.values)
    return out

def state_at(arr, t):
    """ultimo estado del libro con sec<=t. arr=(sec,bid,ask,bidsize)."""
    secs = arr[0]
    i = np.searchsorted(secs, t, side="right") - 1
    if i < 0: return None
    return arr[1][i], arr[2][i], arr[3][i]   # bid, ask, bidsize

def try_fill(trades_tok, ob_tok, t_post, deadline, P, mode):
    """devuelve (filled, fill_ts, fill_price, is_taker). trades_tok: df del token."""
    st = state_at(ob_tok, t_post) if ob_tok is not None else None
    # marketable?
    if st is not None and st[1] is not None and st[1] <= P and st[1] > 0:
        return True, t_post, st[1], True
    # pasivo
    queue = 0.0 if mode == "opt" else (st[2] if st is not None and st[2] else 0.0)
    cum = 0.0
    m = (trades_tok.ts > t_post) & (trades_tok.ts <= deadline) & \
        (trades_tok.side == "SELL") & (trades_tok.price <= P)
    for ts, sz in zip(trades_tok.ts.values[m.values], trades_tok.size_usdc.values[m.values]):
        cum += sz
        if cum > queue:
            return True, ts, P, False
    return False, None, None, None

def sim_window(row, mode):
    m = row.market_id
    if m not in tk_by or m not in ob_by:
        return None
    g_tk = tk_by[m]; obA = book_arrays(ob_by[m])
    t0, t1 = row.ts_open, row.ts_close
    # trades por token dentro de la ventana
    tkw = g_tk[(g_tk.ts >= t0) & (g_tk.ts < t1)]
    tk_tok = {oc: gg for oc, gg in tkw.groupby("outcome")}
    # favorito al abrir = token con mayor bid
    fav, lon = "Down", "Up"
    sU = state_at(obA["Up"], t0) if "Up" in obA else None
    sD = state_at(obA["Down"], t0) if "Down" in obA else None
    bU = sU[0] if sU else 0; bD = sD[0] if sD else 0
    if bU >= bD: fav, lon = "Up", "Down"
    fav_won = (row.outcome == fav)

    pnl = 0.0; cyc_ok = 0; cyc_legged = 0
    t = t0
    while t < t1 - MIN_CLOSE:
        # leg1: comprar favorito @ X
        if fav not in tk_tok: break
        f1 = try_fill(tk_tok[fav], obA.get(fav), t, t1, X, mode)
        if not f1[0]: break
        t1ts, p1, taker1 = f1[1], f1[2], f1[3]
        cost1 = p1 * (1 + (TAKER_FEE if taker1 else 0))
        # leg2: comprar longshot @ Y, deadline t1ts+timeout
        f2 = (False,)
        if lon in tk_tok:
            f2 = try_fill(tk_tok[lon], obA.get(lon), t1ts, min(t1ts+TIMEOUT, t1), Y, mode)
        if f2[0]:
            p2, taker2 = f2[2], f2[3]
            cost2 = p2 * (1 + (TAKER_FEE if taker2 else 0))
            pnl += (1.0 - cost1 - cost2) * SIZE      # set completo paga 1
            cyc_ok += 1
            t = f2[1]
        else:
            # RISK RULE: aguantar leg1 hasta resolucion
            payoff1 = (1.0 if fav_won else 0.0)
            pnl += (payoff1 - cost1) * SIZE
            cyc_legged += 1
            t = t1ts + TIMEOUT   # tiempo consumido; podria reintentar
    return dict(window_id=row.window_id, pnl=pnl, cyc_ok=cyc_ok, cyc_legged=cyc_legged,
                fav=fav, fav_won=fav_won)

for mode in ["pes", "opt"]:
    rows = [sim_window(r, mode) for r in uni.itertuples(index=False)]
    rows = [r for r in rows if r]
    df = pd.DataFrame(rows)
    nwin = len(df)
    tot_ok = df.cyc_ok.sum(); tot_leg = df.cyc_legged.sum()
    pnl = df.pnl.sum()
    label = "PESIMISTA (back-of-queue)" if mode=="pes" else "OPTIMISTA (top-of-queue)"
    print(f"\n=== {label} ===")
    print(f"  ventanas simuladas: {nwin}")
    print(f"  ciclos completos: {tot_ok:,}  | ciclos legged (incompletos): {tot_leg:,}")
    if tot_ok+tot_leg>0:
        print(f"  tasa de legging: {tot_leg/(tot_ok+tot_leg)*100:.1f}%")
    print(f"  PnL total: {pnl:+.2f} USDC  (size={SIZE} shares/pata)")
    print(f"  PnL/ventana: medio {df.pnl.mean():+.4f}  mediana {df.pnl.median():+.4f}  "
          f"| % ventanas+: {(df.pnl>0).mean()*100:.1f}%")
    if tot_ok>0:
        print(f"  PnL si NO hubiera legging (solo completos): {tot_ok*(1-X-Y)*SIZE:+.2f} "
              f"(teorico bruto)")
