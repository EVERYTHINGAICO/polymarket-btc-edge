from __future__ import annotations

import argparse, json, sys, urllib.error, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.polymarket_feed import POLYMARKET_BASE_URL


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--duration-minutes', type=float, default=1.0)
    parser.add_argument('--json-out', type=Path, default=ROOT / 'reports/live/t3_time_alignment_result.json')
    args = parser.parse_args()
    result = {'status':'BLOCKED_ENDPOINT_UNCONFIRMED','base_url':POLYMARKET_BASE_URL,'reason':'active window endpoint not confirmed from current implementation'}
    try:
        with urllib.request.urlopen(POLYMARKET_BASE_URL, timeout=10) as resp:
            result['base_http_status'] = getattr(resp, 'status', None)
    except urllib.error.HTTPError as exc:
        result['base_http_status'] = exc.code
    except Exception as exc:
        result['base_error'] = str(exc)
    args.json_out.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
