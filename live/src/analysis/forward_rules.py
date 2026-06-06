"""Evaluacion forward de reglas congeladas BTC live proxy.

Este modulo no optimiza parametros. Solo evalua las reglas declaradas en
forward_rules_config.json sobre ventanas posteriores al corte congelado.
"""

from __future__ import annotations

import bisect
import json
import random
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any


BOOTSTRAP_SEED = 20260603
BOOTSTRAP_N = 5000


@dataclass(frozen=True)
class ForwardRule:
    rule_id: str
    lookback_min: int
    gap_min: int
    threshold: float
    entry_t: int | str


def parse_iso_z_to_ms(value: str) -> int:
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    return int(datetime.fromisoformat(text).timestamp() * 1000)


def iso_date(value: str) -> str:
    return value[:10]


def iso_hour_utc(value: str) -> int:
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    return int(datetime.fromisoformat(text).astimezone(timezone.utc).hour)


def mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def percentile(sorted_values: list[float], q: float) -> float | None:
    if not sorted_values:
        return None
    pos = (len(sorted_values) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(sorted_values) - 1)
    if lo == hi:
        return sorted_values[lo]
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (pos - lo)


def bootstrap_mean(values: list[float], *, seed: int, n_bootstrap: int = BOOTSTRAP_N) -> dict[str, float] | None:
    if not values:
        return None
    rng = random.Random(seed)
    n = len(values)
    boot_means: list[float] = []
    for _ in range(n_bootstrap):
        boot_means.append(sum(values[rng.randrange(n)] for _ in range(n)) / n)
    boot_means.sort()
    return {
        "ci95_low": float(percentile(boot_means, 0.025)),
        "ci95_high": float(percentile(boot_means, 0.975)),
        "p_boot_mean_le_0": sum(1 for item in boot_means if item <= 0.0) / len(boot_means),
    }


