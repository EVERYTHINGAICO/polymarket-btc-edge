"""Traza detallada de unas ventanas para VER la mecanica del backtest.
Muestra: favorito/longshot, fill de leg1 (precio, taker/maker), intento leg2,
por que no llena, outcome y PnL. Para verificar que no hay bug."""
import numpy as np, pandas as pd
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
X, Y, SIZE, TIMEOUT, TAKER_FEE = 0.90, 0.07, 10, 30, 0.018

uni = pd.read_parquet(ROOT/"data/interim/backtest_universe.parquet")
tk = pd.read_parquet(ROOT/"data/interim/trades_bt.parquet"); tk["ts"]=tk.ts_ms/1000.0
ob = pd.read_parquet(ROOT/"data/interim/ob_bt.parquet")
tk_by={m:g for m,g in tk.groupby("market_id")}; ob_by={m:g for m,g in ob.groupby("market_id")}

def state(o,t):
    s=o.sec.values; i=np.searchsorted(s,t,"right")-1
    if i<0: return None
    return o.best_bid.values[i], o.best_ask.values[i], o.best_bid_size.values[i]

for r in uni.head(6).itertuples(index=False):
    m=r.market_id; t0,t1=r.ts_open,r.ts_close
    g=tk_by[m]; gw=g[(g.ts>=t0)&(g.ts<t1)]; o=ob_by[m]
    oU=o[(o.outcome=="Up")&(o.sec<=t0)]; oD=o[(o.outcome=="Down")&(o.sec<=t0)]
    sU=state(oU,t0); sD=state(oD,t0)
    bU=sU[0] if sU else 0; bD=sD[0] if sD else 0
    fav="Up" if bU>=bD else "Down"; lon="Down" if fav=="Up" else "Up"
    print(f"\n--- window {r.window_id[:14]} outcome={r.outcome} ---")
    print(f"  al abrir: Up(bid={bU:.2f}) Down(bid={bD:.2f}) -> FAVORITO={fav}, LONGSHOT={lon}")
    # estado libro favorito y longshot al abrir
    of=oU if fav=="Up" else oD; ol=oU if lon=="Up" else oD
    sf=state(of,t0); sl=state(ol,t0)
    print(f"  libro FAV {fav}: bid={sf[0]:.2f} ask={sf[1]:.2f}  | LONG {lon}: bid={sl[0]:.2f} ask={sl[1]:.2f}")
    # leg1: comprar favorito @ X=0.90 -> marketable?
    if sf[1]>0 and sf[1]<=X:
        print(f"  LEG1 buy {fav}@{X}: ask={sf[1]:.2f}<=0.90 -> CRUZA, fill TAKER a {sf[1]:.2f} (+fee). costo={sf[1]*(1+TAKER_FEE):.3f}")
    else:
        print(f"  LEG1 buy {fav}@{X}: ask={sf[1]:.2f}>0.90 -> pasivo (espera SELL<=0.90)")
    # leg2: longshot @ Y=0.07 -> hay SELLs del longshot a <=0.07?
    gl=gw[gw.outcome==lon]
    sells_low=gl[(gl.side=="SELL")&(gl.price<=Y)]
    print(f"  LEG2 buy {lon}@{Y}: ask longshot={sl[1]:.2f}. SELLs del longshot a <=0.07 en toda la ventana: {len(sells_low)}")
    print(f"     -> {'LLENA' if len(sells_low)>0 else 'NUNCA LLENA (no hay vendedores tan baratos)'}")
