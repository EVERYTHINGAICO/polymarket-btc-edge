"""Exp6b — El candidato HORA-DEL-DIA, prueba decisiva.
Sesgo: en horas 0-6 UTC el precio sobrevalora Up (bias -4.7pp) -> apostar DOWN.
Tests que debe pasar para no ser ruido:
 (1) EV EJECUTABLE con ask_down real del orderbook (no sintetico) > 0
 (2) estable en split temporal (1a mitad vs 2a mitad)
 (3) consistente, no 1 dia raro
ANTI-OVERFIT: candidato en TRAIN; aun pasando esto, requiere ETH/SOL virgen.
"""
import duckdb, numpy as np, pandas as pd
duckdb.sql("SET enable_progress_bar=false")
OB = "data/interim/orderbook_btc15m_snapshots.parquet"
RES = "data/processed/research_dataset_v1.parquet"
pd.set_option('display.width',200)
fee = 0.018

# orderbook en t*=60s (time_to_close>=840, el mas cercano) + outcome + hora
q = f"""
WITH ob AS (
  SELECT window_id, time_to_close_s, best_ask_up, best_ask_down, ask_size_down,
         ROW_NUMBER() OVER (PARTITION BY window_id ORDER BY time_to_close_s ASC) rn
  FROM '{OB}' WHERE time_to_close_s >= 840 AND best_ask_down IS NOT NULL)
SELECT o.window_id, o.best_ask_up, o.best_ask_down, o.ask_size_down,
       r.outcome win_out, epoch(r.ts_open)::BIGINT t0
FROM ob o JOIN '{RES}' r USING(window_id)
WHERE o.rn=1 AND o.best_ask_down>0 AND o.best_ask_down<1
"""
df = duckdb.sql(q).df()
df["hour"] = pd.to_datetime(df.t0, unit="s", utc=True).dt.hour
df["y_down"] = (df.win_out == "Down").astype(int)
df["ev_down"] = df.y_down*1.0 - df.best_ask_down*(1+fee)   # comprar Down al ask real
df["early"] = df.hour < 6

print(f"n con orderbook+hora = {len(df)}")
print(f"  ventanas hora 0-6 UTC: {df.early.sum()}\n")

print("=== EV de comprar DOWN al ASK REAL, por franja horaria ===")
for name, mask in [("0-6h (candidato)", df.early), ("6-24h (resto)", ~df.early)]:
    d = df[mask]
    print(f"  {name:18s}: n={len(d):4d}  EV_down={d.ev_down.mean():+.4f}  "
          f"Down gana={d.y_down.mean()*100:.1f}%  ask_down medio={d.best_ask_down.mean():.3f}")

print("\n=== candidato 0-6h: estabilidad temporal ===")
d = df[df.early].copy()
med = d.t0.median()
for name, mask in [("1a mitad", d.t0 < med), ("2a mitad", d.t0 >= med)]:
    s = d[mask]
    print(f"  {name}: n={len(s):3d}  EV_down={s.ev_down.mean():+.4f}  Down gana={s.y_down.mean()*100:.1f}%")

print("\n=== candidato 0-6h: por dia (no es 1 dia raro?) ===")
d["dia"] = pd.to_datetime(d.t0, unit="s", utc=True).dt.strftime("%m-%d")
g = d.groupby("dia").agg(n=("ev_down","size"), ev=("ev_down","mean")).reset_index()
print(f"  dias: {len(g)}  | dias con EV>0: {(g.ev>0).sum()}  | EV medio por dia: {g.ev.mean():+.4f}")
print(f"  EV total 0-6h: {d.ev_down.mean():+.4f}  (n={len(d)})")
