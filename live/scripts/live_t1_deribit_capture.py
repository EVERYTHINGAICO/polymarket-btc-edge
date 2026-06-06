from __future__ import annotations

import argparse
import json
import signal
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.deribit_feed import collect_live_deribit_trades

STOP = False


def handle_stop(*_args):
    global STOP
    STOP = True


def finalize_result(duration_minutes: float, started: float, capture, log_path: Path) -> dict:
    elapsed = time.time() - started
    counts = Counter(capture.counts)
    raw = counts['raw_trades']
    skipped_pct = (counts['skipped_trades'] / raw * 100.0) if raw else 0.0
    status = 'PASS' if raw and skipped_pct <= 2.0 else ('FAIL' if raw else 'BLOCKED_NO_TRADES')
    sample_lines = [
        f"trade_id={trade.trade_id or '-'} instrument={trade.instrument_name} direction={trade.direction} type={trade.option_type} moneyness={trade.moneyness} delta_abs={trade.delta_abs:.6f} amount={trade.amount:.6f} price={trade.price:.6f}"
        for trade in capture.trades[:50]
    ]
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open('a', encoding='utf-8') as handle:
        for line in sample_lines:
            handle.write(json.dumps({'event': 'trade', 'line': line, 'ts': time.time()}) + '\n')
    return {
        'status': status,
        'transport': 'canonical_live_capture',
        'duration_minutes_requested': duration_minutes,
        'duration_seconds_actual': round(elapsed, 2),
        'raw_trades': raw,
        'classified_trades': counts['classified_trades'],
        'skipped_trades': counts['skipped_trades'],
        'skip_percent': round(skipped_pct, 4),
        'skip_reasons': {},
        'timeouts': counts['timeouts'],
        'reconnects': counts['reconnects'],
        'errors': counts['errors'],
        'messages': counts['messages'],
        'delta_from_trade': counts['delta_from_trade'],
        'delta_from_ticker': counts['delta_from_ticker'],
        'delta_missing_after_enrichment': counts['delta_missing_after_enrichment'],
        'ticker_fetch_errors': counts['ticker_fetch_errors'],
        'heartbeats_received': counts['heartbeats_received'],
        'test_requests_received': counts['test_requests_received'],
        'test_responses_sent': counts['test_responses_sent'],
        'heartbeat_enabled': capture.heartbeat_enabled,
        'close_codes': capture.close_codes,
        'close_reasons': capture.close_reasons,
        'time_observed_seconds': round(elapsed, 2),
        'log_path': str(log_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--duration-minutes', type=float, default=60.0)
    parser.add_argument('--log-path', type=Path, default=ROOT / 'reports/live/t1_deribit_capture.log')
    parser.add_argument('--json-out', type=Path, default=ROOT / 'reports/live/t1_deribit_capture_result.json')
    args = parser.parse_args()
    signal.signal(signal.SIGINT, handle_stop)
    signal.signal(signal.SIGTERM, handle_stop)
    started = time.time()
    capture = collect_live_deribit_trades(duration_seconds=args.duration_minutes * 60.0)
    result = finalize_result(args.duration_minutes, started, capture, args.log_path)
    args.json_out.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
    return 0 if result['status'] in {'PASS', 'BLOCKED', 'BLOCKED_NO_TRADES'} else 1


if __name__ == '__main__':
    raise SystemExit(main())
