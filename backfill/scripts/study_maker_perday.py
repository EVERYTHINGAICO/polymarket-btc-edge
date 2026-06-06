"""Exp5 — Cuantas ventanas/dia operaria un maker y la economia diaria implicita.
Distingue: TODAS las ventanas vs solo ALTO VOLUMEN (donde vive el edge, Q4-Q5)."""
import duckdb
duckdb.sql("SET enable_progress_bar=false")
TICKS = "data/raw/pm_ticks.parquet"; RES = "data/processed/research_dataset_v1.parquet"

perwin = f"""
WITH w AS (SELECT window_id, epoch(ts_open)::BIGINT t0, epoch(ts_close)::BIGINT t1, outcome win_out FROM '{RES}'),
tk AS (
  SELECT w.window_id, w.t0,
    t.size_usdc sz,
    t.size_usdc * (CASE WHEN t.side='BUY' THEN t.price - (CASE WHEN t.outcome=w.win_out THEN 1 ELSE 0 END)
                        ELSE (CASE WHEN t.outcome=w.win_out THEN 1 ELSE 0 END) - t.price END) pnl,
    -- pnl solo del lado VENDEDOR del maker (taker BUY) = la parte rentable
    CASE WHEN t.side='BUY' THEN t.size_usdc * (t.price - (CASE WHEN t.outcome=w.win_out THEN 1 ELSE 0 END)) ELSE 0 END pnl_sell,
    CASE WHEN t.side='BUY' THEN t.size_usdc ELSE 0 END vol_sell
  FROM '{TICKS}' t JOIN w ON t.timestamp_ms/1000.0 >= w.t0 AND t.timestamp_ms/1000.0 < w.t1),
pw AS (SELECT window_id, strftime(to_timestamp(any_value(t0)),'%Y-%m-%d') dia,
         SUM(sz) vol_w, SUM(pnl) pnl_w, SUM(pnl_sell) pnl_sell_w, SUM(vol_sell) vol_sell_w
       FROM tk GROUP BY window_id),
q AS (SELECT *, ntile(5) OVER (ORDER BY vol_w) quintil FROM pw)
"""
import pandas as pd; pd.set_option('display.width',200)

print("=== Ventanas/dia disponibles en el set (research_v1 INNER ticks) ===")
r = duckdb.sql(perwin + """
SELECT COUNT(DISTINCT dia) dias, COUNT(*) n_win,
  COUNT(*)::FLOAT/COUNT(DISTINCT dia) win_por_dia FROM q""").df()
print(r.to_string(index=False))
dias = int(r.dias.iloc[0])

print("\n=== Economia AGREGADA del mercado (todos los makers juntos), por dia ===")
print(duckdb.sql(perwin + f"""
SELECT 'TODAS las ventanas' escenario, COUNT(*)/{dias}.0 win_dia,
  SUM(vol_w)/{dias}.0 vol_dia, SUM(pnl_w)/{dias}.0 pnl_dia, SUM(pnl_w)/SUM(vol_w)*100 pnl_pct
FROM q
UNION ALL
SELECT 'solo Q4-Q5 (alto vol)', COUNT(*)/{dias}.0, SUM(vol_w)/{dias}.0, SUM(pnl_w)/{dias}.0, SUM(pnl_w)/SUM(vol_w)*100
FROM q WHERE quintil>=4
UNION ALL
SELECT 'solo Q5 (top vol)', COUNT(*)/{dias}.0, SUM(vol_w)/{dias}.0, SUM(pnl_w)/{dias}.0, SUM(pnl_w)/SUM(vol_w)*100
FROM q WHERE quintil=5
UNION ALL
SELECT 'Q5 + solo lado VENDEDOR', COUNT(*)/{dias}.0, SUM(vol_sell_w)/{dias}.0, SUM(pnl_sell_w)/{dias}.0, SUM(pnl_sell_w)/SUM(vol_sell_w)*100
FROM q WHERE quintil=5
""").df().to_string(index=False))
print(f"\n(nota: PnL/dia es de TODOS los makers del mercado juntos; un maker captura una fraccion. dias={dias})")
