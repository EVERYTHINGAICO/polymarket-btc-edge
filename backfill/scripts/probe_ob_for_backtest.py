"""Feasibility: estructura/frecuencia del orderbook para simular fills de limit orders.
Decide la validez del backtest de la estrategia de dos patas (NO@X / YES@Y)."""
import duckdb
duckdb.sql("SET enable_progress_bar=false")
OBR = "data/raw/orderbook/btc15m_orderbook_part0.parquet"
import pandas as pd; pd.set_option('display.width',200)

print("=== columnas raw orderbook ===")
print(duckdb.sql(f"SELECT * FROM '{OBR}' LIMIT 0").columns)

print("\n=== ambos tokens (YES/NO) por market? ===")
print(duckdb.sql(f"""
SELECT outcome, COUNT(*) filas, COUNT(DISTINCT token_id) tokens
FROM '{OBR}' GROUP BY 1""").df().to_string(index=False))

print("\n=== frecuencia de updates (event-level vs snapshot)? muestra de 1 market ===")
r = duckdb.sql(f"""
WITH one AS (
  SELECT ts_ms FROM '{OBR}'
  WHERE market_id = (SELECT market_id FROM '{OBR}' LIMIT 1)
    AND token_id = (SELECT token_id FROM '{OBR}' LIMIT 1) ),
g AS (SELECT ts_ms - lag(ts_ms) OVER (ORDER BY ts_ms) d FROM one)
SELECT (SELECT COUNT(*) FROM one) n_updates,
  (SELECT (MAX(ts_ms)-MIN(ts_ms))/1000.0 FROM one) dur_s,
  median(d) median_gap_ms, min(d) min_gap_ms
FROM g WHERE d IS NOT NULL
""").df()
print(r.to_string(index=False))

print("\n=== updates por market (todo el dataset) ===")
print(duckdb.sql(f"""
WITH m AS (SELECT market_id, COUNT(*) n FROM '{OBR}' GROUP BY 1)
SELECT median(n) mediana_updates_por_market, min(n) minimo, max(n) maximo,
  AVG(n) media FROM m""").df().to_string(index=False))

print("\n=== best_bid_size presente? (para queue/capacity) ===")
print(duckdb.sql(f"""
SELECT
  AVG(CASE WHEN best_bid_size IS NOT NULL THEN 1.0 ELSE 0 END)*100 pct_bid_size,
  AVG(CASE WHEN best_ask_size IS NOT NULL THEN 1.0 ELSE 0 END)*100 pct_ask_size,
  AVG(CASE WHEN local_recv_ts_ns IS NOT NULL THEN 1.0 ELSE 0 END)*100 pct_latency_ts
FROM '{OBR}' USING SAMPLE 100000 ROWS""").df().to_string(index=False))
