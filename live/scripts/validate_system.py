from __future__ import annotations

import json
from pathlib import Path

TEST_PLAN = {
    'T1': {'status': 'PENDING_HUMAN_RUN', 'summary': 'Run Deribit feed for ~1 hour and compare captured counts against public volume sanity check.'},
    'T2': {'status': 'PASS_LOCAL', 'summary': 'Synthetic signal correctness and expiration covered by unit tests.'},
    'T3': {'status': 'PENDING_HUMAN_RUN', 'summary': 'Verify live UTC timestamps align with real Polymarket window openings.'},
    'T4': {'status': 'PENDING_HUMAN_RUN', 'summary': 'Manually interrupt network and verify incomplete/low-flow marking path.'},
    'T5': {'status': 'PASS_LOCAL', 'summary': 'SQLite persistence and restart-safe writes covered by db/logger tests.'},
}

if __name__ == '__main__':
    out = Path('reports/phases/fase_5v_validation_status.json')
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        try:
            current = json.loads(out.read_text(encoding='utf-8'))
            TEST_PLAN.update(current)
        except Exception:
            pass
    out.write_text(json.dumps(TEST_PLAN, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(TEST_PLAN, indent=2))
