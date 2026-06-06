"""Backtest Fase 1 — Loader + reconstruccion del universo backtesteable.

Produce data/interim/backtest_universe.parquet: una fila por ventana operable,
con llaves (window_id, market_id, up/down token), tiempos (ts_open/close),
outcome autoritativo (CLOB via research_v1), y metricas QC (eventos de libro,
trades, ambos tokens presentes). NO simula nada todavia.

Bridge autoritativo: research_v1 (window_id->outcome, grid 15-min limpio)
  x snapshots (window_id<->market_id) x orderbook raw (token map + QC) x ticks (QC).

Uso: py scripts/backtest_phase1_universe.py
"""
import duckdb, hashlib, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
duckdb.sql("SET enable_progress_bar=false")

RES = "data/processed/research_dataset_v1.parquet"
SNAP = "data/interim/orderbook_btc15m_snapshots.parquet"
OBR = "data/raw/orderbook/btc15m_orderbook_part0.parquet"
TICKS = "data/raw/pm_ticks.parquet"
OUT = ROOT / "data" / "interim" / "backtest_universe.parquet"

# QC minimos
MIN_OB_EVENTS = 100   # libro suficientemente denso para simular fills
MIN_TRADES = 5        # algo de flujo tomador

print("Fase 1 — reconstruccion del universo backtesteable")
print("Bridge: research_v1 x snapshots x orderbook x ticks\n")

con = duckdb.connect()
con.execute("SET enable_progress_bar=false")

# 1) spine autoritativo: window con outcome + market_id (via snapshots)
con.execute(f"""
CREATE TEMP TABLE spine AS
SELECT r.window_id, s.market_id,
       epoch(r.ts_open)::BIGINT ts_open, epoch(r.ts_close)::BIGINT ts_close,
       r.outcome, r.price_to_beat
FROM '{RES}' r
JOIN (SELECT DISTINCT window_id, market_id FROM '{SNAP}') s USING(window_id)
""")
n_spine = con.execute("SELECT COUNT(*) FROM spine").fetchone()[0]
print(f"  spine (window con outcome+market_id): {n_spine}")

# 2) orderbook per-market: token map + QC (scan pesado 866M)
print("  escaneando orderbook (866M) para token-map + QC ...")
con.execute(f"""
CREATE TEMP TABLE ob AS
SELECT market_id,
  COUNT(*) n_ob_events,
  COUNT(*) FILTER (WHERE outcome='Up')   n_ob_up,
  COUNT(*) FILTER (WHERE outcome='Down') n_ob_down,
  any_value(token_id) FILTER (WHERE outcome='Up')   up_token,
  any_value(token_id) FILTER (WHERE outcome='Down') down_token
FROM '{OBR}'
WHERE market_id IN (SELECT market_id FROM spine)
GROUP BY market_id
""")

# 3) ticks per-market: QC
print("  escaneando ticks (20.5M) para QC ...")
con.execute(f"""
CREATE TEMP TABLE tk AS
SELECT market_id, COUNT(*) n_trades, SUM(size_usdc) vol_usdc
FROM '{TICKS}'
WHERE market_id IN (SELECT market_id FROM spine)
GROUP BY market_id
""")

# 4) manifest + flags QC
con.execute(f"""
CREATE TEMP TABLE manifest AS
SELECT s.*, ob.n_ob_events, ob.n_ob_up, ob.n_ob_down, ob.up_token, ob.down_token,
  COALESCE(tk.n_trades,0) n_trades, COALESCE(tk.vol_usdc,0) vol_usdc,
  (ob.n_ob_up>0 AND ob.n_ob_down>0) has_both_tokens,
  (ob.n_ob_events>={MIN_OB_EVENTS}) ob_denso,
  (COALESCE(tk.n_trades,0)>={MIN_TRADES}) flujo_ok
FROM spine s
LEFT JOIN ob USING(market_id)
LEFT JOIN tk USING(market_id)
""")

# 5) universo backtesteable = pasa todo QC
con.execute("""
CREATE TEMP TABLE universe AS
SELECT * FROM manifest
WHERE has_both_tokens AND ob_denso AND flujo_ok
  AND up_token IS NOT NULL AND down_token IS NOT NULL
""")

import pandas as pd; pd.set_option('display.width',200)
tot = con.execute("SELECT COUNT(*) FROM manifest").fetchone()[0]
uni = con.execute("SELECT COUNT(*) FROM universe").fetchone()[0]
print(f"\n  manifest total: {tot}")
print(f"  pasan QC (universo backtesteable): {uni}")
print("\n  motivos de descarte:")
print(con.execute("""
SELECT
  SUM(CASE WHEN NOT has_both_tokens THEN 1 ELSE 0 END) sin_2_tokens,
  SUM(CASE WHEN NOT ob_denso THEN 1 ELSE 0 END) ob_ralo,
  SUM(CASE WHEN NOT flujo_ok THEN 1 ELSE 0 END) sin_flujo
FROM manifest""").df().to_string(index=False))

print("\n  resumen del universo:")
print(con.execute("""
SELECT COUNT(*) n_win, COUNT(DISTINCT market_id) n_markets,
  strftime(to_timestamp(MIN(ts_open)),'%Y-%m-%d') desde,
  strftime(to_timestamp(MAX(ts_open)),'%Y-%m-%d') hasta,
  SUM(CASE WHEN outcome='Up' THEN 1 ELSE 0 END) n_up,
  SUM(CASE WHEN outcome='Down' THEN 1 ELSE 0 END) n_down,
  median(n_ob_events)::BIGINT med_ob_events, median(n_trades)::BIGINT med_trades
FROM universe""").df().to_string(index=False))

# 6) guardar + hash
con.execute(f"COPY (SELECT * FROM universe ORDER BY ts_open) TO '{OUT.as_posix()}' (FORMAT PARQUET)")
h = hashlib.sha256(OUT.read_bytes()).hexdigest()
print(f"\n  guardado: {OUT}")
print(f"  filas: {uni}   sha256: {h[:16]}...")
