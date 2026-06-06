"""Fase E — M1 market-making proxy scan.

Question:
  Is displayed spread large enough to compensate future mid-price movement?

Proxy:
  EV_proxy = spread / 2 - abs(mid_future - mid_now)

Interpretation:
  If EV_proxy > 0, a symmetric maker quote around mid could be profitable before
  fill mechanics. This is NOT yet a fill-realistic backtest. If it passes train,
  the next phase uses ticks to estimate fills/adverse selection.

Statistical unit:
  Market-level means. We do not treat millions of snapshots as independent.

Default:
  TRAIN only. Do not use holdout until one rule is frozen.

Usage:
  py scripts/scan_market_making_m1.py --on train
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

SNAPSHOTS = ROOT / "data" / "interim" / "orderbook_btc15m_snapshots.parquet"
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


def selected_condition(on: str) -> str:
    if on == "train":
        return "market_rn <= floor(market_n * 0.7)"
    if on == "holdout":
        return "market_rn > floor(market_n * 0.7)"
    if on == "all":
        return "TRUE"
    raise ValueError(on)


def load_eval_rows(
    on: str,
    horizon_s: int,
    sample_step_s: int,
    future_staleness_s: int,
    limit_markets: int | None,
) -> pd.DataFrame:
    """Return sampled decision rows with nearest future mid for one horizon."""
    con = duckdb.connect()
    con.execute("SET threads TO 4")

    limit_clause = f"LIMIT {limit_markets}" if limit_markets else ""
    cond = selected_condition(on)
    p = SNAPSHOTS.as_posix()
    query = f"""
        WITH markets AS (
          SELECT market_id, min(ts_open) AS ts_open
          FROM '{p}'
          GROUP BY market_id
        ),
        ranked AS (
          SELECT market_id, ts_open,
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
        token_rows AS (
          SELECT
            s.market_id,
            s.window_id,
            s.ts_ms,
            s.time_to_close_s,
            'Up' AS side,
            s.mid_up AS mid,
            s.spread_up AS spread,
            least(s.bid_size_up, s.ask_size_up) AS book_size
          FROM '{p}' s
          JOIN selected_markets m ON s.market_id = m.market_id
          WHERE s.spread_up >= 0
            AND s.mid_up BETWEEN 0 AND 1
          UNION ALL
          SELECT
            s.market_id,
            s.window_id,
            s.ts_ms,
            s.time_to_close_s,
            'Down' AS side,
            s.mid_down AS mid,
            s.spread_down AS spread,
            least(s.bid_size_down, s.ask_size_down) AS book_size
          FROM '{p}' s
          JOIN selected_markets m ON s.market_id = m.market_id
          WHERE s.spread_down >= 0
            AND s.mid_down BETWEEN 0 AND 1
        ),
        sampled AS (
          SELECT * EXCLUDE(rn)
          FROM (
            SELECT *,
                   floor((900.0 - time_to_close_s) / {sample_step_s}) AS bucket_s,
                   row_number() OVER (
                     PARTITION BY market_id, side, floor((900.0 - time_to_close_s) / {sample_step_s})
                     ORDER BY ts_ms
                   ) AS rn
            FROM token_rows
            WHERE time_to_close_s >= {horizon_s + future_staleness_s}
          )
          WHERE rn = 1
        ),
        eval AS (
          SELECT
            d.market_id,
            d.window_id,
            d.side,
            d.ts_ms,
            d.time_to_close_s,
            d.mid,
            d.spread,
            d.book_size,
            first(f.mid ORDER BY f.ts_ms) AS future_mid,
            min(f.ts_ms) AS future_ts_ms
          FROM sampled d
          LEFT JOIN token_rows f
            ON f.market_id = d.market_id
           AND f.side = d.side
           AND f.ts_ms >= d.ts_ms + {horizon_s * 1000}
           AND f.ts_ms <= d.ts_ms + {(horizon_s + future_staleness_s) * 1000}
          GROUP BY
            d.market_id, d.window_id, d.side, d.ts_ms, d.time_to_close_s,
            d.mid, d.spread, d.book_size
        )
        SELECT *
        FROM eval
        WHERE future_mid IS NOT NULL
        ORDER BY market_id, side, ts_ms
    """
    return con.execute(query).df()


def bootstrap_p_greater_zero(values: np.ndarray, seed: int = 42, n_resamples: int = 5000) -> float:
    if len(values) == 0:
        return float("nan")
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(values), size=(n_resamples, len(values)))
    means = values[idx].mean(axis=1)
    return float((means <= 0).mean())


def scan_rules(
    eval_df: pd.DataFrame,
    horizon_s: int,
    spread_thresholds: list[float],
    size_thresholds: list[float],
    time_to_close_thresholds: list[int],
    min_markets: int,
) -> pd.DataFrame:
    df = eval_df.copy()
    df["ev_proxy"] = df["spread"] / 2.0 - (df["future_mid"] - df["mid"]).abs()
    rows = []

    for spread_thr in spread_thresholds:
        for size_thr in size_thresholds:
            for ttc_thr in time_to_close_thresholds:
                sub = df[
                    (df["spread"] >= spread_thr)
                    & (df["book_size"] >= size_thr)
                    & (df["time_to_close_s"] >= ttc_thr)
                ].copy()
                if sub.empty:
                    continue
                market_ev = sub.groupby("market_id", as_index=False).agg(
                    mean_ev=("ev_proxy", "mean"),
                    n_decisions=("ev_proxy", "count"),
                    positive_rate=("ev_proxy", lambda x: float((x > 0).mean())),
                    mean_spread=("spread", "mean"),
                    mean_book_size=("book_size", "mean"),
                )
                n_markets = len(market_ev)
                if n_markets < min_markets:
                    continue
                vals = market_ev["mean_ev"].to_numpy(dtype=float)
                tt = ttest_1samp(vals, 0.0, alternative="greater")
                boot_p = bootstrap_p_greater_zero(vals)
                rows.append({
                    "horizon_s": horizon_s,
                    "spread_threshold": spread_thr,
                    "book_size_threshold": size_thr,
                    "time_to_close_threshold": ttc_thr,
                    "n_markets": int(n_markets),
                    "n_decisions": int(sub.shape[0]),
                    "mean_market_ev_proxy": float(vals.mean()),
                    "median_market_ev_proxy": float(np.median(vals)),
                    "market_positive_rate": float((vals > 0).mean()),
                    "mean_decision_ev_proxy": float(sub["ev_proxy"].mean()),
                    "mean_spread": float(sub["spread"].mean()),
                    "mean_book_size": float(sub["book_size"].mean()),
                    "ttest_p_greater": float(tt.pvalue),
                    "bootstrap_p_greater": boot_p,
                })

    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values(
        ["bootstrap_p_greater", "ttest_p_greater", "mean_market_ev_proxy"],
        ascending=[True, True, False],
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--on", choices=["train", "holdout", "all"], default="train")
    ap.add_argument("--horizons", default="30,60,120")
    ap.add_argument("--sample-step-s", type=int, default=10)
    ap.add_argument("--future-staleness-s", type=int, default=15)
    ap.add_argument("--spread-thresholds", default="0.01,0.02,0.03,0.05,0.10")
    ap.add_argument("--size-thresholds", default="0,1,100,1000")
    ap.add_argument("--time-to-close-thresholds", default="120,300")
    ap.add_argument("--min-markets", type=int, default=50)
    ap.add_argument("--limit-markets", type=int, default=None)
    args = ap.parse_args()

    if not SNAPSHOTS.exists():
        raise FileNotFoundError(f"Missing snapshots: {SNAPSHOTS}. Run build_orderbook_snapshots.py first.")

    horizons = parse_csv_ints(args.horizons)
    spread_thresholds = parse_csv_floats(args.spread_thresholds)
    size_thresholds = parse_csv_floats(args.size_thresholds)
    ttc_thresholds = parse_csv_ints(args.time_to_close_thresholds)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    all_results = []
    eval_stats = []

    for horizon in horizons:
        print(f"Loading eval rows for horizon={horizon}s on={args.on}...")
        eval_df = load_eval_rows(
            on=args.on,
            horizon_s=horizon,
            sample_step_s=args.sample_step_s,
            future_staleness_s=args.future_staleness_s,
            limit_markets=args.limit_markets,
        )
        eval_df["ev_proxy"] = eval_df["spread"] / 2.0 - (eval_df["future_mid"] - eval_df["mid"]).abs()
        eval_stats.append({
            "horizon_s": horizon,
            "rows": int(len(eval_df)),
            "markets": int(eval_df["market_id"].nunique()) if len(eval_df) else 0,
            "mean_ev_proxy_all_rows": float(eval_df["ev_proxy"].mean()) if len(eval_df) else None,
        })
        print(f"  rows={len(eval_df):,} markets={eval_df['market_id'].nunique() if len(eval_df) else 0:,}")
        res = scan_rules(
            eval_df=eval_df,
            horizon_s=horizon,
            spread_thresholds=spread_thresholds,
            size_thresholds=size_thresholds,
            time_to_close_thresholds=ttc_thresholds,
            min_markets=args.min_markets,
        )
        if not res.empty:
            all_results.append(res)

    results = pd.concat(all_results, ignore_index=True) if all_results else pd.DataFrame()
    tag = f"{args.on}"
    if args.limit_markets:
        tag += f"_limit{args.limit_markets}"
    csv_out = REPORT_DIR / f"m1_market_making_scan_{tag}.csv"
    json_out = REPORT_DIR / f"m1_market_making_scan_{tag}.json"
    if not results.empty:
        results.to_csv(csv_out, index=False)

    report = {
        "scan": "M1_market_making_proxy",
        "on": args.on,
        "run_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "snapshots_path": SNAPSHOTS.as_posix(),
        "snapshots_sha256": file_sha256(SNAPSHOTS),
        "sample_step_s": args.sample_step_s,
        "future_staleness_s": args.future_staleness_s,
        "horizons": horizons,
        "spread_thresholds": spread_thresholds,
        "size_thresholds": size_thresholds,
        "time_to_close_thresholds": ttc_thresholds,
        "min_markets": args.min_markets,
        "limit_markets": args.limit_markets,
        "eval_stats": eval_stats,
        "top_rules": results.head(25).to_dict(orient="records") if not results.empty else [],
        "csv": csv_out.as_posix() if not results.empty else None,
        "interpretation": (
            "TRAIN scan only unless --on holdout is explicitly used after pre-registration. "
            "EV_proxy is not fill-realistic; positive results require tick/fill validation."
        ),
    }
    json_out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    if results.empty:
        print("No rules met min_markets.")
    else:
        print("\nTop M1 rules:")
        cols = [
            "horizon_s", "spread_threshold", "book_size_threshold", "time_to_close_threshold",
            "n_markets", "n_decisions", "mean_market_ev_proxy", "market_positive_rate",
            "ttest_p_greater", "bootstrap_p_greater",
        ]
        print(results[cols].head(25).to_string(index=False))
        print(f"\nSaved CSV: {csv_out}")
    print(f"Saved JSON: {json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
