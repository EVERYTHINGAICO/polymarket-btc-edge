"""Exp5 — Robustez del PnL maker (+2,2%/$). Buscar artefactos:
 (a) por time-to-close: concentrado en endgame (ultimos seg) = NO es making real?
 (b) por lado del maker (vende Up a compradores ansiosos vs compra)
 (c) estabilidad temporal (1a mitad vs 2a mitad del periodo)
 (d) distribucion por ventana (outliers?)
"""
import duckdb, numpy as np

duckdb.sql("SET enable_progress_bar=false")
TICKS = "data/raw/pm_ticks.parquet"
RES = "data/processed/research_dataset_v1.parquet"

base = f"""
WITH w AS (SELECT window_id, epoch(ts_open)::BIGINT t0, epoch(ts_close)::BIGINT t1, outcome win_out FROM '{RES}'),
tk AS (
  SELECT t.price, t.side, t.size_usdc sz, t.outcome tok, w.win_out, w.window_id, w.t0,
         w.t1 - t.timestamp_ms/1000.0 AS ttc,
         sz * (CASE WHEN t.side='BUY' THEN t.price - (CASE WHEN t.outcome=w.win_out THEN 1 ELSE 0 END)
                    ELSE (CASE WHEN t.outcome=w.win_out THEN 1 ELSE 0 END) - t.price END) AS pnl
  FROM '{TICKS}' t
  JOIN w ON t.timestamp_ms/1000.0 >= w.t0 AND t.timestamp_ms/1000.0 < w.t1
)
"""

print("=== (a) PnL maker por TIME-TO-CLOSE ===")
qa = base + """
SELECT CASE WHEN ttc<30 THEN '0-30s' WHEN ttc<120 THEN '30-120s'
            WHEN ttc<300 THEN '120-300s' WHEN ttc<600 THEN '300-600s'
            ELSE '600-900s' END bucket,
  COUNT(*) n, SUM(sz) vol, SUM(pnl) pnl, SUM(pnl)/SUM(sz)*100 pnl_pct
FROM tk GROUP BY 1 ORDER BY MIN(ttc)
"""
import pandas as pd; pd.set_option('display.width',200)
print(duckdb.sql(qa).df().to_string(index=False))

print("\n=== (b) PnL maker por LADO (maker vende Up / compra Up / vende Down / compra Down) ===")
qb = base + """
SELECT tok,
  CASE WHEN side='BUY' THEN 'maker VENDE '||tok ELSE 'maker COMPRA '||tok END lado,
  COUNT(*) n, SUM(sz) vol, SUM(pnl)/SUM(sz)*100 pnl_pct
FROM tk GROUP BY tok, side ORDER BY tok, side
"""
print(duckdb.sql(qb).df().to_string(index=False))

print("\n=== (c) ESTABILIDAD temporal (mitades del periodo) ===")
qc = base + """
SELECT CASE WHEN t0 < (SELECT median(t0) FROM tk) THEN '1a mitad' ELSE '2a mitad' END half,
  COUNT(*) n, SUM(sz) vol, SUM(pnl)/SUM(sz)*100 pnl_pct
FROM tk GROUP BY 1 ORDER BY 1
"""
print(duckdb.sql(qc).df().to_string(index=False))

print("\n=== (d) DISTRIBUCION por ventana (outliers?) ===")
qd = base + """
, perwin AS (SELECT window_id, SUM(pnl) pnl_w, SUM(sz) vol_w FROM tk GROUP BY window_id)
SELECT COUNT(*) n_win,
  SUM(CASE WHEN pnl_w>0 THEN 1 ELSE 0 END)::FLOAT/COUNT(*)*100 pct_win_positivas,
  median(pnl_w/vol_w)*100 mediana_pnl_pct_win,
  AVG(pnl_w/vol_w)*100 media_pnl_pct_win
FROM perwin WHERE vol_w>0
"""
print(duckdb.sql(qd).df().to_string(index=False))
