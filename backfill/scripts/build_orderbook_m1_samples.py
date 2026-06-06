"""Build 10-second M1 decision samples from clean orderbook snapshots.

Input:
  data/interim/orderbook_btc15m_snapshots.parquet

Output:
  data/interim/orderbook_m1_samples_10s.parquet

Each row is the first valid snapshot in a 10-second bucket for one market and
one side (Up/Down). This is the decision grid for M1 market-making proxy scans.

Why:
  Avoid expensive self-joins over 94M raw paired snapshots. Horizons 30/60/120s
  can be evaluated by joining bucket_s to bucket_s + horizon.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import duckdb

SNAPSHOTS = (ROOT / "data" / "interim" / "orderbook_btc15m_snapshots.parquet").as_posix()
OUT = ROOT / "data" / "interim" / "orderbook_m1_samples_10s.parquet"
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
    print("Building M1 10s samples...")
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
              mid_up AS mid,
              spread_up AS spread,
              least(bid_size_up, ask_size_up) AS book_size
            FROM '{SNAPSHOTS}'
            WHERE spread_up >= 0 AND mid_up BETWEEN 0 AND 1
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
              mid_down AS mid,
              spread_down AS spread,
              least(bid_size_down, ask_size_down) AS book_size
            FROM '{SNAPSHOTS}'
            WHERE spread_down >= 0 AND mid_down BETWEEN 0 AND 1
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
            mid,
            spread,
            book_size
          FROM ranked
          WHERE rn = 1
          ORDER BY market_id, side, bucket_s
        ) TO '{OUT.as_posix()}' (FORMAT PARQUET)
    """)
    stats = con.execute(f"""
        SELECT COUNT(*) AS n_rows,
               COUNT(DISTINCT market_id) AS n_markets,
               MIN(bucket_s) min_bucket,
               MAX(bucket_s) max_bucket,
               SUM(CASE WHEN spread < 0 THEN 1 ELSE 0 END) bad_spread,
               SUM(CASE WHEN book_size <= 0 THEN 1 ELSE 0 END) nonpositive_book_size
        FROM '{OUT.as_posix()}'
    """).fetchone()
    print(f"Saved: {OUT}")
    print(f"rows: {stats[0]:,}")
    print(f"markets: {stats[1]:,}")
    print(f"bucket_s range: {stats[2]} .. {stats[3]}")
    print(f"bad_spread: {stats[4]}")
    print(f"nonpositive_book_size: {stats[5]:,}")
    print(f"file_sha256: {file_sha256(OUT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
