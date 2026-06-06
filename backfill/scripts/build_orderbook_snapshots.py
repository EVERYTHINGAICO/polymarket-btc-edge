"""Fase D — Build clean BTC 15m orderbook snapshots.

Input:
  data/raw/orderbook/btc15m_orderbook_part0.parquet
  data/raw/polymarket_markets_btc15m.parquet
  data/processed/research_dataset_v1.parquet

Output:
  data/interim/orderbook_btc15m_snapshots.parquet

Purpose:
  Reduce the raw orderbook rows into one paired snapshot table per market_id/timestamp:
    best_bid_up, best_ask_up, best_bid_down, best_ask_down, sizes, mids, spreads,
    time_to_close_s.

Deterministic:
  ORDER BY market_id, ts_ms. Same inputs -> same parquet hash.

No-lookahead:
  Keeps only orderbook rows inside each market window [ts_open, ts_close).
  This table is observational; later M1 decisions at snapshot t may only use
  columns at t, while future mids are targets computed in the scanner.

Usage:
  py scripts/build_orderbook_snapshots.py
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import duckdb

RAW_ORDERBOOK = (ROOT / "data" / "raw" / "orderbook" / "btc15m_orderbook_part0.parquet").as_posix()
WINDOWS = (ROOT / "data" / "raw" / "polymarket_markets_btc15m.parquet").as_posix()
DATASET = (ROOT / "data" / "processed" / "research_dataset_v1.parquet").as_posix()
OUT = ROOT / "data" / "interim" / "orderbook_btc15m_snapshots.parquet"

# Orderbook part-0 coverage starts here. Kept explicit for auditability.
ORDERBOOK_START_MS = 1774847441416


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 24), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    if not Path(RAW_ORDERBOOK).exists():
        raise FileNotFoundError(f"Missing local orderbook: {RAW_ORDERBOOK}. Run download_orderbook_part0.py first.")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("SET threads TO 4")

    print("Building clean paired orderbook snapshots...")
    con.execute(f"""
        COPY (
          WITH eligible_windows AS (
            SELECT
              d.window_id,
              w.market_id,
              d.ts_open,
              d.ts_close,
              epoch_ms(d.ts_open) AS ts_open_ms,
              epoch_ms(d.ts_close) AS ts_close_ms
            FROM '{DATASET}' d
            JOIN '{WINDOWS}' w ON d.window_id = w.condition_id
            WHERE d.outcome IN ('Up','Down')
              AND d.n_trades_15m >= 30
              AND epoch_ms(d.ts_open) >= {ORDERBOOK_START_MS}
          ),
          raw AS (
            SELECT
              ew.window_id,
              ew.market_id,
              ew.ts_open,
              ew.ts_close,
              ob.ts_ms,
              ob.outcome,
              ob.best_bid,
              ob.best_ask,
              ob.best_bid_size,
              ob.best_ask_size
            FROM '{RAW_ORDERBOOK}' ob
            JOIN eligible_windows ew ON ob.market_id = ew.market_id
            WHERE ob.ts_ms >= ew.ts_open_ms
              AND ob.ts_ms < ew.ts_close_ms
          ),
          paired AS (
            SELECT
              window_id,
              market_id,
              any_value(ts_open) AS ts_open,
              any_value(ts_close) AS ts_close,
              ts_ms,
              min(CASE WHEN outcome='Up' THEN best_bid END) AS best_bid_up,
              min(CASE WHEN outcome='Up' THEN best_ask END) AS best_ask_up,
              min(CASE WHEN outcome='Down' THEN best_bid END) AS best_bid_down,
              min(CASE WHEN outcome='Down' THEN best_ask END) AS best_ask_down,
              min(CASE WHEN outcome='Up' THEN best_bid_size END) AS bid_size_up,
              min(CASE WHEN outcome='Up' THEN best_ask_size END) AS ask_size_up,
              min(CASE WHEN outcome='Down' THEN best_bid_size END) AS bid_size_down,
              min(CASE WHEN outcome='Down' THEN best_ask_size END) AS ask_size_down
            FROM raw
            GROUP BY window_id, market_id, ts_ms
          )
          SELECT
            window_id,
            market_id,
            ts_open,
            ts_close,
            ts_ms,
            CAST((epoch_ms(ts_close) - ts_ms) / 1000.0 AS DOUBLE) AS time_to_close_s,
            best_bid_up,
            best_ask_up,
            best_bid_down,
            best_ask_down,
            bid_size_up,
            ask_size_up,
            bid_size_down,
            ask_size_down,
            (best_bid_up + best_ask_up) / 2.0 AS mid_up,
            best_ask_up - best_bid_up AS spread_up,
            (best_bid_down + best_ask_down) / 2.0 AS mid_down,
            best_ask_down - best_bid_down AS spread_down,
            best_ask_up + best_ask_down AS sum_asks,
            least(ask_size_up, ask_size_down) AS pair_ask_capacity
          FROM paired
          WHERE best_bid_up IS NOT NULL
            AND best_ask_up IS NOT NULL
            AND best_bid_down IS NOT NULL
            AND best_ask_down IS NOT NULL
          ORDER BY market_id, ts_ms
        ) TO '{OUT.as_posix()}' (FORMAT PARQUET)
    """)

    stats = con.execute(f"""
        SELECT
          COUNT(*) AS snapshots,
          COUNT(DISTINCT market_id) AS markets,
          MIN(ts_ms) AS min_ts_ms,
          MAX(ts_ms) AS max_ts_ms,
          MIN(time_to_close_s) AS min_time_to_close_s,
          MAX(time_to_close_s) AS max_time_to_close_s,
          SUM(CASE WHEN time_to_close_s <= 0 OR time_to_close_s > 900 THEN 1 ELSE 0 END) AS bad_time_to_close,
          SUM(CASE WHEN spread_up < 0 OR spread_down < 0 THEN 1 ELSE 0 END) AS bad_spreads
        FROM '{OUT.as_posix()}'
    """).fetchone()

    print(f"Saved: {OUT}")
    print(f"snapshots: {stats[0]:,}")
    print(f"markets: {stats[1]:,}")
    print(f"min_ts_ms: {stats[2]} | max_ts_ms: {stats[3]}")
    print(f"time_to_close_s range: {stats[4]} .. {stats[5]}")
    print(f"bad_time_to_close: {stats[6]}")
    print(f"bad_spreads: {stats[7]}")
    print(f"file_sha256: {file_sha256(OUT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
