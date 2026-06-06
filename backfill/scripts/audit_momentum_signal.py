"""Audit the BTC 15m momentum claim without changing the rule.

Rule under audit:
  ts_open = end_ts - 900
  momentum_5m = Binance close at ts_open - Binance close at ts_open - 300s
  predict Up if momentum_5m > 0, Down if momentum_5m < 0

Guardrails:
  - No threshold optimization.
  - Split is made before dropping zero-momentum rows.
  - Primary population is all BTC 15m windows with outcome and pm open price.
  - TRAIN/HOLDOUT are chronological by ts_open, window_id.
  - Binance joins are exact minute joins at ts_open and ts_open - 5m.

Outputs:
  reports/phases/momentum_audit_report.json
  reports/phases/momentum_audit_report.md
"""

from __future__ import annotations

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
from scipy.stats import binomtest, pearsonr, spearmanr, ttest_1samp

WINDOWS = ROOT / "data" / "raw" / "polymarket_markets_btc15m.parquet"
OUTCOMES = ROOT / "data" / "interim" / "outcomes.parquet"
PM_OPEN = ROOT / "data" / "interim" / "pm_open.parquet"
DATASET = ROOT / "data" / "processed" / "research_dataset_v1.parquet"
BINANCE = ROOT / "data" / "raw" / "binance_btc_1m.jsonl"
CHAINLINK = ROOT / "data" / "interim" / "chainlink_refs.parquet"
REPORT_DIR = ROOT / "reports" / "phases"
JSON_OUT = REPORT_DIR / "momentum_audit_report.json"
MD_OUT = REPORT_DIR / "momentum_audit_report.md"

FEE_RATE = 0.018
DOC_HOLDOUT_N = 2769
DOC_HOLDOUT_ACCURACY = 0.5421
DOC_BREAK_EVEN_ACCURACY = 0.527


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 24), b""):
            h.update(chunk)
    return h.hexdigest()


def finite_float(x: Any) -> float | None:
    try:
        v = float(x)
    except Exception:
        return None
    if math.isnan(v) or math.isinf(v):
        return None
    return v


def bootstrap_p_greater_zero(values: np.ndarray, seed: int = 42, n_resamples: int = 5000) -> float | None:
    if len(values) == 0:
        return None
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(values), size=(n_resamples, len(values)))
    means = values[idx].mean(axis=1)
    return float((means <= 0).mean())


def bootstrap_ci(values: np.ndarray, seed: int = 123, n_resamples: int = 5000) -> tuple[float | None, float | None]:
    if len(values) == 0:
        return None, None
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(values), size=(n_resamples, len(values)))
    means = values[idx].mean(axis=1)
    lo, hi = np.quantile(means, [0.025, 0.975])
    return float(lo), float(hi)


