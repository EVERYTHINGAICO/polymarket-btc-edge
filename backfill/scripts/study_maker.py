"""Exp5 — Estudio del lado MAKER (cobrar spread vs seleccion adversa).

Mide el PnL REALIZADO del maker usando fills reales (ticks) + outcomes reales.
Cada trade: el maker esta del lado OPUESTO al tomador (side).
  taker BUY  token @p -> maker VENDE -> pnl = p - win_token
  taker SELL token @p -> maker COMPRA -> pnl = win_token - p
win_token = 1 si ese token (Up/Down) fue el outcome ganador.

PASO 0: verificar que side = lado del TOMADOR (BUY cerca del ask, SELL del bid),
        comparando contra el orderbook. Si no, el signo se invierte.
PASO 1: PnL maker agregado por dolar de volumen (headline: gana o no).

maker fee = 0 (Polymarket). Sin fee de maker -> mejor caso para el maker.
"""
import duckdb, numpy as np

duckdb.sql("SET enable_progress_bar=false")
TICKS = "data/raw/pm_ticks.parquet"
RES = "data/processed/research_dataset_v1.parquet"
OB = "data/interim/orderbook_btc15m_snapshots.parquet"

# PASO 0 — verificar semantica de 'side' contra el orderbook (muestra)
print("=== PASO 0: verificar que side = lado del TOMADOR ===")
q0 = f"""
WITH ob AS (
  SELECT window_id, ts_ms, best_bid_up, best_ask_up FROM '{OB}'
  WHERE best_bid_up IS NOT NULL AND best_ask_up IS NOT NULL
),
tk AS (
  SELECT t.timestamp_ms, t.price, t.side, t.market_id,
         s.window_id, s.ts_open
  FROM '{TICKS}' t
  JOIN (SELECT DISTINCT window_id, market_id, epoch(ts_open)::BIGINT ts_open,
               epoch(ts_close)::BIGINT ts_close FROM '{OB}') s
    ON t.market_id = s.market_id
   AND t.timestamp_ms/1000.0 >= s.ts_open AND t.timestamp_ms/1000.0 < s.ts_close
  WHERE t.outcome = 'Up'
  USING SAMPLE 20000 ROWS
),
joined AS (
  SELECT tk.side, tk.price,
    (SELECT ob.best_bid_up FROM ob WHERE ob.window_id=tk.window_id AND ob.ts_ms <= tk.timestamp_ms
       ORDER BY ob.ts_ms DESC LIMIT 1) bid,
    (SELECT ob.best_ask_up FROM ob WHERE ob.window_id=tk.window_id AND ob.ts_ms <= tk.timestamp_ms
       ORDER BY ob.ts_ms DESC LIMIT 1) ask
  FROM tk
)
SELECT side,
  COUNT(*) n,
  AVG(CASE WHEN ask>bid THEN (price-bid)/(ask-bid) END) pos_en_spread
FROM joined WHERE bid IS NOT NULL AND ask>bid GROUP BY side
"""
import pandas as pd
print(duckdb.sql(q0).df().to_string(index=False))
print("  (pos_en_spread ~1 => en el ask; ~0 => en el bid. BUY debe dar ~1, SELL ~0)")
print()

# PASO 1 — PnL maker agregado (todo el set ticks+outcome via time-join)
print("=== PASO 1: PnL MAKER realizado (todos los fills reales) ===")
q1 = f"""
WITH w AS (SELECT window_id, epoch(ts_open)::BIGINT t0, epoch(ts_close)::BIGINT t1, outcome win_out FROM '{RES}'),
tk AS (
  SELECT t.price, t.side, t.size_usdc sz, t.outcome tok, w.win_out
  FROM '{TICKS}' t
  JOIN w ON t.timestamp_ms/1000.0 >= w.t0 AND t.timestamp_ms/1000.0 < w.t1
)
SELECT
  COUNT(*) n_fills,
  SUM(sz) vol,
  -- pnl maker por share: taker BUY -> p - win ; taker SELL -> win - p
  SUM(sz * (CASE WHEN side='BUY' THEN price - (CASE WHEN tok=win_out THEN 1 ELSE 0 END)
                 ELSE (CASE WHEN tok=win_out THEN 1 ELSE 0 END) - price END)) pnl_maker
FROM tk
"""
r = duckdb.sql(q1).fetchone()
n, vol, pnl = r
print(f"  fills: {n:,}   volumen: {vol:,.0f} USDC")
print(f"  PnL maker total: {pnl:,.0f} USDC")
print(f"  PnL maker por $ de volumen: {pnl/vol*100:+.3f}%   (>0 = making rentable, fee maker=0)")
print(f"  [check] PnL tomador (antes de fee) por $: {-pnl/vol*100:+.3f}%  + fee 1.8% que paga aparte")
