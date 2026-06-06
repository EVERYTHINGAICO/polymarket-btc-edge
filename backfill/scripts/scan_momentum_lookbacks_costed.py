"""Costed momentum lookback scan.

This is a BTC lab scan, not final evidence. The BTC holdout has already been
looked at, so outputs here are for designing one future rule to validate on
independent ETH/SOL/live data.

Fixed rule family:
  t_signal = ts_open - gap
  momentum = spot[t_signal] / spot[t_signal - lookback] - 1
  if abs(momentum) >= threshold:
      buy Up when momentum > 0, buy Down when momentum < 0

Cost models:
  proxy:
    entry Up = first Polymarket up_price at/after entry_t
    entry Down = 1 - that up_price

  orderbook:
    entry Up = first best_ask_up at/after entry_t
    entry Down = first best_ask_down at/after entry_t

Fees:
  crypto taker fee per share = fee_rate * p * (1 - p)
  default fee_rate = 0.07

Outputs:
  reports/phases/momentum_lookback_scan_proxy_prices.csv/json
  reports/phases/momentum_lookback_scan_orderbook_costed.csv/json
  reports/phases/momentum_lookback_costed_summary.md
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import duckdb
import numpy as np
import pandas as pd
from scipy.stats import ttest_1samp

WINDOWS = ROOT / "data" / "raw" / "polymarket_markets_btc15m.parquet"
OUTCOMES = ROOT / "data" / "interim" / "outcomes.parquet"
TRAJ = ROOT / "data" / "interim" / "pm_trajectory.parquet"
BINANCE = ROOT / "data" / "raw" / "binance_btc_1m.jsonl"
ORDERBOOK = ROOT / "data" / "interim" / "orderbook_btc15m_snapshots.parquet"
REPORT_DIR = ROOT / "reports" / "phases"


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 24), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_csv_ints(s: str) -> list[int]:
    return [int(x.strip()) for x in s.split(",") if x.strip()]


def parse_csv_floats(s: str) -> list[float]:
    return [float(x.strip()) for x in s.split(",") if x.strip()]


def bootstrap_p_greater_zero(values: np.ndarray, seed: int = 42, n_resamples: int = 4000) -> float | None:
    if len(values) == 0:
        return None
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(values), size=(n_resamples, len(values)))
    means = values[idx].mean(axis=1)
    return float((means <= 0).mean())


def bootstrap_ci(values: np.ndarray, seed: int = 123, n_resamples: int = 4000) -> tuple[float | None, float | None]:
    if len(values) == 0:
        return None, None
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(values), size=(n_resamples, len(values)))
    means = values[idx].mean(axis=1)
    lo, hi = np.quantile(means, [0.025, 0.975])
    return float(lo), float(hi)


def finite_float(x: Any) -> float | None:
    try:
        v = float(x)
    except Exception:
        return None
    if math.isnan(v) or math.isinf(v):
        return None
    return v


def finite_mean(values: pd.Series | np.ndarray) -> float | None:
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    if len(arr) == 0:
        return None
    return float(arr.mean())


def finite_median(values: pd.Series | np.ndarray) -> float | None:
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    if len(arr) == 0:
        return None
    return float(np.median(arr))


def add_splits(df: pd.DataFrame) -> pd.DataFrame:
    out = df.sort_values(["ts_open_s", "window_id"]).reset_index(drop=True).copy()
    n = len(out)
    train_cut = int(n * 0.50)
    validation_cut = int(n * 0.70)
    idx = np.arange(n)
    out["split"] = np.where(
        idx < train_cut,
        "train",
        np.where(idx < validation_cut, "validation", "holdout_lab"),
    )
    return out


def load_binance(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return con.execute(f"""
        SELECT CAST(ts / 1000 AS BIGINT) AS ts_s, CAST(close AS DOUBLE) AS close
        FROM read_json_auto(
          '{BINANCE.as_posix()}',
          format='newline_delimited',
          columns={{'ts':'BIGINT','close':'DOUBLE'}}
        )
        ORDER BY ts_s
    """).df()


def load_base_windows(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return con.execute(f"""
        SELECT
          w.condition_id AS window_id,
          w.market_id,
          CAST(w.end_ts - 900 AS BIGINT) AS ts_open_s,
          CAST(w.end_ts AS BIGINT) AS ts_close_s,
          o.outcome
        FROM '{WINDOWS.as_posix()}' w
        JOIN '{OUTCOMES.as_posix()}' o ON w.condition_id = o.condition_id
        WHERE w.crypto = 'BTC'
          AND w.timeframe = '15-minute'
          AND o.outcome IN ('Up','Down')
        ORDER BY ts_open_s, window_id
    """).df()


def add_spot_features(df: pd.DataFrame, binance: pd.DataFrame, lookbacks: list[int], gaps: list[int]) -> pd.DataFrame:
    out = df.copy()
    spot = binance.set_index("ts_s")["close"]
    for gap in gaps:
        signal_ts = out["ts_open_s"] - gap * 60
        out[f"spot_signal_g{gap}"] = signal_ts.map(spot)
        for lb in lookbacks:
            start_ts = signal_ts - lb * 60
            out[f"mom_l{lb}_g{gap}"] = out[f"spot_signal_g{gap}"] / start_ts.map(spot) - 1.0
    return out


def load_proxy_entries(con: duckdb.DuckDBPyConnection, entry_seconds: list[int], staleness_s: int) -> pd.DataFrame:
    values = ",".join(f"({int(t)})" for t in entry_seconds)
    rows = con.execute(f"""
        WITH target(entry_t) AS (VALUES {values}),
        cand AS (
          SELECT
            tr.window_id,
            target.entry_t,
            tr.t_seconds,
            tr.pm_up_price,
            row_number() OVER (
              PARTITION BY tr.window_id, target.entry_t
              ORDER BY tr.t_seconds ASC
            ) AS rn
          FROM '{TRAJ.as_posix()}' tr
          JOIN target
            ON tr.t_seconds >= target.entry_t
           AND tr.t_seconds <= target.entry_t + {int(staleness_s)}
        )
        SELECT window_id, entry_t, t_seconds AS actual_entry_t, CAST(pm_up_price AS DOUBLE) AS pm_up_price
        FROM cand
        WHERE rn = 1
        ORDER BY window_id, entry_t
    """).df()
    if rows.empty:
        return pd.DataFrame({"window_id": []})
    price_wide = rows.pivot(index="window_id", columns="entry_t", values="pm_up_price")
    price_wide.columns = [f"proxy_up_price_e{int(c)}" for c in price_wide.columns]
    delay = rows.assign(delay_s=rows["actual_entry_t"] - rows["entry_t"]).pivot(
        index="window_id", columns="entry_t", values="delay_s"
    )
    delay.columns = [f"proxy_delay_s_e{int(c)}" for c in delay.columns]
    return price_wide.join(delay).reset_index()


def load_orderbook_entries(con: duckdb.DuckDBPyConnection, entry_seconds: list[int], staleness_s: int) -> pd.DataFrame:
    values = ",".join(f"({int(t)})" for t in entry_seconds)
    rows = con.execute(f"""
        WITH target(entry_t) AS (VALUES {values}),
        flat AS (
          SELECT
            window_id,
            market_id,
            CAST(epoch(ts_open) AS BIGINT) AS ts_open_s,
            CAST(epoch(ts_close) AS BIGINT) AS ts_close_s,
            900.0 - time_to_close_s AS from_open_s,
            best_ask_up,
            best_ask_down,
            ask_size_up,
            ask_size_down,
            spread_up,
            spread_down
          FROM '{ORDERBOOK.as_posix()}'
          WHERE best_ask_up BETWEEN 0 AND 1
            AND best_ask_down BETWEEN 0 AND 1
            AND spread_up >= 0
            AND spread_down >= 0
        ),
        cand AS (
          SELECT
            flat.*,
            target.entry_t,
            row_number() OVER (
              PARTITION BY flat.window_id, target.entry_t
              ORDER BY flat.from_open_s ASC
            ) AS rn
          FROM flat
          JOIN target
            ON flat.from_open_s >= target.entry_t
           AND flat.from_open_s <= target.entry_t + {int(staleness_s)}
        )
        SELECT
          window_id,
          market_id,
          ts_open_s,
          ts_close_s,
          entry_t,
          from_open_s AS actual_entry_t,
          best_ask_up,
          best_ask_down,
          ask_size_up,
          ask_size_down,
          spread_up,
          spread_down
        FROM cand
        WHERE rn = 1
        ORDER BY window_id, entry_t
    """).df()
    if rows.empty:
        return pd.DataFrame({"window_id": []})
    idx = rows[["window_id", "market_id", "ts_open_s", "ts_close_s"]].drop_duplicates("window_id")
    wide = idx.set_index("window_id")
    for col in ["best_ask_up", "best_ask_down", "ask_size_up", "ask_size_down", "spread_up", "spread_down", "actual_entry_t"]:
        p = rows.pivot(index="window_id", columns="entry_t", values=col)
        p.columns = [f"ob_{col}_e{int(c)}" for c in p.columns]
        wide = wide.join(p)
    for entry_t in entry_seconds:
        actual = f"ob_actual_entry_t_e{entry_t}"
        if actual in wide.columns:
            wide[f"ob_delay_s_e{entry_t}"] = wide[actual] - entry_t
    return wide.reset_index()


def scan_dataset(
    df: pd.DataFrame,
    source: str,
    lookbacks: list[int],
    gaps: list[int],
    entry_seconds: list[int],
    thresholds: list[float],
    fee_rate: float,
    min_n: int,
    size_thresholds: list[float] | None = None,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    size_thresholds = size_thresholds or [0.0]

    for lookback in lookbacks:
        for gap in gaps:
            mom_col = f"mom_l{lookback}_g{gap}"
            if mom_col not in df.columns:
                continue
            for entry_t in entry_seconds:
                if source == "proxy":
                    up_col = f"proxy_up_price_e{entry_t}"
                    delay_col = f"proxy_delay_s_e{entry_t}"
                    if up_col not in df.columns:
                        continue
                else:
                    ask_up_col = f"ob_best_ask_up_e{entry_t}"
                    ask_down_col = f"ob_best_ask_down_e{entry_t}"
                    size_up_col = f"ob_ask_size_up_e{entry_t}"
                    size_down_col = f"ob_ask_size_down_e{entry_t}"
                    spread_up_col = f"ob_spread_up_e{entry_t}"
                    spread_down_col = f"ob_spread_down_e{entry_t}"
                    delay_col = f"ob_delay_s_e{entry_t}"
                    if ask_up_col not in df.columns or ask_down_col not in df.columns:
                        continue

                for threshold in thresholds:
                    for size_threshold in size_thresholds:
                        base = df[df[mom_col].notna() & (df[mom_col].abs() >= threshold) & (df[mom_col] != 0)].copy()
                        if base.empty:
                            continue
                        pred_up = base[mom_col] > 0

                        if source == "proxy":
                            base = base[base[up_col].notna()].copy()
                            if base.empty:
                                continue
                            pred_up = base[mom_col] > 0
                            entry = np.where(pred_up, base[up_col], 1.0 - base[up_col])
                            capacity = np.full(len(base), np.nan)
                            spread = np.full(len(base), np.nan)
                        else:
                            base = base[base[ask_up_col].notna() & base[ask_down_col].notna()].copy()
                            if base.empty:
                                continue
                            pred_up = base[mom_col] > 0
                            entry = np.where(pred_up, base[ask_up_col], base[ask_down_col])
                            capacity = np.where(pred_up, base[size_up_col], base[size_down_col])
                            spread = np.where(pred_up, base[spread_up_col], base[spread_down_col])
                            ok_capacity = capacity >= size_threshold
                            base = base[ok_capacity].copy()
                            entry = entry[ok_capacity]
                            capacity = capacity[ok_capacity]
                            spread = spread[ok_capacity]
                            pred_up = base[mom_col] > 0
                            if base.empty:
                                continue

                        entry = np.asarray(entry, dtype=float)
                        valid_price = np.isfinite(entry) & (entry >= 0) & (entry <= 1)
                        base = base[valid_price].copy()
                        entry = entry[valid_price]
                        capacity = capacity[valid_price]
                        spread = spread[valid_price]
                        pred_up = base[mom_col] > 0
                        if base.empty:
                            continue

                        win = np.where(pred_up, base["outcome"].eq("Up"), base["outcome"].eq("Down")).astype(float)
                        fee = fee_rate * entry * (1.0 - entry)
                        net = win - entry - fee
                        gross = win - entry
                        delay = base[delay_col].to_numpy(dtype=float) if delay_col in base.columns else np.full(len(base), np.nan)

                        calc = pd.DataFrame({
                            "split": base["split"].to_numpy(),
                            "win": win,
                            "entry": entry,
                            "fee": fee,
                            "gross": gross,
                            "net": net,
                            "delay": delay,
                            "capacity": capacity,
                            "spread": spread,
                        })

                        for split_name, sub in calc.groupby("split", sort=False):
                            n = int(len(sub))
                            if n < min_n:
                                continue
                            vals = sub["net"].to_numpy(dtype=float)
                            tt = ttest_1samp(vals, 0.0, alternative="greater")
                            ci_low, ci_high = bootstrap_ci(vals)
                            rows.append({
                                "source": source,
                                "split": split_name,
                                "lookback_min": lookback,
                                "gap_min": gap,
                                "entry_t_s": entry_t,
                                "abs_momentum_threshold": threshold,
                                "ask_size_threshold": size_threshold if source == "orderbook" else None,
                                "n": n,
                                "accuracy": float(sub["win"].mean()),
                                "mean_entry": float(sub["entry"].mean()),
                                "mean_fee": float(sub["fee"].mean()),
                                "mean_gross_pnl": float(sub["gross"].mean()),
                                "mean_net_pnl": float(sub["net"].mean()),
                                "median_net_pnl": float(sub["net"].median()),
                                "ci95_net_low": ci_low,
                                "ci95_net_high": ci_high,
                                "ttest_p_greater": finite_float(tt.pvalue),
                                "bootstrap_p_greater": bootstrap_p_greater_zero(vals),
                                "mean_entry_delay_s": finite_mean(sub["delay"]),
                                "median_entry_delay_s": finite_median(sub["delay"]),
                                "mean_capacity": finite_mean(sub["capacity"]),
                                "median_capacity": finite_median(sub["capacity"]),
                                "mean_spread": finite_mean(sub["spread"]),
                            })

    out = pd.DataFrame(rows)
    if out.empty:
        return out
    size_part = pd.to_numeric(out["ask_size_threshold"], errors="coerce").fillna(0.0).astype(str)
    out["rule_id"] = (
        out["source"].astype(str)
        + "_L" + out["lookback_min"].astype(str)
        + "_G" + out["gap_min"].astype(str)
        + "_E" + out["entry_t_s"].astype(str)
        + "_T" + out["abs_momentum_threshold"].astype(str)
        + "_S" + size_part
    )
    for (source_name, split_name), idx in out.groupby(["source", "split"]).groups.items():
        n_rules = len(idx)
        out.loc[idx, "n_rules_in_split"] = n_rules
        out.loc[idx, "bootstrap_p_bonferroni"] = np.minimum(1.0, out.loc[idx, "bootstrap_p_greater"].fillna(1.0) * n_rules)
        out.loc[idx, "ttest_p_bonferroni"] = np.minimum(1.0, out.loc[idx, "ttest_p_greater"].fillna(1.0) * n_rules)
    return out.sort_values(
        ["source", "split", "bootstrap_p_bonferroni", "mean_net_pnl"],
        ascending=[True, True, True, False],
    )


def paired_train_validation(results: pd.DataFrame, source: str) -> pd.DataFrame:
    if results.empty:
        return pd.DataFrame()
    train = results[(results["source"] == source) & (results["split"] == "train")].copy()
    val = results[(results["source"] == source) & (results["split"] == "validation")].copy()
    if train.empty or val.empty:
        return pd.DataFrame()
    keep_cols = [
        "rule_id", "lookback_min", "gap_min", "entry_t_s", "abs_momentum_threshold", "ask_size_threshold",
        "n", "accuracy", "mean_entry", "mean_fee", "mean_net_pnl", "ci95_net_low",
        "bootstrap_p_greater", "bootstrap_p_bonferroni", "mean_entry_delay_s",
        "median_capacity", "mean_spread",
    ]
    m = train[keep_cols].merge(val[keep_cols], on="rule_id", suffixes=("_train", "_validation"))
    m = m.sort_values(
        ["bootstrap_p_bonferroni_validation", "mean_net_pnl_validation", "mean_net_pnl_train"],
        ascending=[True, False, False],
    )
    return m


def write_summary(
    proxy_results: pd.DataFrame,
    orderbook_results: pd.DataFrame,
    proxy_pairs: pd.DataFrame,
    orderbook_pairs: pd.DataFrame,
    report: dict[str, Any],
) -> None:
    suffix = f"_{report.get('tag')}" if report.get("tag") else ""
    out = REPORT_DIR / f"momentum_lookback_costed_summary{suffix}.md"
    lines = [
        "# Momentum lookback costed scan",
        "",
        f"Run UTC: `{report['run_at_utc']}`",
        "",
        "## Protocol",
        "",
        "BTC is treated as a laboratory sample because it has already been inspected. A rule selected here still requires independent ETH/SOL/live validation.",
        "",
        "Cost formula:",
        "",
        "```text",
        "taker_fee = fee_rate * entry_price * (1 - entry_price)",
        "pnl_net = win - entry_price - taker_fee",
        "```",
        "",
        f"Fee rate used: `{report['fee_rate']}`",
        "",
        "## Proxy Top Train+Validation",
        "",
    ]

    def add_table(df: pd.DataFrame, source: str) -> None:
        if df.empty:
            lines.append(f"No paired {source} rules met minimum n.")
            return
        cols = [
            "rule_id",
            "n_train",
            "mean_net_pnl_train",
            "ci95_net_low_train",
            "bootstrap_p_bonferroni_train",
            "n_validation",
            "mean_net_pnl_validation",
            "ci95_net_low_validation",
            "bootstrap_p_bonferroni_validation",
            "mean_entry_validation",
            "mean_entry_delay_s_validation",
        ]
        if source == "orderbook":
            cols += ["median_capacity_validation", "mean_spread_validation"]
        lines.append("| " + " | ".join(cols) + " |")
        lines.append("|" + "|".join(["---"] * len(cols)) + "|")
        for _, r in df.head(15).iterrows():
            vals = []
            for c in cols:
                v = r.get(c)
                if isinstance(v, float):
                    vals.append(f"{v:.6g}")
                else:
                    vals.append(str(v))
            lines.append("| " + " | ".join(vals) + " |")

    add_table(proxy_pairs, "proxy")
    lines += ["", "## Orderbook Top Train+Validation", ""]
    add_table(orderbook_pairs, "orderbook")

    lines += [
        "",
        "## Files",
        "",
        "- `reports/phases/momentum_lookback_scan_proxy_prices.csv`",
        "- `reports/phases/momentum_lookback_scan_orderbook_costed.csv`",
        "- `reports/phases/momentum_lookback_scan_report.json`",
    ]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lookbacks-min", default="1,2,3,5,10,15,30")
    ap.add_argument("--gaps-min", default="0,1,2")
    ap.add_argument("--entry-seconds", default="0,10,30,60")
    ap.add_argument("--thresholds", default="0,0.0005,0.001,0.002")
    ap.add_argument("--orderbook-size-thresholds", default="1,100,1000")
    ap.add_argument("--fee-rate", type=float, default=0.07)
    ap.add_argument("--proxy-staleness-s", type=int, default=90)
    ap.add_argument("--orderbook-staleness-s", type=int, default=5)
    ap.add_argument("--min-n-proxy", type=int, default=300)
    ap.add_argument("--min-n-orderbook", type=int, default=50)
    ap.add_argument("--tag", default="")
    args = ap.parse_args()

    for path in [WINDOWS, OUTCOMES, TRAJ, BINANCE, ORDERBOOK]:
        if not path.exists():
            raise FileNotFoundError(path)

    lookbacks = parse_csv_ints(args.lookbacks_min)
    gaps = parse_csv_ints(args.gaps_min)
    entry_seconds = parse_csv_ints(args.entry_seconds)
    thresholds = parse_csv_floats(args.thresholds)
    ob_sizes = parse_csv_floats(args.orderbook_size_thresholds)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("SET threads TO 4")

    print("Loading base data...")
    binance = load_binance(con)
    base = add_splits(add_spot_features(load_base_windows(con), binance, lookbacks, gaps))

    print("Loading proxy entries...")
    proxy_entries = load_proxy_entries(con, entry_seconds, args.proxy_staleness_s)
    proxy_df = base.merge(proxy_entries, on="window_id", how="inner")
    print(f"Proxy windows: {len(proxy_df):,}")

    print("Scanning proxy...")
    proxy_results = scan_dataset(
        proxy_df,
        source="proxy",
        lookbacks=lookbacks,
        gaps=gaps,
        entry_seconds=entry_seconds,
        thresholds=thresholds,
        fee_rate=args.fee_rate,
        min_n=args.min_n_proxy,
    )

    print("Loading orderbook entries...")
    ob_entries = load_orderbook_entries(con, entry_seconds, args.orderbook_staleness_s)
    ob_base = load_base_windows(con).merge(ob_entries.drop(columns=["market_id", "ts_open_s", "ts_close_s"], errors="ignore"), on="window_id", how="inner")
    ob_base = add_splits(add_spot_features(ob_base, binance, lookbacks, gaps))
    print(f"Orderbook windows: {len(ob_base):,}")

    print("Scanning orderbook...")
    orderbook_results = scan_dataset(
        ob_base,
        source="orderbook",
        lookbacks=lookbacks,
        gaps=gaps,
        entry_seconds=entry_seconds,
        thresholds=thresholds,
        fee_rate=args.fee_rate,
        min_n=args.min_n_orderbook,
        size_thresholds=ob_sizes,
    )

    suffix = f"_{args.tag}" if args.tag else ""
    proxy_csv = REPORT_DIR / f"momentum_lookback_scan_proxy_prices{suffix}.csv"
    ob_csv = REPORT_DIR / f"momentum_lookback_scan_orderbook_costed{suffix}.csv"
    report_json = REPORT_DIR / f"momentum_lookback_scan_report{suffix}.json"
    proxy_results.to_csv(proxy_csv, index=False)
    orderbook_results.to_csv(ob_csv, index=False)

    proxy_pairs = paired_train_validation(proxy_results, "proxy")
    ob_pairs = paired_train_validation(orderbook_results, "orderbook")
    if not proxy_pairs.empty:
        proxy_pairs.to_csv(REPORT_DIR / f"momentum_lookback_proxy_train_validation_pairs{suffix}.csv", index=False)
    if not ob_pairs.empty:
        ob_pairs.to_csv(REPORT_DIR / f"momentum_lookback_orderbook_train_validation_pairs{suffix}.csv", index=False)

    report = {
        "scan": "momentum_lookbacks_costed",
        "run_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "interpretation": "BTC lab scan only; independent validation required.",
        "grid": {
            "lookbacks_min": lookbacks,
            "gaps_min": gaps,
            "entry_seconds": entry_seconds,
            "thresholds": thresholds,
            "orderbook_size_thresholds": ob_sizes,
        },
        "fee_rate": args.fee_rate,
        "tag": args.tag,
        "fee_formula": "fee = fee_rate * entry_price * (1 - entry_price)",
        "staleness": {
            "proxy_staleness_s": args.proxy_staleness_s,
            "orderbook_staleness_s": args.orderbook_staleness_s,
        },
        "data_hashes": {
            "windows": file_sha256(WINDOWS),
            "outcomes": file_sha256(OUTCOMES),
            "pm_trajectory": file_sha256(TRAJ),
            "binance_btc_1m": file_sha256(BINANCE),
            "orderbook_snapshots": file_sha256(ORDERBOOK),
        },
        "rows": {
            "base_windows": int(len(base)),
            "proxy_windows": int(len(proxy_df)),
            "orderbook_windows": int(len(ob_base)),
            "proxy_result_rows": int(len(proxy_results)),
            "orderbook_result_rows": int(len(orderbook_results)),
        },
        "top_proxy_train_validation": proxy_pairs.head(25).to_dict(orient="records") if not proxy_pairs.empty else [],
        "top_orderbook_train_validation": ob_pairs.head(25).to_dict(orient="records") if not ob_pairs.empty else [],
        "outputs": {
            "proxy_csv": proxy_csv.as_posix(),
            "orderbook_csv": ob_csv.as_posix(),
        },
    }
    report_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    write_summary(proxy_results, orderbook_results, proxy_pairs, ob_pairs, report)

    print("\nTop proxy train+validation:")
    if proxy_pairs.empty:
        print("No paired proxy rules.")
    else:
        print(proxy_pairs.head(10)[[
            "rule_id", "n_train", "mean_net_pnl_train", "bootstrap_p_bonferroni_train",
            "n_validation", "mean_net_pnl_validation", "bootstrap_p_bonferroni_validation",
            "mean_entry_validation",
        ]].to_string(index=False))

    print("\nTop orderbook train+validation:")
    if ob_pairs.empty:
        print("No paired orderbook rules.")
    else:
        print(ob_pairs.head(10)[[
            "rule_id", "n_train", "mean_net_pnl_train", "bootstrap_p_bonferroni_train",
            "n_validation", "mean_net_pnl_validation", "bootstrap_p_bonferroni_validation",
            "mean_entry_validation", "median_capacity_validation",
        ]].to_string(index=False))

    print(f"\nSaved: {proxy_csv}")
    print(f"Saved: {ob_csv}")
    print(f"Saved: {report_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