def load_binance(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return con.execute(f"""
        SELECT
          CAST(ts / 1000 AS BIGINT) AS ts_s,
          CAST(close AS DOUBLE) AS close
        FROM read_json_auto(
          '{BINANCE.as_posix()}',
          format='newline_delimited',
          columns={{'ts':'BIGINT','close':'DOUBLE'}}
        )
        ORDER BY ts_s
    """).df()


def load_population(con: duckdb.DuckDBPyConnection, population: str) -> pd.DataFrame:
    if population == "all_windows":
        return con.execute(f"""
            SELECT
              w.condition_id AS window_id,
              w.market_id,
              CAST(w.end_ts - 900 AS BIGINT) AS ts_open_s,
              CAST(w.end_ts AS BIGINT) AS ts_close_s,
              o.outcome,
              CAST(pm.pm_up_price_open AS DOUBLE) AS pm_up_price_open,
              CAST(cl.price_to_beat AS DOUBLE) AS price_to_beat
            FROM '{WINDOWS.as_posix()}' w
            JOIN '{OUTCOMES.as_posix()}' o ON w.condition_id = o.condition_id
            JOIN '{PM_OPEN.as_posix()}' pm ON w.condition_id = pm.window_id
            LEFT JOIN '{CHAINLINK.as_posix()}' cl ON w.condition_id = cl.window_id
            WHERE w.crypto = 'BTC'
              AND w.timeframe = '15-minute'
              AND o.outcome IN ('Up','Down')
              AND pm.pm_up_price_open IS NOT NULL
            ORDER BY ts_open_s, window_id
        """).df()
    if population == "research_all":
        return con.execute(f"""
            SELECT
              window_id,
              NULL AS market_id,
              CAST(epoch(ts_open) AS BIGINT) AS ts_open_s,
              CAST(epoch(ts_close) AS BIGINT) AS ts_close_s,
              outcome,
              CAST(pm_up_price_open AS DOUBLE) AS pm_up_price_open,
              CAST(price_to_beat AS DOUBLE) AS price_to_beat
            FROM '{DATASET.as_posix()}'
            WHERE outcome IN ('Up','Down')
              AND pm_up_price_open IS NOT NULL
            ORDER BY ts_open_s, window_id
        """).df()
    if population == "canonical_n_trades_ge_30":
        return con.execute(f"""
            SELECT
              window_id,
              NULL AS market_id,
              CAST(epoch(ts_open) AS BIGINT) AS ts_open_s,
              CAST(epoch(ts_close) AS BIGINT) AS ts_close_s,
              outcome,
              CAST(pm_up_price_open AS DOUBLE) AS pm_up_price_open,
              CAST(price_to_beat AS DOUBLE) AS price_to_beat
            FROM '{DATASET.as_posix()}'
            WHERE outcome IN ('Up','Down')
              AND pm_up_price_open IS NOT NULL
              AND n_trades_15m >= 30
            ORDER BY ts_open_s, window_id
        """).df()
    raise ValueError(population)


def attach_momentum(base: pd.DataFrame, binance: pd.DataFrame) -> pd.DataFrame:
    now = binance.rename(columns={"ts_s": "ts_open_s", "close": "btc_open_close"})
    lag = binance.rename(columns={"ts_s": "ts_lag_s", "close": "btc_lag_close"})
    df = base.merge(now, on="ts_open_s", how="left")
    df["ts_lag_s"] = df["ts_open_s"] - 300
    df = df.merge(lag, on="ts_lag_s", how="left")
    df["momentum_5m"] = df["btc_open_close"] - df["btc_lag_close"]
    df["momentum_5m_ret"] = df["momentum_5m"] / df["btc_lag_close"]
    return df


def split_frame(df: pd.DataFrame) -> pd.DataFrame:
    out = df.sort_values(["ts_open_s", "window_id"]).reset_index(drop=True).copy()
    cut = int(len(out) * 0.7)
    out["split"] = np.where(np.arange(len(out)) < cut, "train", "holdout")
    return out


def evaluate_subset(df: pd.DataFrame) -> dict[str, Any]:
    ev = df[df["momentum_5m"].notna() & (df["momentum_5m"] != 0)].copy()
    if ev.empty:
        return {
            "n": 0,
            "missing_momentum": int(df["momentum_5m"].isna().sum()),
            "zero_momentum": int((df["momentum_5m"] == 0).sum()),
        }

    pred_up = ev["momentum_5m"] > 0
    hit = np.where(pred_up, ev["outcome"].eq("Up"), ev["outcome"].eq("Down")).astype(float)
    entry = np.where(pred_up, ev["pm_up_price_open"], 1.0 - ev["pm_up_price_open"])
    gross_pnl = hit - entry
    net_pnl = hit - entry * (1.0 + FEE_RATE)

    acc = float(hit.mean())
    n = int(len(ev))
    wins = int(hit.sum())
    b = binomtest(wins, n, 0.5, alternative="greater")
    tt_net = ttest_1samp(net_pnl, 0.0, alternative="greater")
    ci_low, ci_high = bootstrap_ci(net_pnl)
    return {
        "n": n,
        "wins": wins,
        "accuracy": acc,
        "binom_p_greater": float(b.pvalue),
        "missing_momentum": int(df["momentum_5m"].isna().sum()),
        "zero_momentum": int((df["momentum_5m"] == 0).sum()),
        "mean_entry": float(np.mean(entry)),
        "mean_entry_with_fee": float(np.mean(entry * (1.0 + FEE_RATE))),
        "break_even_accuracy_flat_fee": float(np.mean(entry * (1.0 + FEE_RATE))),
        "accuracy_minus_break_even": float(acc - np.mean(entry * (1.0 + FEE_RATE))),
        "mean_gross_pnl": float(np.mean(gross_pnl)),
        "mean_net_pnl": float(np.mean(net_pnl)),
        "median_net_pnl": float(np.median(net_pnl)),
        "net_ttest_p_greater": finite_float(tt_net.pvalue),
        "net_bootstrap_p_greater": bootstrap_p_greater_zero(net_pnl),
        "net_bootstrap_ci95_low": ci_low,
        "net_bootstrap_ci95_high": ci_high,
    }


def threshold_table(df: pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    for split in ["train", "holdout", "all"]:
        part = df if split == "all" else df[df["split"] == split]
        part = part[part["momentum_5m"].notna() & (part["momentum_5m"] != 0)].copy()
        for thr in [0.0, 0.001, 0.002]:
            sub = part[part["momentum_5m_ret"].abs() >= thr]
            if sub.empty:
                rows.append({"split": split, "abs_momentum_ret_threshold": thr, "n": 0})
                continue
            pred_up = sub["momentum_5m"] > 0
            hit = np.where(pred_up, sub["outcome"].eq("Up"), sub["outcome"].eq("Down")).astype(float)
            rows.append({
                "split": split,
                "abs_momentum_ret_threshold": thr,
                "n": int(len(sub)),
                "coverage_of_split": float(len(sub) / len(part)) if len(part) else None,
                "accuracy": float(hit.mean()),
            })
    return rows


def mechanism_stats(df: pd.DataFrame) -> dict[str, Any]:
    ev = df[df["momentum_5m"].notna() & (df["momentum_5m"] != 0)].copy()
    out: dict[str, Any] = {}
    if len(ev) >= 3:
        x = ev["momentum_5m_ret"].to_numpy(dtype=float)
        y = (ev["pm_up_price_open"] - 0.5).to_numpy(dtype=float)
        pr = pearsonr(x, y)
        sr = spearmanr(x, y)
        out["corr_momentum_ret_vs_pm_open_minus_half"] = {
            "pearson_r": float(pr.statistic),
            "pearson_p": float(pr.pvalue),
            "spearman_rho": float(sr.statistic),
            "spearman_p": float(sr.pvalue),
            "n": int(len(ev)),
        }

    regimes = []
    for name, sub in [("bullish_momentum", ev[ev["momentum_5m"] > 0]), ("bearish_momentum", ev[ev["momentum_5m"] < 0])]:
        if sub.empty:
            continue
        p_up = float(sub["outcome"].eq("Up").mean())
        pm_up = float(sub["pm_up_price_open"].mean())
        regimes.append({
            "regime": name,
            "n": int(len(sub)),
            "realized_p_up": p_up,
            "mean_pm_up_price_open": pm_up,
            "up_gap_realized_minus_price": p_up - pm_up,
            "down_gap_realized_minus_price": (1.0 - p_up) - (1.0 - pm_up),
        })
    out["regimes"] = regimes

    ev_all = ev.assign(mom_signal=np.sign(ev["momentum_5m"]))
    price_signal = np.sign(ev_all["pm_up_price_open"] - 0.5)
    ev = ev_all.assign(price_signal=price_signal)
    ev = ev[ev["price_signal"] != 0].copy()
    pieces = {}
    for label, cond in [("agree", ev["price_signal"] * ev["mom_signal"] > 0), ("disagree", ev["price_signal"] * ev["mom_signal"] < 0)]:
        sub = ev[cond]
        if sub.empty:
            pieces[label] = {"n": 0}
            continue
        pred_up = sub["mom_signal"] > 0
        hit = np.where(pred_up, sub["outcome"].eq("Up"), sub["outcome"].eq("Down")).astype(float)
        pieces[label] = {"n": int(len(sub)), "accuracy": float(hit.mean())}
    out["momentum_vs_pm_price_signal"] = pieces

    if "price_to_beat" in ev_all.columns and "btc_open_close" in ev_all.columns:
        ptb_ev = ev_all[ev_all["price_to_beat"].notna() & ev_all["btc_open_close"].notna()].copy()
        ptb_ev = ptb_ev.assign(price_to_beat_signal=np.sign(ptb_ev["btc_open_close"] - ptb_ev["price_to_beat"]))
        ptb_ev = ptb_ev[ptb_ev["price_to_beat_signal"] != 0].copy()
        ptb_pieces = {}
        for label, cond in [
            ("agree", ptb_ev["price_to_beat_signal"] * ptb_ev["mom_signal"] > 0),
            ("disagree", ptb_ev["price_to_beat_signal"] * ptb_ev["mom_signal"] < 0),
        ]:
            sub = ptb_ev[cond]
            if sub.empty:
                ptb_pieces[label] = {"n": 0}
                continue
            pred_up = sub["mom_signal"] > 0
            hit = np.where(pred_up, sub["outcome"].eq("Up"), sub["outcome"].eq("Down")).astype(float)
            ptb_pieces[label] = {"n": int(len(sub)), "accuracy": float(hit.mean())}
        out["momentum_vs_price_to_beat_signal"] = ptb_pieces
    return out


def audit_population(population: str, binance: pd.DataFrame, con: duckdb.DuckDBPyConnection) -> tuple[pd.DataFrame, dict[str, Any]]:
    base = load_population(con, population)
    df = split_frame(attach_momentum(base, binance))
    by_split = {
        "train": evaluate_subset(df[df["split"] == "train"]),
        "holdout": evaluate_subset(df[df["split"] == "holdout"]),
        "all": evaluate_subset(df),
    }
    split_ranges = {}
    for split in ["train", "holdout"]:
        part = df[df["split"] == split]
        split_ranges[split] = {
            "rows_before_zero_drop": int(len(part)),
            "min_ts_open_s": int(part["ts_open_s"].min()) if len(part) else None,
            "max_ts_open_s": int(part["ts_open_s"].max()) if len(part) else None,
        }

    report = {
        "population": population,
        "rows_before_zero_drop": int(len(df)),
        "split_cut_floor_70pct": int(len(df) * 0.7),
        "split_ranges": split_ranges,
        "binance_join": {
            "missing_open_price": int(df["btc_open_close"].isna().sum()),
            "missing_lag_price": int(df["btc_lag_close"].isna().sum()),
            "max_signal_ts_minus_open_s": 0,
            "lag_seconds": 300,
        },
        "metrics": by_split,
        "threshold_table": threshold_table(df),
        "mechanism_by_split": {
            "train": mechanism_stats(df[df["split"] == "train"]),
            "holdout": mechanism_stats(df[df["split"] == "holdout"]),
            "all": mechanism_stats(df),
        },
    }
    return df, report


def write_markdown(report: dict[str, Any]) -> None:
    primary = report["populations"]["all_windows"]
    hold = primary["metrics"]["holdout"]
    train = primary["metrics"]["train"]
    mech = primary["mechanism_by_split"]["holdout"]
    corr = mech.get("corr_momentum_ret_vs_pm_open_minus_half", {})
    regimes = mech.get("regimes", [])
    thresholds = [
        r for r in primary["threshold_table"]
        if r.get("split") == "holdout"
    ]

    lines = [
        "# Momentum audit report",
        "",
        f"Run UTC: `{report['run_at_utc']}`",
        "",
        "## Primary population",
        "",
        "`all_windows` = BTC 15m windows joined from raw markets + CLOB outcomes + pm open price.",
        "",
        "Formula:",
        "",
        "```text",
        "ts_open = end_ts - 900",
        "momentum_5m = Binance_close[ts_open] - Binance_close[ts_open - 300s]",
        "predict Up if momentum_5m > 0, Down if momentum_5m < 0",
        "split = chronological 70/30 before dropping zero momentum",
        "```",
        "",
        "## Result",
        "",
        "| split | n | accuracy | binom p | mean entry+fee | acc - breakeven | mean net pnl | net bootstrap p |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, m in [("train", train), ("holdout", hold), ("all", primary["metrics"]["all"])]:
        lines.append(
            f"| {name} | {m.get('n', 0):,} | {m.get('accuracy', 0):.4f} | "
            f"{m.get('binom_p_greater', 1):.4g} | {m.get('mean_entry_with_fee', 0):.4f} | "
            f"{m.get('accuracy_minus_break_even', 0):.4f} | {m.get('mean_net_pnl', 0):.4f} | "
            f"{m.get('net_bootstrap_p_greater', 1):.4g} |"
        )

    lines += [
        "",
        "## Compare with ESTUDIO_MOMENTUM.md",
        "",
        f"- Document claim holdout n: `{DOC_HOLDOUT_N}`",
        f"- Reproduced holdout n: `{hold.get('n')}`",
        f"- Document claim holdout accuracy: `{DOC_HOLDOUT_ACCURACY:.4f}`",
        f"- Reproduced holdout accuracy: `{hold.get('accuracy', 0):.4f}`",
        f"- Accuracy delta: `{hold.get('accuracy', 0) - DOC_HOLDOUT_ACCURACY:+.4f}`",
        f"- Document claim break-even accuracy: `{DOC_BREAK_EVEN_ACCURACY:.4f}`",
        f"- Reproduced break-even under `entry*(1+0.018)`: `{hold.get('break_even_accuracy_flat_fee', 0):.4f}`",
        f"- Break-even delta: `{hold.get('break_even_accuracy_flat_fee', 0) - DOC_BREAK_EVEN_ACCURACY:+.4f}`",
        "",
        "## Holdout threshold diagnostic",
        "",
        "| abs momentum ret threshold | n | coverage | accuracy |",
        "|---:|---:|---:|---:|",
    ]
    for r in thresholds:
        lines.append(
            f"| {r.get('abs_momentum_ret_threshold', 0):.4f} | {r.get('n', 0):,} | "
            f"{r.get('coverage_of_split', 0):.4f} | {r.get('accuracy', 0):.4f} |"
        )

    lines += [
        "",
        "## Holdout mechanism diagnostic",
        "",
        f"- Pearson corr(momentum_ret, pm_open - 0.5): `{corr.get('pearson_r', float('nan')):.4f}` "
        f"(p=`{corr.get('pearson_p', float('nan')):.4g}`, n=`{corr.get('n', 0)}`)",
        "",
        "| regime | n | realized P(Up) | mean pm Up price | Up gap | Down gap |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for r in regimes:
        lines.append(
            f"| {r['regime']} | {r['n']:,} | {r['realized_p_up']:.4f} | "
            f"{r['mean_pm_up_price_open']:.4f} | {r['up_gap_realized_minus_price']:+.4f} | "
            f"{r['down_gap_realized_minus_price']:+.4f} |"
        )

    disagree = mech.get("momentum_vs_pm_price_signal", {}).get("disagree", {})
    agree = mech.get("momentum_vs_pm_price_signal", {}).get("agree", {})
    ptb_disagree = mech.get("momentum_vs_price_to_beat_signal", {}).get("disagree", {})
    ptb_agree = mech.get("momentum_vs_price_to_beat_signal", {}).get("agree", {})
    lines += [
        "",
        "## Momentum vs PM open-price signal",
        "",
        f"- Agree: n=`{agree.get('n', 0)}`, momentum accuracy=`{agree.get('accuracy')}`",
        f"- Disagree: n=`{disagree.get('n', 0)}`, momentum accuracy=`{disagree.get('accuracy')}`",
        "",
        "## Momentum vs BTC price_to_beat signal",
        "",
        f"- Agree: n=`{ptb_agree.get('n', 0)}`, momentum accuracy=`{ptb_agree.get('accuracy')}`",
        f"- Disagree: n=`{ptb_disagree.get('n', 0)}`, momentum accuracy=`{ptb_disagree.get('accuracy')}`",
        "",
        "## Verdict",
        "",
        "This report reproduces the exact BTC momentum rule on local data. It does not confirm an independent edge because this is still the previously touched BTC sample. Independent ETH/SOL/live data remain required.",
    ]
    MD_OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    for path in [WINDOWS, OUTCOMES, PM_OPEN, DATASET, BINANCE, CHAINLINK]:
        if not path.exists():
            raise FileNotFoundError(path)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("SET threads TO 4")
    binance = load_binance(con)

    populations: dict[str, Any] = {}
    for pop in ["all_windows", "research_all", "canonical_n_trades_ge_30"]:
        _, pop_report = audit_population(pop, binance, con)
        populations[pop] = pop_report

    report = {
        "audit": "BTC_15m_momentum_signal",
        "run_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "fee_rate": FEE_RATE,
        "data_hashes": {
            "windows": file_sha256(WINDOWS),
            "outcomes": file_sha256(OUTCOMES),
            "pm_open": file_sha256(PM_OPEN),
            "research_dataset": file_sha256(DATASET),
            "binance_btc_1m": file_sha256(BINANCE),
            "chainlink_refs": file_sha256(CHAINLINK),
        },
        "binance_coverage": {
            "rows": int(len(binance)),
            "min_ts_s": int(binance["ts_s"].min()),
            "max_ts_s": int(binance["ts_s"].max()),
            "gaps_not_equal_60s": int((binance["ts_s"].diff().dropna() != 60).sum()),
        },
        "doc_claims": {
            "holdout_n": DOC_HOLDOUT_N,
            "holdout_accuracy": DOC_HOLDOUT_ACCURACY,
            "break_even_accuracy": DOC_BREAK_EVEN_ACCURACY,
        },
        "populations": populations,
    }
    JSON_OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    write_markdown(report)

    primary = populations["all_windows"]["metrics"]["holdout"]
    print("Primary all_windows holdout:")
    print(f"  n={primary['n']:,}")
    print(f"  accuracy={primary['accuracy']:.6f}")
    print(f"  binom_p_greater={primary['binom_p_greater']:.6g}")
    print(f"  mean_entry_with_fee={primary['mean_entry_with_fee']:.6f}")
    print(f"  accuracy_minus_break_even={primary['accuracy_minus_break_even']:.6f}")
    print(f"  mean_net_pnl={primary['mean_net_pnl']:.6f}")
    print(f"Saved JSON: {JSON_OUT}")
    print(f"Saved MD: {MD_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