def load_config(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_rules(config: dict[str, Any]) -> list[ForwardRule]:
    return [
        ForwardRule(
            rule_id=str(item["id"]),
            lookback_min=int(item["lookback_min"]),
            gap_min=int(item["gap_min"]),
            threshold=float(item["threshold"]),
            entry_t=item["entry_t"],
        )
        for item in config["rules"]
    ]


def _open_connection_readonly(db_path: Path) -> sqlite3.Connection:
    uri = "file:" + db_path.as_posix() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def load_forward_inputs(db_path: str | Path, config: dict[str, Any]) -> dict[str, Any]:
    db = Path(db_path)
    data_cfg = config["data"]
    outcome_in = tuple(data_cfg.get("filter_outcome_in", ["Up", "Down"]))
    start_after = str(data_cfg["forward_start_after_ts_open_utc"])
    is_incomplete = int(data_cfg.get("filter_is_incomplete", 0))
    exclude_window_id = str(data_cfg.get("exclude_window_id", "demo-window"))
    conn = _open_connection_readonly(db)
    try:
        observations = [
            dict(row)
            for row in conn.execute(
                """
                SELECT window_id, ts_open, outcome, pm_up_price_open
                FROM observations
                WHERE outcome IN ({})
                  AND is_incomplete = ?
                  AND window_id != ?
                  AND datetime(ts_open) > datetime(?)
                ORDER BY ts_open, window_id
                """.format(",".join("?" for _ in outcome_in)),
                (*outcome_in, is_incomplete, exclude_window_id, start_after),
            ).fetchall()
        ]
        intrawindow = [
            dict(row)
            for row in conn.execute(
                """
                SELECT window_id, t_seconds, pm_up_price
                FROM observations_intrawindow
                WHERE pm_up_price IS NOT NULL
                ORDER BY window_id, t_seconds
                """
            ).fetchall()
        ]
        deribit_rows = [
            dict(row)
            for row in conn.execute(
                """
                SELECT timestamp_ms, index_price
                FROM deribit_trades_raw
                WHERE index_price IS NOT NULL
                ORDER BY timestamp_ms
                """
            ).fetchall()
        ]
    finally:
        conn.close()
    intrawindow_by_window: dict[str, list[tuple[int, float]]] = {}
    for row in intrawindow:
        intrawindow_by_window.setdefault(str(row["window_id"]), []).append(
            (int(row["t_seconds"]), float(row["pm_up_price"]))
        )
    return {
        "observations": observations,
        "intrawindow_by_window": intrawindow_by_window,
        "deribit_times": [int(row["timestamp_ms"]) for row in deribit_rows],
        "deribit_prices": [float(row["index_price"]) for row in deribit_rows],
    }


def _last_deribit_at_or_before(times: list[int], prices: list[float], target_ms: int) -> tuple[float, float] | None:
    idx = bisect.bisect_right(times, target_ms) - 1
    if idx < 0:
        return None
    timestamp_ms = times[idx]
    return prices[idx], (target_ms - timestamp_ms) / 1000.0


def _entry_price(row: dict[str, Any], intrawindow_by_window: dict[str, list[tuple[int, float]]], entry_t: int | str, side: str, entry_window_seconds: int) -> tuple[float, float] | None:
    if entry_t == "open":
        up_price = row.get("pm_up_price_open")
        if up_price is None:
            return None
        return (float(up_price) if side == "Up" else 1.0 - float(up_price)), 0.0
    target = int(entry_t)
    candidates = [
        (abs(t_seconds - target), t_seconds, price)
        for t_seconds, price in intrawindow_by_window.get(str(row["window_id"]), [])
        if target <= t_seconds <= target + entry_window_seconds
    ]
    if not candidates:
        return None
    _, actual_t, up_price = min(candidates)
    return (up_price if side == "Up" else 1.0 - up_price), float(actual_t - target)


def evaluate_rule(inputs: dict[str, Any], config: dict[str, Any], rule: ForwardRule, *, seed_offset: int = 0) -> dict[str, Any]:
    data_cfg = config["data"]
    max_staleness = float(data_cfg["max_deribit_staleness_seconds"])
    entry_window_seconds = int(data_cfg["entry_window_seconds"])
    observations = inputs["observations"]
    times = inputs["deribit_times"]
    prices = inputs["deribit_prices"]
    intrawindow_by_window = inputs["intrawindow_by_window"]
    pnls: list[float] = []
    wins: list[float] = []
    entries: list[float] = []
    fees: list[float] = []
    signal_staleness: list[float] = []
    lag_staleness: list[float] = []
    entry_delay: list[float] = []
    by_day: dict[str, list[float]] = {}
    by_hour: dict[str, list[float]] = {}
    eligible_momentum = 0
    no_signal = 0
    missing_entry = 0
    for row in observations:
        open_ms = parse_iso_z_to_ms(str(row["ts_open"]))
        signal = _last_deribit_at_or_before(times, prices, open_ms - rule.gap_min * 60_000)
        lag = _last_deribit_at_or_before(times, prices, open_ms - (rule.gap_min + rule.lookback_min) * 60_000)
        if signal is None or lag is None:
            continue
        signal_price, signal_stale = signal
        lag_price, lag_stale = lag
        if signal_stale > max_staleness or lag_stale > max_staleness:
            continue
        eligible_momentum += 1
        momentum = signal_price / lag_price - 1.0
        if momentum > rule.threshold:
            side = "Up"
        elif momentum < -rule.threshold:
            side = "Down"
        else:
            no_signal += 1
            continue
        entry = _entry_price(row, intrawindow_by_window, rule.entry_t, side, entry_window_seconds)
        if entry is None:
            missing_entry += 1
            continue
        entry_value, delay = entry
        win = 1.0 if side == row["outcome"] else 0.0
        fee = 0.07 * entry_value * (1.0 - entry_value)
        pnl = win - entry_value - fee
        pnls.append(pnl)
        wins.append(win)
        entries.append(entry_value)
        fees.append(fee)
        signal_staleness.append(signal_stale)
        lag_staleness.append(lag_stale)
        entry_delay.append(delay)
        by_day.setdefault(iso_date(str(row["ts_open"])), []).append(pnl)
        by_hour.setdefault(str(iso_hour_utc(str(row["ts_open"]))), []).append(pnl)
    boot = bootstrap_mean(pnls, seed=BOOTSTRAP_SEED + seed_offset)
    return {
        "rule_id": rule.rule_id,
        "lookback_min": rule.lookback_min,
        "gap_min": rule.gap_min,
        "threshold": rule.threshold,
        "entry_t": rule.entry_t,
        "n": len(pnls),
        "coverage": len(pnls) / len(observations) if observations else None,
        "forward_windows_available": len(observations),
        "eligible_momentum_windows": eligible_momentum,
        "no_signal_windows": no_signal,
        "missing_entry_after_signal": missing_entry,
        "accuracy": mean(wins),
        "mean_entry": mean(entries),
        "mean_fee": mean(fees),
        "mean_net_pnl": mean(pnls),
        "median_net_pnl": median(pnls) if pnls else None,
        "ci95_bootstrap": None if boot is None else [boot["ci95_low"], boot["ci95_high"]],
        "p_boot": None if boot is None else boot["p_boot_mean_le_0"],
        "avg_signal_staleness_s": mean(signal_staleness),
        "avg_lag_staleness_s": mean(lag_staleness),
        "avg_entry_delay_s": mean(entry_delay),
        "by_day": {
            key: {"n": len(values), "mean_net_pnl": mean(values)}
            for key, values in sorted(by_day.items())
        },
        "by_hour_utc": {
            key: {"n": len(values), "mean_net_pnl": mean(values)}
            for key, values in sorted(by_hour.items(), key=lambda item: int(item[0]))
        },
    }


def evaluate_forward_rules(db_path: str | Path, config: dict[str, Any]) -> dict[str, Any]:
    inputs = load_forward_inputs(db_path, config)
    rules = load_rules(config)
    results = [evaluate_rule(inputs, config, rule, seed_offset=index) for index, rule in enumerate(rules, start=1)]
    observations = inputs["observations"]
    if observations:
        min_ts_open = min(str(row["ts_open"]) for row in observations)
        max_ts_open = max(str(row["ts_open"]) for row in observations)
        elapsed_days = (parse_iso_z_to_ms(max_ts_open) - parse_iso_z_to_ms(min_ts_open)) / 86_400_000
    else:
        min_ts_open = max_ts_open = None
        elapsed_days = 0.0
    min_n = int(config["data"]["min_n_for_report"])
    min_days = float(config["data"]["additional_days_for_report"])
    ready_by_n = any(result["n"] >= min_n for result in results)
    ready_by_days = elapsed_days >= min_days
    return {
        "analysis_type": "BTC_FORWARD_FROZEN_RULES_ONLY",
        "config_version": config["config_version"],
        "frozen_at_utc": config["frozen_at_utc"],
        "forward_start_after_ts_open_utc": config["data"]["forward_start_after_ts_open_utc"],
        "verdict_ceiling_without_orderbook": config["verdict_ceiling_without_orderbook"],
        "forward_windows_available": len(observations),
        "min_ts_open": min_ts_open,
        "max_ts_open": max_ts_open,
        "elapsed_forward_days": elapsed_days,
        "ready_for_formal_report": bool(ready_by_n or ready_by_days),
        "ready_reason": "n>=1000" if ready_by_n else ("additional_days>=7" if ready_by_days else "WAIT_FOR_MORE_FORWARD_DATA"),
        "rules": results,
    }
