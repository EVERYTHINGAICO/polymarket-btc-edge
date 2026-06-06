"""Consolidacion de gates + hash SHA256 del output completo.

Mismo input + mismo config = mismo output_hash bit-exact.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from typing import Any

from src.analysis.gates import GateResult

PROJECT_VERDICT_AVANZA = 'EDGE_VALIDATED'
PROJECT_VERDICT_FIN = 'NO_EDGE_FIN'
PROJECT_VERDICT_INSUFICIENTE = 'WAIT_FOR_MORE_DATA'


def consolidate(
    gate_results: list[GateResult],
    config_version: str,
    input_hash: str,
    n_total_complete: int,
    n_after_filter: int,
    min_n_for_verdict: int,
    extra: dict | None = None,
) -> dict:
    """Combina los gates en un resultado global con hash output."""
    verdicts = [g.verdict for g in gate_results]
    if 'INSUFICIENTE' in verdicts and n_after_filter < min_n_for_verdict:
        project_verdict = PROJECT_VERDICT_INSUFICIENTE
    elif all(v == 'AVANZA' for v in verdicts):
        project_verdict = PROJECT_VERDICT_AVANZA
    elif 'FIN' in verdicts:
        project_verdict = PROJECT_VERDICT_FIN
    else:
        project_verdict = PROJECT_VERDICT_INSUFICIENTE

    deterministic_core = {
        'config_version': config_version,
        'input_hash': input_hash,
        'n_total_complete': n_total_complete,
        'n_after_filter': n_after_filter,
        'min_n_for_verdict': min_n_for_verdict,
        'project_verdict': project_verdict,
        'gates': [asdict(g) for g in gate_results],
    }
    if extra:
        deterministic_extra = {k: v for k, v in extra.items() if k != 'run_at_utc'}
        deterministic_core['extra'] = deterministic_extra
    serialized = json.dumps(deterministic_core, sort_keys=True, ensure_ascii=False, default=str).encode('utf-8')
    output_hash = hashlib.sha256(serialized).hexdigest()

    summary = dict(deterministic_core)
    if extra:
        summary['extra'] = extra  # restaurar full extra con run_at_utc
    summary['output_hash'] = output_hash
    return summary
