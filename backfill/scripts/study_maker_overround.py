"""Exp5b — El edge ESTRUCTURAL del maker (vig / overround) y el spread.
Tesis del usuario: los bots estan en casi TODAS las ventanas -> debe haber
dinero consistente sin riesgo direccional. Candidato: ask_up+ask_down > 1.

Mide sobre el orderbook real (snapshots):
  overround = best_ask_up + best_ask_down - 1   (vig que cobra el que vende ambos)
  underround = 1 - (best_bid_up + best_bid_down) (lo que paga el que compra ambos)
  spread por token
Por time-to-close, para ver si el margen es estable toda la ventana."""
import duckdb
duckdb.sql("SET enable_progress_bar=false")
OB = "data/interim/orderbook_btc15m_snapshots.parquet"
import pandas as pd; pd.set_option('display.width',220)

print("=== columnas disponibles ===")
print(duckdb.sql(f"SELECT * FROM '{OB}' LIMIT 0").columns)

print("\n=== OVERROUND estructural (ask_up+ask_down-1) y spreads, por time-to-close ===")
q = f"""
WITH s AS (
  SELECT *,
    (best_ask_up + best_ask_down) - 1.0 AS overround,
    1.0 - (best_bid_up + best_bid_down) AS underround,
    (best_ask_up - best_bid_up) AS spr_up,
    (best_ask_down - best_bid_down) AS spr_down
  FROM '{OB}'
  WHERE best_ask_up IS NOT NULL AND best_ask_down IS NOT NULL
    AND best_bid_up IS NOT NULL AND best_bid_down IS NOT NULL
    AND best_ask_up>0 AND best_ask_up<1 AND best_ask_down>0 AND best_ask_down<1
)
SELECT CASE WHEN time_to_close_s<60 THEN '0-60s' WHEN time_to_close_s<300 THEN '60-300s'
            WHEN time_to_close_s<600 THEN '300-600s' ELSE '600-900s' END bucket,
  COUNT(*) n,
  median(overround)*100 overround_med_pct,
  AVG(overround)*100 overround_avg_pct,
  median(spr_up)*100 spr_up_med_pct,
  median(underround)*100 underround_med_pct,
  AVG(CASE WHEN overround>0 THEN 1.0 ELSE 0.0 END)*100 pct_overround_pos
FROM s GROUP BY 1 ORDER BY MIN(time_to_close_s)
"""
print(duckdb.sql(q).df().to_string(index=False))

print("\n=== Resumen global ===")
q2 = f"""
WITH s AS (
  SELECT (best_ask_up + best_ask_down) - 1.0 AS overround,
         (best_ask_up - best_bid_up) AS spr_up, (best_ask_down - best_bid_down) AS spr_down
  FROM '{OB}'
  WHERE best_ask_up>0 AND best_ask_up<1 AND best_ask_down>0 AND best_ask_down<1
    AND best_bid_up IS NOT NULL AND best_bid_down IS NOT NULL )
SELECT median(overround)*100 overround_med_pct,
  AVG(CASE WHEN overround>0 THEN 1.0 ELSE 0.0 END)*100 pct_pos,
  median((spr_up+spr_down)/2)*100 spread_med_pct
FROM s
"""
print(duckdb.sql(q2).df().to_string(index=False))
