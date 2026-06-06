"""Exp6 — Edge condicional al REGIMEN (idea de Pedro).
Test de eficiencia condicional: el residual (outcome - precio) en t*=60s
no debe correlacionar con NINGUNA variable de regimen conocida en t*.
Si corr != 0 robusto -> candidato a edge condicional (a validar fuera de muestra).

Regimenes ex-ante (todos <= t*):
  - hora UTC (humanos vs bots)
  - volumen/actividad en [ts_open, t*)
  - momentum del spot (abril): (spot_at_t - price_to_beat)/ptb
  - volatilidad del spot (abril): std de spot en [ts_open, t*)
ANTI-OVERFIT: esto es TRAIN/exploratorio. Cualquier senal -> validar en holdout/ETH-SOL.
"""
import duckdb, numpy as np, pandas as pd
duckdb.sql("SET enable_progress_bar=false")
TICKS = "data/raw/pm_ticks.parquet"; RES = "data/processed/research_dataset_v1.parquet"
pd.set_option('display.width',220)

q = f"""
WITH w AS (SELECT window_id, epoch(ts_open)::BIGINT t0, price_to_beat ptb, outcome win_out FROM '{RES}'),
tk AS (
  SELECT w.window_id, w.ptb, w.win_out, w.t0,
         t.timestamp_ms/1000.0 ts, t.price px, t.outcome side, t.size_usdc sz, t.spot_price_usdt spot
  FROM '{TICKS}' t
  JOIN w ON t.timestamp_ms/1000.0 >= w.t0 AND t.timestamp_ms/1000.0 < w.t0+60),
agg AS (
  SELECT window_id, any_value(ptb) ptb, any_value(win_out) win_out, any_value(t0) t0,
    arg_max(px,ts) FILTER(WHERE side='Up') up_px,
    SUM(sz) vol60, COUNT(*) n60,
    arg_max(spot,ts) FILTER(WHERE spot>0) spot_t,
    stddev(spot) FILTER(WHERE spot>0) spot_std,
    COUNT(*) FILTER(WHERE spot>0) n_spot
  FROM tk GROUP BY window_id)
SELECT * FROM agg WHERE up_px IS NOT NULL
"""
df = duckdb.sql(q).df()
df["y"] = (df.win_out == "Up").astype(int)
df["resid"] = df.y - df.up_px            # >0 => precio subvalora Up (edge comprar Up)
df["hour"] = (pd.to_datetime(df.t0, unit="s", utc=True)).dt.hour
df["lvol"] = np.log1p(df.vol60)
df["mom"] = (df.spot_t - df.ptb) / df.ptb            # abril
df["volat"] = df.spot_std / df.spot_t                 # abril
print(f"n total={len(df)}  | con spot (abril)={df.spot_t.notna().sum()}")
print(f"calibracion global: mean(resid)={df.resid.mean():+.4f}  (debe ser ~0 si eficiente)\n")

def corr_test(col, sub=None):
    d = df if sub is None else df[sub]
    d = d[d[col].notna()]
    if len(d) < 30: return None
    r = np.corrcoef(d[col], d.resid)[0,1]
    # significancia aprox
    t = r*np.sqrt((len(d)-2)/(1-r**2+1e-12))
    return len(d), r, t

print("=== corr(residual, variable de regimen) ===")
print("  (|t|>2 ~ significativo; corr ALTA y robusta = candidato a edge condicional)")
for col in ["hour","lvol","mom","volat"]:
    res = corr_test(col)
    if res: print(f"  {col:8s}: n={res[0]:4d}  corr={res[1]:+.3f}  t={res[2]:+.1f}")

print("\n=== bias de calibracion por bin de regimen (mean resid) ===")
for col, bins in [("hour",[0,6,12,18,24]), ("lvol",4), ("mom",5), ("volat",4)]:
    d = df[df[col].notna()].copy()
    if len(d) < 50: continue
    try:
        d["b"] = pd.cut(d[col], bins) if isinstance(bins,list) else pd.qcut(d[col], bins, duplicates="drop")
    except Exception: continue
    g = d.groupby("b", observed=True).agg(n=("resid","size"), bias=("resid","mean")).reset_index()
    g["bias_pp"] = (g.bias*100).round(1)
    print(f"\n  -- {col} --")
    print(g[["b","n","bias_pp"]].to_string(index=False))
