"""Backtest Fase 2a — Extraccion del stream de eventos compacto para el simulador.

De los 1.028 markets del universo, extrae:
  - trades_bt.parquet: TODOS los trades (resolucion completa; son los fills reales)
  - ob_bt.parquet: orderbook remuestreado a 1 SEGUNDO (ultimo estado por segundo)
    Simplificacion documentada: la estrategia opera en 5-120s; no modelamos
    latencia/cola sub-segundo (no tenemos los datos). 1s preserva todo lo relevante.

Salida ordenada por (market_id, ts) -> el simulador lee por-market eficiente.
Uso: py scripts/backtest_phase2a_extract.py
"""
import duckdb, hashlib
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
duckdb.sql("SET enable_progress_bar=false")

UNI = "data/interim/backtest_universe.parquet"
OBR = "data/raw/orderbook/btc15m_orderbook_part0.parquet"
TICKS = "data/raw/pm_ticks.parquet"
OUT_TK = ROOT / "data" / "interim" / "trades_bt.parquet"
OUT_OB = ROOT / "data" / "interim" / "ob_bt.parquet"

def h(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()[:16]

print("Fase 2a — extraccion del stream de eventos\n")

print("  trades (resolucion completa)...")
duckdb.sql(f"""
COPY (
  SELECT t.market_id, t.token_id, t.outcome, t.timestamp_ms ts_ms,
         t.side, t.price, t.size_usdc
  FROM '{TICKS}' t
  WHERE t.market_id IN (SELECT market_id FROM '{UNI}')
  ORDER BY t.market_id, t.timestamp_ms
) TO '{OUT_TK.as_posix()}' (FORMAT PARQUET)
""")
n_tk = duckdb.sql(f"SELECT COUNT(*) FROM '{OUT_TK.as_posix()}'").fetchone()[0]
print(f"    {n_tk:,} trades  sha256={h(OUT_TK)}")

print("  orderbook remuestreado a 1s (last state por segundo)...")
duckdb.sql(f"""
COPY (
  SELECT market_id, token_id, any_value(outcome) outcome,
         (ts_ms // 1000) sec,
         arg_max(best_bid, ts_ms)      best_bid,
         arg_max(best_ask, ts_ms)      best_ask,
         arg_max(best_bid_size, ts_ms) best_bid_size,
         arg_max(best_ask_size, ts_ms) best_ask_size
  FROM '{OBR}'
  WHERE market_id IN (SELECT market_id FROM '{UNI}')
  GROUP BY market_id, token_id, ts_ms // 1000
  ORDER BY market_id, sec
) TO '{OUT_OB.as_posix()}' (FORMAT PARQUET)
""")
n_ob = duckdb.sql(f"SELECT COUNT(*) FROM '{OUT_OB.as_posix()}'").fetchone()[0]
print(f"    {n_ob:,} filas de libro (1s)  sha256={h(OUT_OB)}")
print("\n  listo. Fase 2b: simulador event-driven sobre estos dos archivos.")
