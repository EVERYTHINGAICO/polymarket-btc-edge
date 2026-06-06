"""Edge de ENDGAME / latencia de resolucion (medido, no operado).
En los ultimos N seg, comprar al FAVORITO (mayor mid) al ASK REAL. fee=0.
EV = (favorito gana ? 1 : 0) - ask_favorito. Sin lookahead: el favorito se conoce en t.
Bucketea por nivel de confianza (mid del favorito) y por segundos al cierre."""
import duckdb, numpy as np, pandas as pd
duckdb.sql("SET enable_progress_bar=false")
uni = pd.read_parquet("data/interim/backtest_universe.parquet")
ob = pd.read_parquet("data/interim/ob_bt.parquet")
ob_by = {m: g for m, g in ob.groupby("market_id")}

def state(g, oc, t):
    a = g[(g.outcome == oc) & (g.sec <= t)]
    if len(a) == 0: return None
    r = a.iloc[-1]
    return r.best_bid, r.best_ask, r.best_ask_size

rows = []
for r in uni.itertuples(index=False):
    g = ob_by.get(r.market_id)
    if g is None: continue
    for ttc in (60, 30, 10):
        t = r.ts_close - ttc
        sU = state(g, "Up", t); sD = state(g, "Down", t)
        if not sU or not sD: continue
        midU = (sU[0]+sU[1])/2; midD = (sD[0]+sD[1])/2
        if midU >= midD:
            fav, ask, asksz, fav_lbl = "Up", sU[1], sU[2], "Up"
            fav_mid = midU
        else:
            fav, ask, asksz, fav_lbl = "Down", sD[1], sD[2], "Down"
            fav_mid = midD
        if ask is None or ask <= 0 or ask >= 1: continue
        rows.append(dict(ttc=ttc, fav_mid=fav_mid, ask=ask, asksz=asksz,
                         win=int(r.outcome == fav)))
df = pd.DataFrame(rows)
df["ev"] = df.win - df.ask  # fee 0

for ttc in (60, 30, 10):
    d = df[df.ttc == ttc]
    print(f"=== ultimos {ttc}s al cierre (n={len(d)}) ===")
    print(f"  comprar favorito al ask: EV medio {d.ev.mean():+.4f}  acc {d.win.mean()*100:.1f}%  ask medio {d.ask.mean():.3f}")
    # por nivel de confianza del favorito
    for lo, hi in [(0.5,0.7),(0.7,0.85),(0.85,0.95),(0.95,1.01)]:
        s = d[(d.fav_mid>=lo)&(d.fav_mid<hi)]
        if len(s) < 10: continue
        cap = s.asksz.median()
        print(f"    fav_mid [{lo:.2f},{hi:.2f}): n={len(s):4d}  EV={s.ev.mean():+.4f}  "
              f"acc={s.win.mean()*100:.1f}%  ask={s.ask.mean():.3f}  cap(ask_size med)={cap:.0f}")
    print()
