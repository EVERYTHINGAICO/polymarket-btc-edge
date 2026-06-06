"""Pilot S1: structural orderbook arbitrage by market, TRAIN only.

Hypothesis:
  There may be moments where buying both UP and DOWN at displayed best asks
  costs less than the guaranteed payoff of 1.0:

      ask_up + ask_down < 1

This pilot is deliberately small and market-level. It does NOT scan holdout and
does NOT treat correlated snapshots as independent evidence.

Outputs:
  - per-market opportunity summaries
  - per-opportunity runs (contiguous arb snapshots)
  - aggregate pilot report

Usage:
  py scripts/pilot_orderbook_arbitrage_s1.py --n-markets 100
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
import numpy as np
import pandas as pd

DATASET = (ROOT / "data" / "processed" / "research_dataset_v1.parquet").as_posix()
WINDOWS = (ROOT / "data" / "raw" / "polymarket_markets_btc15m.parquet").as_posix()
REPORT_DIR = ROOT / "reports" / "phases"
LOCAL_ORDERBOOK = ROOT / "data" / "raw" / "orderbook" / "btc15m_orderbook_part0.parquet"

# Observed BTC-15m orderbook coverage in part-0 starts around 2026-03-30 UTC.
ORDERBOOK_START_MS = 1774847441416
ORDERBOOK_PATH = LOCAL_ORDERBOOK.as_posix()


def execute_with_backoff(con: duckdb.DuckDBPyConnection, sql: str, retries: int, retry_sleep: float) -> pd.DataFrame:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            return con.execute(sql).fetchdf()
        except Exception as exc:
            last_error = exc
            msg = str(exc)
            if "429" not in msg and "Too Many Requests" not in msg:
                raise
            if attempt == retries - 1:
                break
            sleep_s = retry_sleep * (attempt + 1)
            print(f"HTTP 429 from HuggingFace; retrying in {sleep_s:.0f}s ({attempt + 1}/{retries})...")
            time.sleep(sleep_s)
    raise last_error  # type: ignore[misc]


def selected_train_markets(n_markets: int, sample: str) -> pd.DataFrame:
    """Deterministic TRAIN-only sample within orderbook-covered period."""
    df = duckdb.sql(f"""
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
        train AS (
          SELECT *, row_number() OVER (ORDER BY ts_open, window_id) train_rn,
                    count(*) OVER () train_n
          FROM covered
          WHERE rn <= floor(n * 0.7)
        )
        SELECT window_id, market_id, ts_open, ts_close, train_rn, train_n
        FROM train
        ORDER BY ts_open, window_id
    """).df()
    if sample == "first":
        return df.head(n_markets).copy()
    if sample == "spread":
        if len(df) <= n_markets:
            return df.copy()
        idx = np.linspace(0, len(df) - 1, n_markets).round().astype(int)
        return df.iloc[idx].drop_duplicates("market_id").copy().reset_index(drop=True)
    raise ValueError(sample)


def load_paired_snapshots(markets: pd.DataFrame, retries: int, retry_sleep: float) -> pd.DataFrame:
    con = duckdb.connect()
    con.execute("SET threads TO 4")
    con.register("selected", markets[["market_id", "ts_open", "ts_close"]])
    sql = f"""
        WITH ob AS (
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
        )
        SELECT *,
               ask_up + ask_down AS sum_ask,
               1.0 - (ask_up + ask_down) AS gross_edge,
               least(ask_up_size, ask_down_size) AS displayed_pair_capacity
        FROM snap
        WHERE ask_up IS NOT NULL AND ask_down IS NOT NULL
        ORDER BY market_id, ts_ms
    """
    return execute_with_backoff(con, sql, retries, retry_sleep)


def opportunity_runs(paired: pd.DataFrame, max_gap_ms: int) -> pd.DataFrame:
    arb = paired[paired["sum_ask"] < 1.0].copy()
    if len(arb) == 0:
        return pd.DataFrame(columns=[
            "market_id", "run_id", "start_ts_ms", "end_ts_ms", "duration_ms",
            "snapshots", "min_sum_ask", "max_gross_edge", "avg_gross_edge",
            "max_capacity", "avg_capacity", "break_even_fee_rate_at_best",
        ])

    arb["prev_ts"] = arb.groupby("market_id")["ts_ms"].shift(1)
    arb["new_run"] = ((arb["prev_ts"].isna()) | ((arb["ts_ms"] - arb["prev_ts"]) > max_gap_ms)).astype(int)
    arb["run_id"] = arb.groupby("market_id")["new_run"].cumsum()

    runs = arb.groupby(["market_id", "run_id"], as_index=False).agg(
        start_ts_ms=("ts_ms", "min"),
        end_ts_ms=("ts_ms", "max"),
        snapshots=("ts_ms", "count"),
        min_sum_ask=("sum_ask", "min"),
        max_gross_edge=("gross_edge", "max"),
        avg_gross_edge=("gross_edge", "mean"),
        max_capacity=("displayed_pair_capacity", "max"),
        avg_capacity=("displayed_pair_capacity", "mean"),
    )
    runs["duration_ms"] = runs["end_ts_ms"] - runs["start_ts_ms"]
    runs["break_even_fee_rate_at_best"] = (1.0 / runs["min_sum_ask"]) - 1.0
    cols = [
        "market_id", "run_id", "start_ts_ms", "end_ts_ms", "duration_ms",
        "snapshots", "min_sum_ask", "max_gross_edge", "avg_gross_edge",
        "max_capacity", "avg_capacity", "break_even_fee_rate_at_best",
    ]
    return runs[cols].sort_values(["max_gross_edge", "duration_ms", "max_capacity"], ascending=[False, False, False])


def summarize(markets: pd.DataFrame, paired: pd.DataFrame, runs: pd.DataFrame, fee_scenarios: list[float]) -> dict:
    markets_with_paired = int(paired["market_id"].nunique()) if len(paired) else 0
    markets_with_arb = int(runs["market_id"].nunique()) if len(runs) else 0
    best_sum = float(paired["sum_ask"].min()) if len(paired) else None
    report = {
        "selected_markets": int(len(markets)),
        "markets_with_paired_snapshots": markets_with_paired,
        "paired_snapshots": int(len(paired)),
        "arb_runs": int(len(runs)),
        "markets_with_arb": markets_with_arb,
        "market_level_arb_rate": float(markets_with_arb / len(markets)) if len(markets) else None,
        "min_sum_ask": best_sum,
        "max_gross_edge": float(runs["max_gross_edge"].max()) if len(runs) else 0.0,
        "median_run_duration_ms": float(runs["duration_ms"].median()) if len(runs) else 0.0,
        "max_run_duration_ms": float(runs["duration_ms"].max()) if len(runs) else 0.0,
        "max_displayed_pair_capacity": float(runs["max_capacity"].max()) if len(runs) else 0.0,
        "fee_scenarios": {},
    }
    for fee in fee_scenarios:
        # Net positive if sum_ask * (1 + fee) < 1 under a conservative entry-fee model.
        threshold = 1.0 / (1.0 + fee)
        report["fee_scenarios"][str(fee)] = {
            "required_sum_ask_below": threshold,
            "runs_net_positive": int((runs["min_sum_ask"] < threshold).sum()) if len(runs) else 0,
            "markets_net_positive": int(runs.loc[runs["min_sum_ask"] < threshold, "market_id"].nunique()) if len(runs) else 0,
        }
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-markets", type=int, default=100)
    ap.add_argument("--sample", choices=["first", "spread"], default="spread")
    ap.add_argument("--max-gap-ms", type=int, default=2000)
    ap.add_argument("--retries", type=int, default=3)
    ap.add_argument("--retry-sleep", type=float, default=60.0)
    args = ap.parse_args()

    if not LOCAL_ORDERBOOK.exists():
        raise FileNotFoundError(
            f"Local orderbook not found: {LOCAL_ORDERBOOK}. "
            "Run scripts/download_orderbook_part0.py first."
        )

    markets = selected_train_markets(args.n_markets, args.sample)
    print(f"Selected TRAIN markets: {len(markets)}")
    if len(markets):
        print(f"Range: {markets['ts_open'].min()} .. {markets['ts_open'].max()}")

    paired = load_paired_snapshots(markets, args.retries, args.retry_sleep)
    runs = opportunity_runs(paired, args.max_gap_ms)
    summary = summarize(markets, paired, runs, fee_scenarios=[0.0, 0.01, 0.02, 0.07])

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    tag = f"{args.sample}_{len(markets)}"
    paired_out = REPORT_DIR / f"s1_pilot_paired_snapshots_{tag}.csv"
    runs_out = REPORT_DIR / f"s1_pilot_arb_runs_{tag}.csv"
    report_out = REPORT_DIR / f"s1_pilot_report_{tag}.json"
    paired.to_csv(paired_out, index=False)
    runs.to_csv(runs_out, index=False)

    report = {
        "scan": "S1_pilot_orderbook_arbitrage",
        "run_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "sample": args.sample,
        "n_markets_requested": args.n_markets,
        "max_gap_ms": args.max_gap_ms,
        "orderbook_path": ORDERBOOK_PATH,
        "summary": summary,
        "top_runs": runs.head(25).to_dict(orient="records"),
        "outputs": {
            "paired_snapshots_csv": paired_out.as_posix(),
            "arb_runs_csv": runs_out.as_posix(),
        },
        "interpretation": (
            "Pilot only. Evidence is market-level. If fee_scenarios show no net-positive "
            "runs under realistic fees, S1 is not tradable without maker economics."
        ),
    }
    report_out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    print(f"\nSaved: {report_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
