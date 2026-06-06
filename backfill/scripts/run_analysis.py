"""CLI determinista para correr los 4 gates de PROJECT_DESIGN seccion 7.B.

Uso:
    py scripts/run_analysis.py
    py scripts/run_analysis.py --output reports/phases/analysis_<ts>.json
    py scripts/run_analysis.py --db data/observations.db --config analysis_config.json

Garantia: mismo DB + mismo config = mismo output_hash. Reproducibilidad bit-exact.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.analysis.config import load_config
from src.analysis.data import load_data
from src.analysis.exploratory import (
    analyze_chainlink_vs_polymarket_flips,
    analyze_d_brackets,
    analyze_d_variants_accuracy,
    analyze_pm_open_brackets,
    analyze_running_accuracy,
)
from src.analysis.gates import (
    gate1_d_vs_coin,
    gate2_d_vs_market,
    gate3_lead_lag,
    gate4a_chainlink_deribit,
    gate4b_costs,
    kfold_accuracy,
)
from src.analysis.stats import bonferroni_alpha, deterministic_train_holdout_split
from src.analysis.verdict import consolidate


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def main() -> int:
    parser = argparse.ArgumentParser(description='Analisis determinista (PROJECT_DESIGN 7.B).')
    parser.add_argument('--config', default='analysis_config.json')
    parser.add_argument('--db', default=None, help='Override path to SQLite DB.')
    parser.add_argument('--output', default=None, help='Write JSON output to this path.')
    args = parser.parse_args()

    config = load_config(args.config)
    data = load_data(config, db_path_override=args.db)

    min_n = int(config.get('data', 'min_n_for_verdict'))
    alpha = float(config.get('gate1', 'alpha'))
    n_tests = int(config.get('bonferroni', 'n_tests_total'))
    alpha_corrected = bonferroni_alpha(alpha, n_tests)

    train, holdout = deterministic_train_holdout_split(
        data.observations,
        ratio=float(config.get('split', 'train_holdout_ratio')),
        seed=int(config.get('split', 'random_seed')),
    )

    # Gates corren sobre HOLDOUT (no train) para evitar overfit
    gate_results = [
        gate1_d_vs_coin(holdout, config, alpha_corrected, min_n),
        gate2_d_vs_market(holdout, config, alpha_corrected, min_n),
        gate3_lead_lag(holdout, data.trajectory, config, min_n),
        gate4a_chainlink_deribit(holdout, config, min_n),
        gate4b_costs(holdout, config, alpha_corrected, min_n),
    ]

    kfold_train = kfold_accuracy(
        train,
        d_variant=config.get('gate1', 'D_variant'),
        d_threshold=float(config.get('gate1', 'D_threshold_abs')),
        n_splits=int(config.get('split', 'kfold_n_splits')),
        seed=int(config.get('split', 'random_seed')),
    )

    # EXPLORATORIO: NO afecta veredicto de gates oficiales (pre-registro v1.0.0 intacto)
    flip_analysis = analyze_chainlink_vs_polymarket_flips(data.observations)
    d_variants_analysis = analyze_d_variants_accuracy(data.observations)
    d_brackets_analysis = analyze_d_brackets(data.observations)
    pm_open_brackets_analysis = analyze_pm_open_brackets(data.observations)
    running_accuracy_analysis = analyze_running_accuracy(data.observations)

    summary = consolidate(
        gate_results=gate_results,
        config_version=config.config_version,
        input_hash=data.input_hash,
        n_total_complete=data.n_total_complete,
        n_after_filter=data.n_after_filter,
        min_n_for_verdict=min_n,
        extra={
            'run_at_utc': utc_now(),
            'n_train': len(train),
            'n_holdout': len(holdout),
            'kfold_train_accuracy': kfold_train,
            'bonferroni': {
                'alpha_uncorrected': alpha,
                'n_tests': n_tests,
                'alpha_corrected': alpha_corrected,
            },
            'pre_registration': {
                'config_version': config.config_version,
                'frozen_at_utc': config.frozen_at_utc,
            },
            'exploratory': {
                '_doc': 'Sub-analisis NO parte del pre-registro. No afectan veredicto de gates oficiales.',
                'chainlink_vs_polymarket_flips': flip_analysis,
                'd_variants_accuracy': d_variants_analysis,
                'd_brackets_accuracy': d_brackets_analysis,
                'pm_up_open_brackets': pm_open_brackets_analysis,
                'running_accuracy': running_accuracy_analysis,
            },
        },
    )

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding='utf-8')

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
