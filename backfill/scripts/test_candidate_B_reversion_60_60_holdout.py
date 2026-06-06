"""Confirm one preselected B candidate on temporal holdout.

Candidate chosen from TRAIN exploration:
  H_B_REVERSION_60_60_005

Rule:
  At t=60s, if abs(pm_up_price_60 - pm_up_price_open) >= 0.05,
  predict pm_up_price reverts over the next 60s.

Metric:
  signed_move = -sign(pm_up_price_60 - pm_up_price_open)
                * (pm_up_price_120 - pm_up_price_60)

Evidence:
  - mean signed_move > 0 by one-sided t-test
  - hit_rate P(signed_move > 0) > 50% by one-sided binomtest

This tests a statistical price-path edge, not yet an executable trading edge.
Execution requires orderbook/spread validation.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import duckdb
import numpy as np
import pandas as pd
from scipy.stats import binomtest, ttest_1samp

DATASET = (ROOT / "data" / "processed" / "research_dataset_v1.parquet").as_posix()
TRAJ = (ROOT / "data" / "interim" / "pm_trajectory.parquet").as_posix()
OUT = ROOT / "reports" / "phases" / "candidate_B_reversion_60_60_holdout.json"

ENTRY_T = 60
EXIT_T = 120
THRESHOLD = 0.05
MAX_STALENESS = 90


def load_split() -> tuple[pd.DataFrame, pd.DataFrame]:
    df = duckdb.sql(f"""
        SELECT *
        FROM '{DATASET}'
        WHERE outcome IN ('Up','Down') AND n_trades_15m >= 30
        ORDER BY ts_open, window_id
    """).df()
    cutoff = int(len(df) * 0.7)
    return df.iloc[:cutoff].copy().reset_index(drop=True), df.iloc[cutoff:].copy().reset_index(drop=True)


def prices_at(df: pd.DataFrame) -> pd.DataFrame:
    ids = df[["window_id", "pm_up_price_open"]].copy()
    con = duckdb.connect()
    con.register("ids", ids)
    return con.execute(f"""
        WITH target(t_target) AS (VALUES ({ENTRY_T}), ({EXIT_T})),
        cand AS (
          SELECT tr.window_id, target.t_target, tr.t_seconds, tr.pm_up_price,
                 row_number() OVER (
                   PARTITION BY tr.window_id, target.t_target
                   ORDER BY tr.t_seconds DESC
                 ) rn
          FROM '{TRAJ}' tr
          JOIN ids ON tr.window_id = ids.window_id
          JOIN target ON tr.t_seconds <= target.t_target
        ),
        px AS (
          SELECT window_id, t_target, pm_up_price
          FROM cand
          WHERE rn = 1 AND (t_target - t_seconds) <= {MAX_STALENESS}
        )
        SELECT ids.window_id, ids.pm_up_price_open,
               max(CASE WHEN t_target={ENTRY_T} THEN pm_up_price END) p_entry,
               max(CASE WHEN t_target={EXIT_T} THEN pm_up_price END) p_exit
        FROM ids
        LEFT JOIN px ON ids.window_id = px.window_id
        GROUP BY ids.window_id, ids.pm_up_price_open
    """).df()


def evaluate(label: str, df: pd.DataFrame) -> dict:
    px = prices_at(df).dropna().copy()
    px["prior_delta"] = px["p_entry"] - px["pm_up_price_open"]
    sub = px[px["prior_delta"].abs() >= THRESHOLD].copy()
    sub["pred_dir"] = -np.sign(sub["prior_delta"])
    sub["signed_move"] = sub["pred_dir"] * (sub["p_exit"] - sub["p_entry"])
    sub = sub[sub["signed_move"] != 0].copy()

    n = int(len(sub))
    if n == 0:
        return {"label": label, "n": 0}
    hits = (sub["signed_move"] > 0).astype(int)
    successes = int(hits.sum())
    b = binomtest(successes, n, 0.5, alternative="greater")
    tt = ttest_1samp(sub["signed_move"].to_numpy(), 0.0, alternative="greater")
    return {
        "label": label,
        "n": n,
        "successes": successes,
        "hit_rate": float(successes / n),
        "binom_p_greater": float(b.pvalue),
        "mean_gross_move": float(sub["signed_move"].mean()),
        "median_gross_move": float(sub["signed_move"].median()),
        "total_gross_move": float(sub["signed_move"].sum()),
        "ttest_p_greater": float(tt.pvalue),
        "max_roundtrip_cost_to_break_even": float(sub["signed_move"].mean()),
        "coverage_after_price_availability": int(len(px)),
    }


def main() -> int:
    train, holdout = load_split()
    result = {
        "candidate": "H_B_REVERSION_60_60_005",
        "rule": {
            "entry_t_seconds": ENTRY_T,
            "exit_t_seconds": EXIT_T,
            "threshold_abs_move_from_open": THRESHOLD,
            "prediction": "reversion",
            "max_staleness_seconds": MAX_STALENESS,
        },
        "run_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "train": evaluate("train", train),
        "holdout": evaluate("holdout", holdout),
        "interpretation": (
            "Statistical path edge only. A tradable edge requires orderbook "
            "roundtrip cost below max_roundtrip_cost_to_break_even."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    print(f"\nSaved: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
