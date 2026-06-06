"""Orquestación mínima observable del logger para Fase 4/5/T4/Fase 6 pilot."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from src.db import fetch_observation, insert_open_snapshot, update_close_snapshot
from src.polymarket_feed import ActiveWindowSnapshot
from src.signal import RollingSignalBuffer


@dataclass(frozen=True)
class OpenContext:
    window: ActiveWindowSnapshot
    deribit_index_open: float
    signal_timestamp_ms: int


@dataclass(frozen=True)
class CloseContext:
    window_id: str
    ts_close: str | None
    deribit_index_close: float | None
    chainlink_close: float | None
    pm_up_price_close: float | None


@dataclass(frozen=True)
class RuntimeStatus:
    ok: bool
    is_incomplete: bool = False
    notes: str = ''


class UtcJsonLogger:
    def __init__(self, log_path: str | Path) -> None:
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, event: str, **payload) -> None:
        from datetime import datetime, timezone

        record = {
            'ts_utc': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            'event': event,
            **payload,
        }
        with self.log_path.open('a', encoding='utf-8') as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + '\n')


def _merge_notes(*parts: str) -> str:
    merged: list[str] = []
    for part in parts:
        for item in part.split(','):
            item = item.strip()
            if item and item not in merged:
                merged.append(item)
    return ','.join(merged)


def build_open_snapshot(context: OpenContext, signal_buffer: RollingSignalBuffer, *, min_trades: int = 1, runtime_status: RuntimeStatus = RuntimeStatus(ok=True)) -> dict:
    metrics = signal_buffer.snapshot(context.signal_timestamp_ms)
    total_trades = int(metrics['n_trades_15m'])
    incomplete = 1 if runtime_status.is_incomplete else 0
    low_flow = 1 if total_trades < min_trades else 0
    notes = ','.join(part for part in [runtime_status.notes, 'low_flow' if low_flow else ''] if part)
    return {
        'window_id': context.window.window_id,
        'ts_open': context.window.ts_open,
        'price_to_beat': context.window.price_to_beat,
        'pm_up_price_open': context.window.pm_up_price_open,
        'deribit_index_open': context.deribit_index_open,
        'D_5m_otm_dotm': metrics['D_5m_otm_dotm'],
        'D_10m_otm_dotm': metrics['D_10m_otm_dotm'],
        'D_15m_otm_dotm': metrics['D_15m_otm_dotm'],
        'D_5m_atm': metrics['D_5m_atm'],
        'D_10m_atm': metrics['D_10m_atm'],
        'D_15m_atm': metrics['D_15m_atm'],
        'V_5m_otm_dotm': metrics['V_5m_otm_dotm'],
        'V_10m_otm_dotm': metrics['V_10m_otm_dotm'],
        'V_15m_otm_dotm': metrics['V_15m_otm_dotm'],
        'n_trades_5m': int(metrics['n_trades_5m']),
        'n_trades_10m': int(metrics['n_trades_10m']),
        'n_trades_15m': total_trades,
        'is_incomplete': incomplete,
        'insufficient_flow': low_flow,
        'notes': notes,
    }


def build_close_snapshot(close: CloseContext, *, price_to_beat: float | None, is_incomplete: bool = False, notes: str = '', insufficient_flow: bool = False, outcome_override: str | None = None) -> dict:
    merged_notes = _merge_notes(notes)
    if price_to_beat is None:
        merged_notes = _merge_notes(merged_notes, 'missing_price_to_beat')
    if close.pm_up_price_close is None:
        merged_notes = _merge_notes(merged_notes, 'missing_pm_up_price_close')
    derived_outcome = None
    if price_to_beat is not None and close.chainlink_close is not None:
        derived_outcome = 'Up' if close.chainlink_close >= price_to_beat else 'Down'
    outcome = outcome_override if outcome_override is not None else derived_outcome
    if close.chainlink_close is None:
        merged_notes = _merge_notes(merged_notes, 'chainlink_close_unavailable')
    if outcome is None:
        merged_notes = _merge_notes(merged_notes, 'missing_outcome_authority')
        is_incomplete = True
    return {
        'ts_close': close.ts_close,
        'deribit_index_close': close.deribit_index_close,
        'chainlink_close': close.chainlink_close,
        'outcome': outcome,
        'pm_up_price_close': close.pm_up_price_close,
        'is_incomplete': 1 if is_incomplete else 0,
        'insufficient_flow': 1 if insufficient_flow else 0,
        'notes': merged_notes,
    }


def record_open_window(db_path: str | Path, context: OpenContext, signal_buffer: RollingSignalBuffer, *, min_trades: int = 1, runtime_status: RuntimeStatus = RuntimeStatus(ok=True)) -> dict:
    snapshot = build_open_snapshot(context, signal_buffer, min_trades=min_trades, runtime_status=runtime_status)
    insert_open_snapshot(db_path, snapshot)
    return snapshot


def record_close_window(db_path: str | Path, close: CloseContext, *, price_to_beat: float | None, is_incomplete: bool = False, notes: str = '', insufficient_flow: bool = False, outcome_override: str | None = None) -> dict:
    snapshot = build_close_snapshot(close, price_to_beat=price_to_beat, is_incomplete=is_incomplete, notes=notes, insufficient_flow=insufficient_flow, outcome_override=outcome_override)
    update_close_snapshot(db_path, close.window_id, snapshot)
    return snapshot


def cleanup_incomplete_window(db_path: str | Path, window_id: str, *, notes: str, insufficient_flow: bool = True) -> dict | None:
    row = fetch_observation(db_path, window_id)
    if row is None:
        return None
    if row.get('ts_close') is not None:
        return row
    snapshot = {
        'ts_close': None,
        'deribit_index_close': row.get('deribit_index_close'),
        'chainlink_close': row.get('chainlink_close'),
        'outcome': row.get('outcome'),
        'pm_up_price_close': row.get('pm_up_price_close'),
        'is_incomplete': 1,
        'insufficient_flow': 1 if insufficient_flow else int(row.get('insufficient_flow') or 0),
        'notes': _merge_notes(str(row.get('notes') or ''), notes),
    }
    update_close_snapshot(db_path, window_id, snapshot)
    return fetch_observation(db_path, window_id)


class SupervisedLoggerRuntime:
    def __init__(self, db_path: str | Path, log_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.json_logger = UtcJsonLogger(log_path)

    def open_window(self, context: OpenContext, signal_buffer: RollingSignalBuffer, *, min_trades: int = 1, runtime_status: RuntimeStatus = RuntimeStatus(ok=True)) -> dict:
        snapshot = record_open_window(self.db_path, context, signal_buffer, min_trades=min_trades, runtime_status=runtime_status)
        self.json_logger.emit('window_opened', window_id=context.window.window_id, ts_open=context.window.ts_open, incomplete=bool(snapshot['is_incomplete']), insufficient_flow=bool(snapshot['insufficient_flow']))
        return snapshot

    def close_window(self, close: CloseContext, *, price_to_beat: float | None, is_incomplete: bool = False, notes: str = '', insufficient_flow: bool = False, outcome_override: str | None = None) -> dict:
        snapshot = record_close_window(self.db_path, close, price_to_beat=price_to_beat, is_incomplete=is_incomplete, notes=notes, insufficient_flow=insufficient_flow, outcome_override=outcome_override)
        self.json_logger.emit('window_closed', window_id=close.window_id, ts_close=close.ts_close, incomplete=bool(snapshot['is_incomplete']), insufficient_flow=bool(snapshot['insufficient_flow']), notes=snapshot['notes'])
        return snapshot

    def mark_runtime_error(self, window_id: str, *, ts_close: str | None, price_to_beat: float | None, deribit_index_close: float | None = None, chainlink_close: float | None = None, pm_up_price_close: float | None = None, notes: str = 'runtime_error', insufficient_flow: bool = True) -> dict:
        self.json_logger.emit('runtime_error', window_id=window_id, notes=notes)
        snapshot = self.close_window(
            CloseContext(
                window_id=window_id,
                ts_close=ts_close,
                deribit_index_close=deribit_index_close,
                chainlink_close=chainlink_close,
                pm_up_price_close=pm_up_price_close,
            ),
            price_to_beat=price_to_beat,
            is_incomplete=True,
            notes=notes,
            insufficient_flow=insufficient_flow,
        )
        self.json_logger.emit('reconnect_observed', window_id=window_id, notes='manual verification required')
        return snapshot

    def cleanup_post_open_failure(self, window_id: str, *, notes: str, insufficient_flow: bool = True) -> dict | None:
        self.json_logger.emit('post_open_cleanup', window_id=window_id, notes=notes, insufficient_flow=insufficient_flow)
        return cleanup_incomplete_window(self.db_path, window_id, notes=notes, insufficient_flow=insufficient_flow)

    def read_window(self, window_id: str) -> dict | None:
        return fetch_observation(self.db_path, window_id)


def demo_runtime_once(db_path: str | Path, log_path: str | Path) -> dict:
    from src.signal import SignalTrade

    runtime = SupervisedLoggerRuntime(db_path, log_path)
    buffer = RollingSignalBuffer()
    now_ms = 15 * 60 * 1000
    buffer.add_trade(SignalTrade(now_ms - 60_000, 'buyer', 'call', 'OTM', 10.0, 0.10))
    window = ActiveWindowSnapshot('demo-window', '2026-05-25T20:30:00Z', 65000.0, 0.51)
    open_snapshot = runtime.open_window(OpenContext(window=window, deribit_index_open=65010.0, signal_timestamp_ms=now_ms), buffer, min_trades=5)
    close_snapshot = runtime.mark_runtime_error('demo-window', ts_close='2026-05-25T20:45:00Z', price_to_beat=65000.0, notes='demo_runtime_error', insufficient_flow=True)
    return {'open_snapshot': open_snapshot, 'close_snapshot': close_snapshot, 'row': runtime.read_window('demo-window')}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', default='data/observations.db')
    parser.add_argument('--log-path', default='reports/live/logger_runtime.log')
    parser.add_argument('--demo-once', action='store_true')
    parser.add_argument('--one-window-pilot', action='store_true')
    parser.add_argument('--continuous', action='store_true', help='Run persistent continuous logger (Fase 6 modo continuo).')
    parser.add_argument('--with-trajectory', action='store_true', help='Sample pm_up_price during the window (opt-in, Fase 6.b)')
    parser.add_argument('--trajectory-interval-seconds', type=int, default=30)
    args = parser.parse_args()
    if args.continuous:
        from src.continuous_logger import ContinuousLogger
        cl = ContinuousLogger(
            Path(args.db), Path(args.log_path),
            interval_seconds=args.trajectory_interval_seconds,
            with_trajectory=args.with_trajectory,
        )
        try:
            cl.start()
        except KeyboardInterrupt:
            cl.stop()
        return 0
    if args.one_window_pilot:
        from scripts.one_window_pilot import run_one_window_pilot
        result = run_one_window_pilot(
            Path(args.db), Path(args.log_path),
            with_trajectory=args.with_trajectory,
            interval_seconds=args.trajectory_interval_seconds,
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result.get('status') in {'PASS', 'READY_FOR_NEXT_WINDOW'} else 1
    if not args.demo_once:
        print('Logger runtime scaffold is available. Use --demo-once for a bounded observable dry run or --one-window-pilot for a real pilot.')
        return 0
    result = demo_runtime_once(args.db, args.log_path)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
