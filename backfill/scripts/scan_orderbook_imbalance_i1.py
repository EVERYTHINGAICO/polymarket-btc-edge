"""I1 orderbook imbalance TRAIN scan.

Question:
  Does visible bid/ask size imbalance predict enough future mid movement to buy
  a token at the current best ask?

Executable proxy:
  EV_taker_proxy = future_mid - best_ask

This is stricter than a mid-move target because it pays the current half-spread.
It still excludes fees, latency, and fill failure.

Default:
  TRAIN only. Do not run holdout until one rule is frozen.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import duckdb
import numpy as np
import pandas as pd
from scipy.stats import ttest_1samp

SAMPLES = ROOT / "data" / "interim" / "orderbook_i1_samples_10s.parquet"
REPORT_DIR = ROOT / "reports" / "phases"


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 24), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_csv_floats(s: str) -> list[float]:
    return [float(x.strip()) for x in s.split(",") if x.strip()]


def parse_csv_ints(s: str) -> list[int]:
    return [int(x.strip()) for x in s.split(",") if x.strip()]


def parse_csv_strings(s: str) -> list[str]:
    return [x.strip() for x in s.split(",") if x.strip()]


def selected_condition(on: str) -> str:
    if on == "train":
        return "market_rn <= floor(market_n * 0.7)"
    if on == "holdout":
        return "market_rn > floor(market_n * 0.7)"
    if on == "all":
        return "TRUE"
    raise ValueError(on)


def bootstrap_p_greater_zero(values: np.ndarray, seed: int = 42, n_resamples: int = 5000) -> float:
    if len(values) == 0:
        return float("nan")
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(values), size=(n_resamples, len(values)))
    means = values[idx].mean(axis=1)
    return float((means <= 0).mean())


def bootstrap_ci(values: np.ndarray, seed: int = 123, n_resamples: int = 5000) -> tuple[float, float]:
    if len(values) == 0:
        return float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(values), size=(n_resamples, len(values)))
    means = values[idx].mean(axis=1)
    lo, hi = np.quantile(means, [0.025, 0.975])
    return float(lo), float(hi)


def load_eval_rows(
    on: str,
    horizon_s: int,
    future_staleness_s: int,
    limit_markets: int | None,
) -> pd.DataFrame:
    con = duckdb.connect()
    con.execute("SET threads TO 4")
    p = SAMPLES.as_posix()
    cond = selected_condition(on)
    limit_clause = f"LIMIT {limit_markets}" if limit_markets else ""
    query = f"""
        WITH markets AS (
          SELECT market_id, min(ts_open) AS ts_open
          FROM '{p}'
          GROUP BY market_id
        ),
        ranked AS (
          SELECT
            market_id,
            ts_open,
            row_number() OVER (ORDER BY ts_open, market_id) AS market_rn,
            count(*) OVER () AS market_n
          FROM markets
        ),
        selected_markets AS (
          SELECT market_id
          FROM ranked
          WHERE {cond}
          ORDER BY ts_open, market_id
          {limit_clause}
        ),
        decisions AS (
          SELECT s.*
          FROM '{p}' s
          JOIN selected_markets m USING (market_id)
          WHERE s.time_to_close_s >= {horizon_s + future_staleness_s}
            AND s.size_imbalance IS NOT NULL
            AND s.best_ask BETWEEN 0 AND 1
        ),
        candidates AS (
          SELECT
            d.market_id,
            d.window_id,
            d.ts_open,
            d.ts_close,
            d.side,
            d.ts_ms,
            d.bucket_s,
            d.time_to_close_s,
            d.best_bid,
            d.best_ask,
            d.bid_size,
            d.ask_size,
            d.mid,
            d.spread,
            d.book_size,
            d.size_imbalance,
            f.ts_ms AS future_ts_ms,
            f.mid AS future_mid,
            row_number() OVER (
              PARTITION BY d.market_id, d.side, d.bucket_s
              ORDER BY f.ts_ms
            ) AS rn
          FROM decisions d
          JOIN '{p}' f
            ON f.market_id = d.market_id
           AND f.side = d.side
           AND f.ts_ms >= d.ts_ms + {horizon_s * 1000}
           AND f.ts_ms <= d.ts_ms + {(horizon_s + future_staleness_s) * 1000}
        )
        SELECT
          market_id,
          window_id,
          ts_open,
          ts_close,
          side,
          ts_ms,
          bucket_s,
          time_to_close_s,
          best_bid,
          best_ask,
          bid_size,
          ask_size,
          mid,
          spread,
          book_size,
          size_imbalance,
          future_ts_ms,
          future_mid,
          (future_ts_ms - ts_ms) / 1000.0 AS future_delta_s,
          future_mid - best_ask AS ev_taker_proxy,
          future_mid - mid AS mid_move
        FROM candidates
        WHERE rn = 1
        ORDER BY market_id, side, ts_ms
    """
    return con.execute(query).df()


def scan_rules(
    eval_df: pd.DataFrame,
    horizon_s: int,
    modes: list[str],
    imbalance_thresholds: list[float],
    max_spreads: list[float],
    ask_size_thresholds: list[float],
    time_to_close_thresholds: list[int],
    min_markets: int,
) -> pd.DataFrame:
    rows = []
    for mode in modes:
        if mode not in {"momentum", "contrarian"}:
            raise ValueError(f"Unknown mode: {mode}")
        for imb_thr in imbalance_thresholds:
            for max_spread in max_spreads:
                for ask_thr in ask_size_thresholds:
                    for ttc_thr in time_to_close_thresholds:
                        if mode == "momentum":
                            imb_mask = eval_df["size_imbalance"] >= imb_thr
                        else:
                            imb_mask = eval_df["size_imbalance"] <= -imb_thr
                        sub = eval_df[
                            imb_mask
                            & (eval_df["spread"] <= max_spread)
                            & (eval_df["ask_size"] >= ask_thr)
                            & (eval_df["time_to_close_s"] >= ttc_thr)
                        ]
                        if sub.empty:
                            continue

                        market_ev = sub.groupby("market_id", as_index=False).agg(
                            mean_ev=("ev_taker_proxy", "mean"),
                            n_decisions=("ev_taker_proxy", "count"),
                            positive_decision_rate=("ev_taker_proxy", lambda x: float((x > 0).mean())),
                            mean_mid_move=("mid_move", "mean"),
                            mean_spread=("spread", "mean"),
                            median_spread=("spread", "median"),
                            mean_imbalance=("size_imbalance", "mean"),
                            mean_ask_size=("ask_size", "mean"),
                            median_ask_size=("ask_size", "median"),
                        )
                        n_markets = len(market_ev)
                        if n_markets < min_markets:
                            continue

                        vals = market_ev["mean_ev"].to_numpy(dtype=float)
                        tt = ttest_1samp(vals, 0.0, alternative="greater")
                        boot_p = bootstrap_p_greater_zero(vals)
                        ci_low, ci_high = bootstrap_ci(vals)
                        rows.append({
                            "horizon_s": horizon_s,
                            "mode": mode,
                            "imbalance_threshold": imb_thr,
                            "max_spread": max_spread,
                            "ask_size_threshold": ask_thr,
                            "time_to_close_threshold": ttc_thr,
                            "n_markets": int(n_markets),
                            "n_decisions": int(len(sub)),
                            "mean_market_ev_taker_proxy": float(vals.mean()),
                            "median_market_ev_taker_proxy": float(np.median(vals)),
                            "market_positive_rate": float((vals > 0).mean()),
                            "mean_decision_ev_taker_proxy": float(sub["ev_taker_proxy"].mean()),
                            "decision_positive_rate": float((sub["ev_taker_proxy"] > 0).mean()),
                            "ci95_market_ev_low": ci_low,
                            "ci95_market_ev_high": ci_high,
                            "mean_mid_move": float(sub["mid_move"].mean()),
                            "mean_spread": float(sub["spread"].mean()),
                            "median_spread": float(sub["spread"].median()),
                            "mean_imbalance": float(sub["size_imbalance"].mean()),
                            "mean_ask_size": float(sub["ask_size"].mean()),
                            "median_ask_size": float(sub["ask_size"].median()),
                            "mean_future_delta_s": float(sub["future_delta_s"].mean()),
                            "ttest_p_greater": float(tt.pvalue),
                            "bootstrap_p_greater": boot_p,
                        })

    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values(
        ["bootstrap_p_greater", "ttest_p_greater", "mean_market_ev_taker_proxy"],
        ascending=[True, True, False],
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--on", choices=["train", "holdout", "all"], default="train")
    ap.add_argument("--horizons", default="30,60,120")
    ap.add_argument("--future-staleness-s", type=int, default=20)
    ap.add_argument("--modes", default="momentum,contrarian")
    ap.add_argument("--imbalance-thresholds", default="0.2,0.4,0.6,0.8")
    ap.add_argument("--max-spreads", default="0.01,0.02,0.05,0.10,0.20")
    ap.add_argument("--ask-size-thresholds", default="1,100,1000")
    ap.add_argument("--time-to-close-thresholds", default="120,300")
    ap.add_argument("--min-markets", type=int, default=50)
    ap.add_argument("--limit-markets", type=int, default=None)
    args = ap.parse_args()

    if not SAMPLES.exists():
        raise FileNotFoundError(f"Missing samples: {SAMPLES}. Run build_orderbook_i1_samples.py first.")

    horizons = parse_csv_ints(args.horizons)
    modes = parse_csv_strings(args.modes)
    imbalance_thresholds = parse_csv_floats(args.imbalance_thresholds)
    max_spreads = parse_csv_floats(args.max_spreads)
    ask_size_thresholds = parse_csv_floats(args.ask_size_thresholds)
    ttc_thresholds = parse_csv_ints(args.time_to_close_thresholds)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    all_results = []
    eval_stats = []

    for horizon in horizons:
        print(f"Loading I1 eval rows horizon={horizon}s on={args.on}...")
        eval_df = load_eval_rows(
            on=args.on,
            horizon_s=horizon,
            future_staleness_s=args.future_staleness_s,
            limit_markets=args.limit_markets,
        )
        eval_stats.append({
            "horizon_s": horizon,
            "rows": int(len(eval_df)),
            "markets": int(eval_df["market_id"].nunique()) if len(eval_df) else 0,
            "mean_ev_taker_proxy_all_rows": float(eval_df["ev_taker_proxy"].mean()) if len(eval_df) else None,
            "mean_mid_move_all_rows": float(eval_df["mid_move"].mean()) if len(eval_df) else None,
        })
        print(f"  rows={len(eval_df):,} markets={eval_df['market_id'].nunique() if len(eval_df) else 0:,}")

        res = scan_rules(
            eval_df=eval_df,
            horizon_s=horizon,
            modes=modes,
            imbalance_thresholds=imbalance_thresholds,
            max_spreads=max_spreads,
            ask_size_thresholds=ask_size_thresholds,
            time_to_close_thresholds=ttc_thresholds,
            min_markets=args.min_markets,
        )
        if not res.empty:
            all_results.append(res)

    results = pd.concat(all_results, ignore_index=True) if all_results else pd.DataFrame()
    if not results.empty:
        n_rules = len(results)
        results["n_rules_tested"] = n_rules
        results["bootstrap_p_bonferroni"] = np.minimum(1.0, results["bootstrap_p_greater"] * n_rules)
        results["ttest_p_bonferroni"] = np.minimum(1.0, results["ttest_p_greater"] * n_rules)
        results = results.sort_values(
            ["bootstrap_p_bonferroni", "bootstrap_p_greater", "mean_market_ev_taker_proxy"],
            ascending=[True, True, False],
        )

    tag = f"{args.on}_i1_samples10s"
    if args.limit_markets:
        tag += f"_limit{args.limit_markets}"
    csv_out = REPORT_DIR / f"i1_orderbook_imbalance_scan_{tag}.csv"
    json_out = REPORT_DIR / f"i1_orderbook_imbalance_scan_{tag}.json"
    if not results.empty:
        results.to_csv(csv_out, index=False)

    report = {
        "scan": "I1_orderbook_imbalance_taker_proxy",
        "on": args.on,
        "run_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "samples_path": SAMPLES.as_posix(),
        "samples_sha256": file_sha256(SAMPLES),
        "future_staleness_s": args.future_staleness_s,
        "horizons": horizons,
        "modes": modes,
        "imbalance_thresholds": imbalance_thresholds,
        "max_spreads": max_spreads,
        "ask_size_thresholds": ask_size_thresholds,
        "time_to_close_thresholds": ttc_thresholds,
        "min_markets": args.min_markets,
        "limit_markets": args.limit_markets,
        "eval_stats": eval_stats,
        "n_rules_tested": int(len(results)) if not results.empty else 0,
        "top_rules": results.head(25).to_dict(orient="records") if not results.empty else [],
        "csv": csv_out.as_posix() if not results.empty else None,
        "interpretation": (
            "TRAIN exploratory scan. EV_taker_proxy buys at best_ask and exits at future_mid. "
            "It excludes fees and latency; holdout requires one frozen rule."
        ),
    }
    json_out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    if results.empty:
        print("No rules met min_markets.")
    else:
        cols = [
            "horizon_s",
            "mode",
            "imbalance_threshold",
            "max_spread",
            "ask_size_threshold",
            "time_to_close_threshold",
            "n_markets",
            "n_decisions",
            "mean_market_ev_taker_proxy",
            "ci95_market_ev_low",
            "market_positive_rate",
            "bootstrap_p_greater",
            "bootstrap_p_bonferroni",
        ]
        print("\nTop I1 rules:")
        print(results[cols].head(25).to_string(index=False))
        print(f"\nSaved CSV: {csv_out}")
    print(f"Saved JSON: {json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
