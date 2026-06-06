"""S1 structural arbitrage scan: ask_up + ask_down < 1.

This targets the kind of edge that successful Polymarket bots are more likely
to exploit: orderbook structure, not directional prediction.

Definition:
  If both legs can be bought at best asks and ask_up + ask_down < 1, the gross
  payoff at resolution is locked at 1. Gross edge = 1 - sum_asks.

Caveat:
  This script measures displayed best asks. It does NOT prove both legs could
  be filled atomically, nor latency/cancel risk. Treat it as edge discovery.

Data coverage:
  The aliplayer1 BTC-15m orderbook partition starts around 2026-03-30, so this
  script creates a separate temporal split inside the orderbook-covered period.

Usage:
  py scripts/scan_orderbook_arbitrage_s1.py --on train
  py scripts/scan_orderbook_arbitrage_s1.py --on holdout
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import duckdb

DATASET = (ROOT / "data" / "processed" / "research_dataset_v1.parquet").as_posix()
WINDOWS = (ROOT / "data" / "raw" / "polymarket_markets_btc15m.parquet").as_posix()
REPORT_DIR = ROOT / "reports" / "phases"
LOCAL_ORDERBOOK = ROOT / "data" / "raw" / "orderbook" / "btc15m_orderbook_part0.parquet"

# Observed range of part-0 parquet: 2026-03-30 05:10:41.416 UTC onward.
ORDERBOOK_START_MS = 1774847441416
ORDERBOOK_PATH = LOCAL_ORDERBOOK.as_posix()


def split_where(on: str) -> str:
    if on == "all":
        return "TRUE"
    if on == "train":
        return "rn <= floor(n * 0.7)"
    if on == "holdout":
        return "rn > floor(n * 0.7)"
    raise ValueError(on)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--on", choices=["train", "holdout", "all"], default="train")
    ap.add_argument("--limit-windows", type=int, default=None)
    ap.add_argument("--fee-rate", type=float, default=0.07)
    ap.add_argument("--min-gross-edge", type=float, default=0.0)
    ap.add_argument("--retries", type=int, default=5)
    ap.add_argument("--retry-sleep", type=float, default=60.0)
    args = ap.parse_args()

    if not LOCAL_ORDERBOOK.exists():
        raise FileNotFoundError(
            f"Local orderbook not found: {LOCAL_ORDERBOOK}. "
            "Run scripts/download_orderbook_part0.py first."
        )

    limit_clause = f"LIMIT {args.limit_windows}" if args.limit_windows else ""
    where_split = split_where(args.on)
    gross_threshold = 1.0 - args.min_gross_edge

    con = duckdb.connect()
    con.execute("SET threads TO 4")

    query = f"""
    WITH covered AS (
      SELECT d.window_id, w.market_id, d.ts_open, d.ts_close,
             row_number() OVER (ORDER BY d.ts_open, d.window_id) rn,
             count(*) OVER () n
      FROM '{DATASET}' d
      JOIN '{WINDOWS}' w ON d.window_id = w.condition_id
      WHERE d.outcome IN ('Up','Down')
        AND d.n_trades_15m >= 30
        AND epoch_ms(d.ts_open) >= {ORDERBOOK_START_MS}
    ),
    selected AS (
      SELECT * FROM covered
      WHERE {where_split}
      ORDER BY ts_open, window_id
      {limit_clause}
    ),
    ob AS (
      SELECT o.market_id, o.ts_ms, o.outcome, o.best_ask, o.best_ask_size
      FROM '{ORDERBOOK_PATH}' o
      JOIN selected s ON o.market_id = s.market_id
      WHERE o.ts_ms >= epoch_ms(s.ts_open)
        AND o.ts_ms < epoch_ms(s.ts_close)
    ),
    snap AS (
      SELECT market_id, ts_ms,
             min(CASE WHEN outcome='Up' THEN best_ask END) ask_up,
             min(CASE WHEN outcome='Down' THEN best_ask END) ask_down,
             min(CASE WHEN outcome='Up' THEN best_ask_size END) ask_up_size,
             min(CASE WHEN outcome='Down' THEN best_ask_size END) ask_down_size
      FROM ob
      GROUP BY market_id, ts_ms
    ),
    paired AS (
      SELECT *,
             ask_up + ask_down AS sum_ask,
             1.0 - (ask_up + ask_down) AS gross_edge,
             1.0 - (ask_up + ask_down) * (1.0 + {args.fee_rate}) AS conservative_net_edge,
             least(ask_up_size, ask_down_size) AS displayed_pair_capacity
      FROM snap
      WHERE ask_up IS NOT NULL AND ask_down IS NOT NULL
    )
    SELECT
      (SELECT count(*) FROM covered) AS covered_windows_total,
      (SELECT count(*) FROM selected) AS selected_windows,
      (SELECT min(ts_open) FROM selected) AS selected_min_ts,
      (SELECT max(ts_open) FROM selected) AS selected_max_ts,
      count(*) AS paired_snapshots,
      count(DISTINCT market_id) AS markets_with_paired_snapshots,
      count(*) FILTER (WHERE sum_ask < 1.0) AS gross_arb_snapshots,
      count(DISTINCT market_id) FILTER (WHERE sum_ask < 1.0) AS gross_arb_markets,
      count(*) FILTER (WHERE sum_ask < {gross_threshold}) AS threshold_arb_snapshots,
      count(*) FILTER (WHERE conservative_net_edge > 0) AS conservative_net_arb_snapshots,
      min(sum_ask) AS min_sum_ask,
      avg(sum_ask) AS avg_sum_ask,
      max(gross_edge) AS max_gross_edge,
      avg(gross_edge) FILTER (WHERE sum_ask < 1.0) AS avg_gross_edge_when_arb,
      max(conservative_net_edge) AS max_conservative_net_edge,
      max(displayed_pair_capacity) FILTER (WHERE sum_ask < 1.0) AS max_displayed_pair_capacity_when_arb,
      avg(displayed_pair_capacity) FILTER (WHERE sum_ask < 1.0) AS avg_displayed_pair_capacity_when_arb
    FROM paired
    """

    def execute_with_backoff(sql: str):
        last_error: Exception | None = None
        for attempt in range(args.retries):
            try:
                return con.execute(sql).fetchdf()
            except Exception as exc:
                last_error = exc
                msg = str(exc)
                if "429" not in msg and "Too Many Requests" not in msg:
                    raise
                if attempt == args.retries - 1:
                    break
                sleep_s = args.retry_sleep * (attempt + 1)
                print(f"HTTP 429 from HuggingFace; retrying in {sleep_s:.0f}s ({attempt+1}/{args.retries})...")
                time.sleep(sleep_s)
        raise last_error  # type: ignore[misc]

    result = execute_with_backoff(query).iloc[0].to_dict()

    examples_query = f"""
    WITH covered AS (
      SELECT d.window_id, w.market_id, d.ts_open, d.ts_close,
             row_number() OVER (ORDER BY d.ts_open, d.window_id) rn,
             count(*) OVER () n
      FROM '{DATASET}' d
      JOIN '{WINDOWS}' w ON d.window_id = w.condition_id
      WHERE d.outcome IN ('Up','Down')
        AND d.n_trades_15m >= 30
        AND epoch_ms(d.ts_open) >= {ORDERBOOK_START_MS}
    ),
    selected AS (
      SELECT * FROM covered
      WHERE {where_split}
      ORDER BY ts_open, window_id
      {limit_clause}
    ),
    ob AS (
      SELECT o.market_id, o.ts_ms, o.outcome, o.best_ask, o.best_ask_size
      FROM '{ORDERBOOK_PATH}' o
      JOIN selected s ON o.market_id = s.market_id
      WHERE o.ts_ms >= epoch_ms(s.ts_open)
        AND o.ts_ms < epoch_ms(s.ts_close)
    ),
    snap AS (
      SELECT market_id, ts_ms,
             min(CASE WHEN outcome='Up' THEN best_ask END) ask_up,
             min(CASE WHEN outcome='Down' THEN best_ask END) ask_down,
             min(CASE WHEN outcome='Up' THEN best_ask_size END) ask_up_size,
             min(CASE WHEN outcome='Down' THEN best_ask_size END) ask_down_size
      FROM ob GROUP BY market_id, ts_ms
    )
    SELECT market_id, ts_ms, ask_up, ask_down, ask_up+ask_down AS sum_ask,
           1.0-(ask_up+ask_down) AS gross_edge,
           least(ask_up_size, ask_down_size) AS displayed_pair_capacity
    FROM snap
    WHERE ask_up IS NOT NULL AND ask_down IS NOT NULL AND ask_up+ask_down < 1.0
    ORDER BY gross_edge DESC, displayed_pair_capacity DESC
    LIMIT 25
    """
    examples = execute_with_backoff(examples_query).to_dict(orient="records")

    report = {
        "scan": "S1_structural_arbitrage_ask_up_plus_ask_down",
        "on": args.on,
        "limit_windows": args.limit_windows,
        "fee_rate_conservative": args.fee_rate,
        "min_gross_edge": args.min_gross_edge,
        "orderbook_path": ORDERBOOK_PATH,
        "run_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "result": result,
        "top_examples": examples,
        "interpretation": {
            "gross_arb": "sum_ask < 1 is deterministic gross edge if both legs fill.",
            "conservative_net": "conservative_net_edge > 0 uses the repo's old 7% fee-on-entry model.",
            "not_proven": "No atomic fill, latency, cancellation, or order size execution proof yet.",
        },
    }
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORT_DIR / f"s1_orderbook_arbitrage_{args.on}.json"
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    print(f"\nSaved: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
