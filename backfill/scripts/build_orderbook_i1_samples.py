"""Build 10-second enriched samples for I1 orderbook imbalance tests.

Input:
  data/interim/orderbook_btc15m_snapshots.parquet

Output:
  data/interim/orderbook_i1_samples_10s.parquet

Each row is the first valid snapshot in a 10-second bucket for one market and
one token side. Unlike the M1 sample table, this keeps bid/ask prices and sizes
so imbalance rules can be tested without re-reading the 94M snapshot table.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import duckdb

SNAPSHOTS = (ROOT / "data" / "interim" / "orderbook_btc15m_snapshots.parquet").as_posix()
OUT = ROOT / "data" / "interim" / "orderbook_i1_samples_10s.parquet"
SAMPLE_STEP_S = 10


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 24), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("SET threads TO 4")
    print("Building I1 10s enriched samples...")
    con.execute(f"""
        COPY (
          WITH token_rows AS (
            SELECT
              window_id,
              market_id,
              ts_open,
              ts_close,
              ts_ms,
              CAST(floor((900.0 - time_to_close_s) / {SAMPLE_STEP_S}) * {SAMPLE_STEP_S} AS INTEGER) AS bucket_s,
              time_to_close_s,
              'Up' AS side,
              best_bid_up AS best_bid,
              best_ask_up AS best_ask,
              bid_size_up AS bid_size,
              ask_size_up AS ask_size,
              mid_up AS mid,
              spread_up AS spread
            FROM '{SNAPSHOTS}'
            WHERE spread_up >= 0
              AND mid_up BETWEEN 0 AND 1
              AND best_bid_up BETWEEN 0 AND 1
              AND best_ask_up BETWEEN 0 AND 1
            UNION ALL
            SELECT
              window_id,
              market_id,
              ts_open,
              ts_close,
              ts_ms,
              CAST(floor((900.0 - time_to_close_s) / {SAMPLE_STEP_S}) * {SAMPLE_STEP_S} AS INTEGER) AS bucket_s,
              time_to_close_s,
              'Down' AS side,
              best_bid_down AS best_bid,
              best_ask_down AS best_ask,
              bid_size_down AS bid_size,
              ask_size_down AS ask_size,
              mid_down AS mid,
              spread_down AS spread
            FROM '{SNAPSHOTS}'
            WHERE spread_down >= 0
              AND mid_down BETWEEN 0 AND 1
              AND best_bid_down BETWEEN 0 AND 1
              AND best_ask_down BETWEEN 0 AND 1
          ),
          ranked AS (
            SELECT *,
                   row_number() OVER (
                     PARTITION BY market_id, side, bucket_s
                     ORDER BY ts_ms
                   ) AS rn
            FROM token_rows
            WHERE bucket_s BETWEEN 0 AND 890
          )
          SELECT
            window_id,
            market_id,
            ts_open,
            ts_close,
            ts_ms,
            bucket_s,
            time_to_close_s,
            side,
            best_bid,
            best_ask,
            bid_size,
            ask_size,
            mid,
            spread,
            least(bid_size, ask_size) AS book_size,
            CASE
              WHEN bid_size + ask_size > 0
              THEN (bid_size - ask_size) / (bid_size + ask_size)
              ELSE NULL
            END AS size_imbalance
          FROM ranked
          WHERE rn = 1
          ORDER BY market_id, side, bucket_s
        ) TO '{OUT.as_posix()}' (FORMAT PARQUET)
    """)
    stats = con.execute(f"""
        SELECT
          COUNT(*) AS n_rows,
          COUNT(DISTINCT market_id) AS n_markets,
          MIN(bucket_s) AS min_bucket,
          MAX(bucket_s) AS max_bucket,
          SUM(CASE WHEN size_imbalance IS NULL THEN 1 ELSE 0 END) AS null_imbalance,
          SUM(CASE WHEN book_size <= 0 THEN 1 ELSE 0 END) AS nonpositive_book_size
        FROM '{OUT.as_posix()}'
    """).fetchone()
    print(f"Saved: {OUT}")
    print(f"rows: {stats[0]:,}")
    print(f"markets: {stats[1]:,}")
    print(f"bucket_s range: {stats[2]} .. {stats[3]}")
    print(f"null_imbalance: {stats[4]:,}")
    print(f"nonpositive_book_size: {stats[5]:,}")
    print(f"file_sha256: {file_sha256(OUT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
