"""Continuous collection loop for Fase 6.

Calls one_window_pilot in a loop. After each window finishes (capture + resolve),
discovers the next active window and starts again. Continues until target count
reached or stopped by user (Ctrl+C).

Read-only on external APIs. Writes to data/observations.db only via the logger.
"""

from __future__ import annotations

import argparse
import json
import signal
import sqlite3
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.one_window_pilot import run_one_window_pilot

DEFAULT_DB = ROOT / 'data' / 'observations.db'
DEFAULT_LOG = ROOT / 'reports' / 'live' / 'continuous_collection.log'
DEFAULT_STATUS = ROOT / 'reports' / 'live' / 'continuous_collection_status.json'

_stop_requested = False


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def handle_sigint(signum, frame):
    global _stop_requested
    _stop_requested = True
    print(f'\n[{utc_now_iso()}] Stop requested; finishing current window then exiting.', flush=True)


def count_real_windows(db_path: Path) -> int:
    if not db_path.exists():
        return 0
    con = sqlite3.connect(db_path)
    try:
        return con.execute(
            "SELECT COUNT(*) FROM observations "
            "WHERE window_id != 'demo-window' AND is_incomplete = 0"
        ).fetchone()[0]
    finally:
        con.close()


def append_log(log_path: Path, payload: dict) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open('a', encoding='utf-8') as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + '\n')


def write_status(status_path: Path, payload: dict) -> None:
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')


def main() -> int:
    parser = argparse.ArgumentParser(description='Continuous Fase 6 collection loop.')
    parser.add_argument('--target-windows', type=int, default=1000,
                        help='Stop after this many complete (is_incomplete=0) windows. Default 1000.')
    parser.add_argument('--db', default=str(DEFAULT_DB))
    parser.add_argument('--log-path', default=str(ROOT / 'reports' / 'live' / 'logger_runtime.log'))
    parser.add_argument('--cycle-log', default=str(DEFAULT_LOG))
    parser.add_argument('--status-path', default=str(DEFAULT_STATUS))
    parser.add_argument('--with-trajectory', action='store_true', default=True,
                        help='Capture intra-window trajectory. Default true for Fase 6.b.')
    parser.add_argument('--no-trajectory', dest='with_trajectory', action='store_false',
                        help='Disable trajectory sampling.')
    parser.add_argument('--trajectory-interval-seconds', type=int, default=30)
    parser.add_argument('--max-consecutive-failures', type=int, default=5,
                        help='Halt if this many windows fail in a row.')
    args = parser.parse_args()

    db_path = Path(args.db)
    log_path = Path(args.log_path)
    cycle_log = Path(args.cycle_log)
    status_path = Path(args.status_path)

    signal.signal(signal.SIGINT, handle_sigint)
    try:
        signal.signal(signal.SIGTERM, handle_sigint)
    except (AttributeError, ValueError):
        pass

    started_at = utc_now_iso()
    consecutive_failures = 0
    iterations = 0

    while not _stop_requested:
        complete_count = count_real_windows(db_path)
        if complete_count >= args.target_windows:
            print(f'[{utc_now_iso()}] Target reached: {complete_count}/{args.target_windows} complete windows.', flush=True)
            break

        iterations += 1
        iteration_started_at = utc_now_iso()
        print(f'[{iteration_started_at}] Iteration {iterations} starting (complete so far: {complete_count}/{args.target_windows}).', flush=True)
        write_status(status_path, {
            'started_at_utc': started_at,
            'iteration_started_at_utc': iteration_started_at,
            'iteration': iterations,
            'complete_windows': complete_count,
            'target_windows': args.target_windows,
            'consecutive_failures': consecutive_failures,
            'state': 'RUNNING',
        })

        result_entry: dict = {
            'iteration': iterations,
            'iteration_started_at_utc': iteration_started_at,
        }

        try:
            result = run_one_window_pilot(
                db_path,
                log_path,
                with_trajectory=args.with_trajectory,
                interval_seconds=args.trajectory_interval_seconds,
            )
            result_entry['status'] = result.get('status')
            result_entry['row_kind'] = result.get('row_kind')
            result_entry['window_id'] = result.get('selected_window_id')
            result_entry['trajectory_samples'] = result.get('trajectory_samples')
            result_entry['finished_at_utc'] = result.get('finished_at_utc')
            if result.get('status') == 'PASS':
                consecutive_failures = 0
            else:
                consecutive_failures += 1
        except KeyboardInterrupt:
            result_entry['status'] = 'INTERRUPTED'
            append_log(cycle_log, result_entry)
            break
        except Exception as exc:
            result_entry['status'] = 'EXCEPTION'
            result_entry['error'] = repr(exc)
            result_entry['traceback'] = traceback.format_exc()
            consecutive_failures += 1

        result_entry['ended_at_utc'] = utc_now_iso()
        append_log(cycle_log, result_entry)
        print(f'[{result_entry["ended_at_utc"]}] Iteration {iterations} ended: status={result_entry.get("status")} consecutive_failures={consecutive_failures}', flush=True)

        if consecutive_failures >= args.max_consecutive_failures:
            print(f'[{utc_now_iso()}] HALTING: {consecutive_failures} consecutive failures.', flush=True)
            write_status(status_path, {
                'started_at_utc': started_at,
                'iteration': iterations,
                'complete_windows': count_real_windows(db_path),
                'target_windows': args.target_windows,
                'consecutive_failures': consecutive_failures,
                'state': 'HALTED_CONSECUTIVE_FAILURES',
            })
            return 1

    final_count = count_real_windows(db_path)
    final_state = 'STOPPED_BY_USER' if _stop_requested else 'TARGET_REACHED'
    write_status(status_path, {
        'started_at_utc': started_at,
        'ended_at_utc': utc_now_iso(),
        'iteration': iterations,
        'complete_windows': final_count,
        'target_windows': args.target_windows,
        'consecutive_failures': consecutive_failures,
        'state': final_state,
    })
    print(f'[{utc_now_iso()}] Final state: {final_state} ({final_count}/{args.target_windows}).', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
