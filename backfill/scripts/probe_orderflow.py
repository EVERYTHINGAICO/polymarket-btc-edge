"""Sonda: poder predictivo del flujo de ordenes (tick side+size), incremental sobre el precio.
Flujo neto sobre Up en [ts_open, ts_open+60): BUY_up - SELL_up.
NO concluyente por si solo; mide si el flujo agrega info mas alla del precio."""
import duckdb, numpy as np, pandas as pd

duckdb.sql("SET enable_progress_bar=false")
TICKS = "data/raw/pm_ticks.parquet"
RES = "data/processed/research_dataset_v1.parquet"

q = f"""
WITH w AS (SELECT window_id, epoch(ts_open)::BIGINT t0, outcome win_out FROM '{RES}'),
tk AS (SELECT w.window_id, w.win_out, t.timestamp_ms/1000.0 ts, t.price px,
              t.outcome side, t.side bs, t.size_usdc sz
       FROM '{TICKS}' t
       JOIN w ON t.timestamp_ms/1000.0 >= w.t0 AND t.timestamp_ms/1000.0 < w.t0+60),
agg AS (SELECT window_id, any_value(win_out) win_out,
          arg_max(px,ts) FILTER(WHERE side='Up') up_px,
          SUM(sz) FILTER(WHERE side='Up' AND bs='BUY') buy_up,
          SUM(sz) FILTER(WHERE side='Up' AND bs='SELL') sell_up
        FROM tk GROUP BY window_id)
SELECT * FROM agg WHERE up_px IS NOT NULL AND buy_up IS NOT NULL AND sell_up IS NOT NULL
"""
df = duckdb.sql(q).df()
df["net"] = df.buy_up - df.sell_up
df["netpct"] = (df.buy_up - df.sell_up) / (df.buy_up + df.sell_up + 1e-9)
y = (df.win_out == "Up").astype(int).values
print(f"n={len(df)}")
acc_flow = ((df.net > 0).astype(int).values == y).mean() * 100
print(f"(a) sign(flujo neto Up) predice outcome: {acc_flow:.2f}%")
print(f"    corr(netpct, outcome): {np.corrcoef(df.netpct.values, y)[0,1]:+.3f}")
print(f"    corr(netpct, precio) : {np.corrcoef(df.netpct.values, df.up_px.values)[0,1]:+.3f}  (alto=redundante con precio)")
print()
print("(b) INCREMENTAL: dentro de cada bin de precio, P(Up) real segun signo del flujo:")
df["pb"] = pd.cut(df.up_px, [0, .45, .55, 1.01], right=False, labels=["<0.45", "0.45-0.55", ">0.55"])
for b, g in df.groupby("pb", observed=True):
    hi = g[g.net > 0]; lo = g[g.net <= 0]
    if len(hi) > 10 and len(lo) > 10:
        ph = (hi.win_out == "Up").mean() * 100
        pl = (lo.win_out == "Up").mean() * 100
        print(f"  precio {str(b):10s}: flujo+ -> Up {ph:.1f}% (n={len(hi)}) | "
              f"flujo- -> Up {pl:.1f}% (n={len(lo)})  delta={ph-pl:+.1f}pp")
