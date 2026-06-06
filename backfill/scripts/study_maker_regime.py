"""Exp5 — Es el PnL maker un efecto de REGIMEN (vender Down en mercado alcista)
o un edge genuino? Y vive en las ventanas de alto volumen?"""
import duckdb
duckdb.sql("SET enable_progress_bar=false")
TICKS = "data/raw/pm_ticks.parquet"; RES = "data/processed/research_dataset_v1.parquet"

base = f"""
WITH w AS (SELECT window_id, epoch(ts_open)::BIGINT t0, epoch(ts_close)::BIGINT t1, outcome win_out FROM '{RES}'),
tk AS (
  SELECT t.outcome tok, t.side, t.size_usdc sz, w.win_out, w.window_id,
         sz * (CASE WHEN t.side='BUY' THEN t.price - (CASE WHEN t.outcome=w.win_out THEN 1 ELSE 0 END)
                    ELSE (CASE WHEN t.outcome=w.win_out THEN 1 ELSE 0 END) - t.price END) pnl
  FROM '{TICKS}' t JOIN w ON t.timestamp_ms/1000.0 >= w.t0 AND t.timestamp_ms/1000.0 < w.t1)
"""
import pandas as pd; pd.set_option('display.width',200)

# 1) balance de outcomes en el periodo (regimen)
print("=== balance Up/Down en ventanas analizadas (regimen) ===")
print(duckdb.sql(base+"""
SELECT win_out, COUNT(DISTINCT window_id) n_win FROM tk GROUP BY 1""").df().to_string(index=False))

# 2) PnL maker segun outcome de la ventana (si gana solo cuando sale Up -> direccional)
print("\n=== PnL maker por OUTCOME de la ventana ===")
print(duckdb.sql(base+"""
SELECT win_out, SUM(sz) vol, SUM(pnl)/SUM(sz)*100 pnl_pct FROM tk GROUP BY 1""").df().to_string(index=False))

# 3) PnL por quintil de volumen de ventana (vive en las de alto volumen?)
print("\n=== PnL maker por QUINTIL de volumen de la ventana ===")
print(duckdb.sql(base+"""
, perwin AS (SELECT window_id, SUM(sz) vol_w, SUM(pnl) pnl_w FROM tk GROUP BY 1),
q AS (SELECT *, ntile(5) OVER (ORDER BY vol_w) quintil FROM perwin)
SELECT quintil, COUNT(*) n_win, SUM(vol_w) vol, SUM(pnl_w)/SUM(vol_w)*100 pnl_pct,
  SUM(CASE WHEN pnl_w>0 THEN 1 ELSE 0 END)::FLOAT/COUNT(*)*100 pct_pos
FROM q GROUP BY 1 ORDER BY 1""").df().to_string(index=False))
