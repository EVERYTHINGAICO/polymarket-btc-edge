"""Cálculo puro de señales D/V para Fase 2."""

from __future__ import annotations

import threading
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Deque

WINDOW_MINUTES = (5, 10, 15)
WINDOW_SECONDS = tuple(minutes * 60 for minutes in WINDOW_MINUTES)


@dataclass(frozen=True)
class SignalTrade:
    timestamp_ms: int
    direction: str
    option_type: str
    moneyness: str
    amount: float
    delta_abs: float

    @property
    def signed_pressure(self) -> float:
        sign = 1.0 if self.direction == "buyer" else -1.0
        return sign * self.amount * self.delta_abs


class RollingSignalBuffer:
    def __init__(self) -> None:
        self._trades: Deque[SignalTrade] = deque()
        self._lock = threading.Lock()

    def add_trade(self, trade: SignalTrade) -> None:
        with self._lock:
            self._trades.append(trade)

    def prune(self, current_timestamp_ms: int, window_seconds: int = 15 * 60) -> None:
        cutoff_ms = current_timestamp_ms - (window_seconds * 1000)
        with self._lock:
            while self._trades and self._trades[0].timestamp_ms < cutoff_ms:
                self._trades.popleft()

    def trades_in_window(self, current_timestamp_ms: int, window_seconds: int) -> list[SignalTrade]:
        cutoff_ms = current_timestamp_ms - (window_seconds * 1000)
        with self._lock:
            return [trade for trade in self._trades if trade.timestamp_ms >= cutoff_ms]

    def snapshot(self, current_timestamp_ms: int) -> dict[str, float]:
        metrics: dict[str, float] = {}
        for minutes, window_seconds in zip(WINDOW_MINUTES, WINDOW_SECONDS, strict=True):
            summary = compute_signal_metrics(self.trades_in_window(current_timestamp_ms, window_seconds))
            metrics.update(flatten_metrics(summary, minutes))
        return metrics


def bucket_for_trade(trade: SignalTrade) -> str | None:
    if trade.moneyness in {"DOTM", "OTM"}:
        return "otm_dotm"
    if trade.moneyness == "ATM":
        return "atm"
    return None


def aggregate_window(trades: list[SignalTrade]) -> dict[str, dict[str, float]]:
    aggregates: dict[str, dict[str, float]] = defaultdict(lambda: {"A_C": 0.0, "A_P": 0.0, "n_trades": 0.0})
    for trade in trades:
        bucket = bucket_for_trade(trade)
        if bucket is None:
            continue
        key = "A_C" if trade.option_type == "call" else "A_P"
        aggregates[bucket][key] += trade.signed_pressure
        aggregates[bucket]["n_trades"] += 1
    return dict(aggregates)


def compute_signal_metrics(trades: list[SignalTrade]) -> dict[str, dict[str, float]]:
    aggregates = aggregate_window(trades)
    metrics: dict[str, dict[str, float]] = {}
    for bucket in ("otm_dotm", "atm"):
        aggregate = aggregates.get(bucket, {"A_C": 0.0, "A_P": 0.0, "n_trades": 0.0})
        a_c = aggregate["A_C"]
        a_p = aggregate["A_P"]
        metrics[bucket] = {
            "A_C": a_c,
            "A_P": a_p,
            "D": (a_c - a_p) / 2.0,
            "V": (a_c + a_p) / 2.0,
            "n_trades": aggregate["n_trades"],
        }
    return metrics


def flatten_metrics(metrics: dict[str, dict[str, float]], window_minutes: int) -> dict[str, float]:
    flat: dict[str, float] = {
        f'n_trades_{window_minutes}m': metrics['otm_dotm']['n_trades'] + metrics['atm']['n_trades']
    }
    for bucket in ('otm_dotm', 'atm'):
        suffix = 'otm_dotm' if bucket == 'otm_dotm' else 'atm'
        flat[f'D_{window_minutes}m_{suffix}'] = metrics[bucket]['D']
        if bucket == 'otm_dotm':
            flat[f'V_{window_minutes}m_{suffix}'] = metrics[bucket]['V']
    return flat
