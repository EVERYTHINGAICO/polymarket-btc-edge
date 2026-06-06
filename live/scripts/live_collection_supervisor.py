from __future__ import annotations

import argparse, json, signal, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STOP = False

def handle_stop(*_args):
    global STOP
    STOP = True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--duration-minutes', type=float, default=15.0)
    parser.add_argument('--json-out', type=Path, default=ROOT / 'reports/live/live_collection_supervisor_result.json')
    args = parser.parse_args()
    signal.signal(signal.SIGINT, handle_stop)
    signal.signal(signal.SIGTERM, handle_stop)
    result = {
        'status': 'PENDING_HUMAN_CONFIRMATION',
        'reason': 'live collection should only start after T1/T3/T4 human review and confirmed stable runtime',
        'suggested_command': 'python3 -m src.logger',
        'duration_minutes_requested': args.duration_minutes,
    }
    args.json_out.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
