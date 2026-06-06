from __future__ import annotations

import argparse, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--duration-minutes', type=float, default=1.0)
    parser.add_argument('--json-out', type=Path, default=ROOT / 'reports/live/t4_resilience_check_result.json')
    args = parser.parse_args()
    result = {
        'status': 'PENDING_MANUAL_NETWORK_CUT',
        'reason': 'real network interruption cannot be safely forced from this runtime without external control',
        'manual_procedure': 'Cut network mid-window during supervised live logger run and verify is_incomplete/insufficient_flow markers.',
    }
    args.json_out.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
