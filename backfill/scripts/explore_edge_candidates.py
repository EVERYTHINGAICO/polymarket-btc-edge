"""Post-EXP2 edge search, TRAIN ONLY.

Purpose:
  Find candidate hypotheses that could be tested once against the temporal
  holdout. This script does NOT evaluate holdout performance.

Angles covered with data already in hand:
  B: Polymarket pm_up_price intra-window momentum/reversion.
  V: D/V relation with realized volatility (diagnostic, not direct edge).

Rules:
  - Train = first 70% by ts_open after canonical filters.
  - Holdout is left untouched here.
  - All tests are exploratory; p-values are not final evidence after scanning.

Usage:
  py scripts/explore_edge_candidates.py
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import duckdb
import numpy as np
import pandas as pd
from scipy.stats import binomtest, spearmanr, ttest_1samp

DATASET = (ROOT / "data" / "processed" / "research_dataset_v1.parquet").as_posix()
TRAJ = (ROOT / "data" / "interim" / "pm_trajectory.parquet").as_posix()


@dataclass(frozen=True)
class SplitData:
    train_ids: set[str]
    holdout_ids: set[str]
    train: pd.DataFrame


def load_train() -> SplitData:
    df = duckdb.sql(f"""
        SELECT *
        FROM '{DATASET}'
        WHERE outcome IN ('Up','Down') AND n_trades_15m >= 30
        ORDER BY ts_open, window_id
    """).df()
    cutoff = int(len(df) * 0.7)
    train = df.iloc[:cutoff].copy().reset_index(drop=True)
    holdout = df.iloc[cutoff:].copy().reset_index(drop=True)
    return SplitData(set(train["window_id"]), set(holdout["window_id"]), train)


def prices_at_targets(train_ids: set[str], targets: list[int], max_staleness: int = 90) -> pd.DataFrame:
    """Last observed pm_up_price at or before each target second, train windows only."""
    ids = pd.DataFrame({"window_id": sorted(train_ids)})
    con = duckdb.connect()
    con.register("ids", ids)
    values = ",".join(f"({t})" for t in targets)
    return con.execute(f"""
        WITH target(t_target) AS (VALUES {values}),
        cand AS (
          SELECT tr.window_id, target.t_target, tr.t_seconds, tr.pm_up_price,
                 row_number() OVER (
                   PARTITION BY tr.window_id, target.t_target
                   ORDER BY tr.t_seconds DESC
                 ) AS rn
          FROM '{TRAJ}' tr
          JOIN ids ON tr.window_id = ids.window_id
          JOIN target ON tr.t_seconds <= target.t_target
        )
        SELECT window_id, t_target, pm_up_price
        FROM cand
        WHERE rn = 1 AND (t_target - t_seconds) <= {max_staleness}
    """).df()


def scan_pm_trajectory(split: SplitData) -> pd.DataFrame:
    entry_times = [60, 120, 180, 300, 450, 600]
    horizons = [30, 60, 120, 180, 300]
    thresholds = [0.02, 0.05, 0.10, 0.15]
    targets = sorted(set(entry_times + [t + h for t in entry_times for h in horizons if t + h < 900]))
    px = prices_at_targets(split.train_ids, targets)
    wide = px.pivot(index="window_id", columns="t_target", values="pm_up_price")
    wide.columns = [f"p{int(c)}" for c in wide.columns]
    wide = wide.reset_index()
    wide = wide.merge(split.train[["window_id", "pm_up_price_open"]], on="window_id", how="left")

    rows = []
    for t in entry_times:
        for h in horizons:
            exit_t = t + h
            if exit_t >= 900:
                continue
            needed = ["pm_up_price_open", f"p{t}", f"p{exit_t}"]
            if any(c not in wide.columns for c in needed):
                continue
            sub0 = wide[["window_id", *needed]].dropna().copy()
            sub0["prior_delta"] = sub0[f"p{t}"] - sub0["pm_up_price_open"]
            sub0["future_delta"] = sub0[f"p{exit_t}"] - sub0[f"p{t}"]
            sub0 = sub0[sub0["future_delta"] != 0].copy()
            for thr in thresholds:
                base = sub0[sub0["prior_delta"].abs() >= thr].copy()
                if len(base) < 200:
                    continue
                for mode, mult in [("momentum", 1.0), ("reversion", -1.0)]:
                    pred = mult * np.sign(base["prior_delta"].to_numpy())
                    fut = base["future_delta"].to_numpy()
                    hits = (pred * np.sign(fut) > 0).astype(int)
                    pnl = pred * fut
                    successes = int(hits.sum())
                    n = int(len(hits))
                    b = binomtest(successes, n, 0.5, alternative="greater")
                    tt = ttest_1samp(pnl, 0.0, alternative="greater")
                    rows.append({
                        "angle": "B_pm_trajectory",
                        "mode": mode,
                        "entry_t": t,
                        "horizon": h,
                        "threshold": thr,
                        "n": n,
                        "hit_rate": successes / n,
                        "binom_p_greater": float(b.pvalue),
                        "mean_gross_move": float(np.mean(pnl)),
                        "median_gross_move": float(np.median(pnl)),
                        "ttest_p_greater": float(tt.pvalue) if not math.isnan(tt.pvalue) else float("nan"),
                    })
    out = pd.DataFrame(rows)
    if len(out) == 0:
        return out
    out["score"] = out["mean_gross_move"] * np.sqrt(out["n"])
    return out.sort_values(["ttest_p_greater", "binom_p_greater", "score"], ascending=[True, True, False])


def scan_entry_to_resolution(split: SplitData) -> pd.DataFrame:
    """Trade at t based on pm move from open, then hold to outcome."""
    entry_times = [60, 120, 180, 300, 450, 600]
    thresholds = [0.02, 0.05, 0.10, 0.15, 0.20]
    fee = 0.07
    spread = 0.01
    targets = entry_times
    px = prices_at_targets(split.train_ids, targets)
    wide = px.pivot(index="window_id", columns="t_target", values="pm_up_price")
    wide.columns = [f"p{int(c)}" for c in wide.columns]
    wide = wide.reset_index()
    wide = wide.merge(
        split.train[["window_id", "pm_up_price_open", "outcome"]],
        on="window_id",
        how="left",
    )

    rows = []
    for t in entry_times:
        pcol = f"p{t}"
        if pcol not in wide.columns:
            continue
        sub0 = wide[["window_id", "pm_up_price_open", "outcome", pcol]].dropna().copy()
        sub0["prior_delta"] = sub0[pcol] - sub0["pm_up_price_open"]
        for thr in thresholds:
            base = sub0[sub0["prior_delta"].abs() >= thr].copy()
            if len(base) < 200:
                continue
            for mode, mult in [("momentum", 1.0), ("reversion", -1.0)]:
                pred_dir = mult * np.sign(base["prior_delta"].to_numpy())
                side_up = pred_dir > 0
                entry = np.where(side_up, base[pcol].to_numpy(), 1.0 - base[pcol].to_numpy())
                win = np.where(side_up, base["outcome"].to_numpy() == "Up", base["outcome"].to_numpy() == "Down").astype(float)
                gross = win - entry
                entry_with_costs = entry + spread
                net = win - entry_with_costs - fee * entry_with_costs
                tt_gross = ttest_1samp(gross, 0.0, alternative="greater")
                tt_net = ttest_1samp(net, 0.0, alternative="greater")
                rows.append({
                    "angle": "B_entry_to_resolution",
                    "mode": mode,
                    "entry_t": t,
                    "threshold": thr,
                    "n": int(len(base)),
                    "win_rate": float(win.mean()),
                    "avg_entry_price": float(entry.mean()),
                    "mean_gross_pnl": float(gross.mean()),
                    "mean_net_pnl": float(net.mean()),
                    "median_net_pnl": float(np.median(net)),
                    "ttest_gross_p_greater": float(tt_gross.pvalue) if not math.isnan(tt_gross.pvalue) else float("nan"),
                    "ttest_net_p_greater": float(tt_net.pvalue) if not math.isnan(tt_net.pvalue) else float("nan"),
                })
    out = pd.DataFrame(rows)
    if len(out) == 0:
        return out
    return out.sort_values(["ttest_net_p_greater", "mean_net_pnl"], ascending=[True, False])


def volatility_diagnostics(split: SplitData) -> pd.DataFrame:
    df = split.train.copy()
    df["realized_abs_ret"] = (df["chainlink_close"] - df["price_to_beat"]).abs() / df["price_to_beat"]
    df["pm_open_uncertainty"] = 1.0 - (df["pm_up_price_open"] - 0.5).abs() * 2.0
    features = [
        "D_5m_otm_dotm", "D_10m_otm_dotm", "D_15m_otm_dotm",
        "V_5m_otm_dotm", "V_10m_otm_dotm", "V_15m_otm_dotm",
        "n_trades_5m", "n_trades_10m", "n_trades_15m",
    ]
    rows = []
    for f in features:
        x = df[f].abs() if f.startswith("D_") else df[f]
        ok = x.notna() & df["realized_abs_ret"].notna()
        if ok.sum() < 100:
            continue
        rho, p = spearmanr(x[ok], df.loc[ok, "realized_abs_ret"])
        rows.append({
            "angle": "V_volatility_diagnostic",
            "feature": f,
            "n": int(ok.sum()),
            "spearman_rho_abs_move": float(rho),
            "p_value": float(p),
        })
    return pd.DataFrame(rows).sort_values("p_value")


def main() -> int:
    split = load_train()
    print(f"TRAIN windows: {len(split.train_ids):,} | HOLDOUT sealed: {len(split.holdout_ids):,}")
    print(f"TRAIN range: {split.train['ts_open'].min()} .. {split.train['ts_open'].max()}")
    print()

    b = scan_pm_trajectory(split)
    print("=== B: pm_up_price trajectory candidates (TRAIN ONLY) ===")
    if len(b) == 0:
        print("No candidates with enough n.")
    else:
        cols = ["mode", "entry_t", "horizon", "threshold", "n", "hit_rate",
                "binom_p_greater", "mean_gross_move", "median_gross_move", "ttest_p_greater"]
        print(b[cols].head(25).to_string(index=False))
        b.to_csv(ROOT / "reports" / "phases" / "train_edge_scan_B_pm_trajectory.csv", index=False)
        print("\nSaved: reports/phases/train_edge_scan_B_pm_trajectory.csv")
    print()

    br = scan_entry_to_resolution(split)
    print("=== B2: enter at t, hold to resolution (TRAIN ONLY, fee+spread model) ===")
    if len(br) == 0:
        print("No candidates with enough n.")
    else:
        cols = ["mode", "entry_t", "threshold", "n", "win_rate", "avg_entry_price",
                "mean_gross_pnl", "mean_net_pnl", "median_net_pnl", "ttest_net_p_greater"]
        print(br[cols].head(25).to_string(index=False))
        br.to_csv(ROOT / "reports" / "phases" / "train_edge_scan_B_entry_to_resolution.csv", index=False)
        print("\nSaved: reports/phases/train_edge_scan_B_entry_to_resolution.csv")
    print()

    v = volatility_diagnostics(split)
    print("=== V: D/V -> realized volatility diagnostics (TRAIN ONLY) ===")
    print(v.to_string(index=False))
    v.to_csv(ROOT / "reports" / "phases" / "train_edge_scan_V_volatility.csv", index=False)
    print("\nSaved: reports/phases/train_edge_scan_V_volatility.csv")
    print()

    print("NOTE: These are exploratory scans. Do not claim edge from this output.")
    print("Next: choose exactly ONE candidate, write it down, then run a holdout test once.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
