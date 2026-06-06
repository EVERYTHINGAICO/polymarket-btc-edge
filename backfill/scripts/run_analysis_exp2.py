"""EXP2-8 — Análisis confirmatorio Exp2 (orquestador).

Corre los 5 gates de Exp1 (clonados, intactos) sobre el HOLDOUT del split TEMPORAL
(veredicto oficial v2.0.0). Adicionalmente:
  - split ALEATORIO (Exp1) como comparación secundaria.
  - block bootstrap en Gate 1/2 como robustez informativa (NO decide veredicto).

Determinista: mismo DB + mismo config = mismo output_hash.
Corrida confirmatoria: se corre UNA vez sobre el holdout. NO re-tunear.

Uso:
    py scripts/run_analysis_exp2.py --split temporal   # oficial
    py scripts/run_analysis_exp2.py --split random     # comparativo Exp1
    py scripts/run_analysis_exp2.py --on train         # validar pipeline SIN tocar holdout
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np

from src.analysis.config import load_config
from src.analysis.data import load_data
from src.analysis.gates import (
    gate1_d_vs_coin, gate2_d_vs_market, gate3_lead_lag,
    gate4a_chainlink_deribit, gate4b_costs, kfold_accuracy,
)
from src.analysis.stats import (
    bonferroni_alpha, block_bootstrap_pvalue,
    deterministic_train_holdout_split, temporal_train_holdout_split,
)
from src.analysis.verdict import consolidate


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def hits_series(df, d_var, d_thr):
    sub = df[df[d_var].abs() > d_thr].sort_values("ts_open", kind="stable")
    if len(sub) == 0:
        return np.array([])
    pred = np.where(sub[d_var] > 0, "Up", "Down")
    return (pred == sub["outcome"].values).astype(int)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="analysis_config.json")
    ap.add_argument("--db", default="data/observations_exp2.db")
    ap.add_argument("--split", choices=["temporal", "random"], default="temporal")
    ap.add_argument("--on", choices=["holdout", "train", "full"], default="holdout",
                    help="full=dataset completo (veredicto PRINCIPAL, como Exp1). holdout=validacion secundaria. train=pipeline.")
    ap.add_argument("--output", default=None)
    args = ap.parse_args()

    config = load_config(args.config)
    data = load_data(config, db_path_override=args.db)

    min_n = int(config.get("data", "min_n_for_verdict"))
    alpha = float(config.get("gate1", "alpha"))
    n_tests = int(config.get("bonferroni", "n_tests_total"))
    alpha_corr = bonferroni_alpha(alpha, n_tests)
    ratio = float(config.get("split", "train_holdout_ratio"))

    if args.split == "temporal":
        train, holdout = temporal_train_holdout_split(data.observations, ratio, time_col="ts_open")
    else:
        train, holdout = deterministic_train_holdout_split(data.observations, ratio,
                                                           int(config.get("split", "random_seed")))

    if args.on == "full":
        target = data.observations
    elif args.on == "holdout":
        target = holdout
    else:
        target = train
    label = f"{args.split}/{args.on}"
    print(f"=== Corrida: split={args.split} | conjunto={args.on} | n={len(target)} ===")

    gates = [
        gate1_d_vs_coin(target, config, alpha_corr, min_n),
        gate2_d_vs_market(target, config, alpha_corr, min_n),
        gate3_lead_lag(target, data.trajectory, config, min_n),
        gate4a_chainlink_deribit(target, config, min_n),
        gate4b_costs(target, config, alpha_corr, min_n),
    ]

    # k-fold CV sobre el target (robustez, como Exp1)
    kfold = kfold_accuracy(target, d_variant=config.get("gate1", "D_variant"),
                           d_threshold=float(config.get("gate1", "D_threshold_abs")),
                           n_splits=int(config.get("split", "kfold_n_splits")),
                           seed=int(config.get("split", "random_seed")))

    # robustez: block bootstrap en Gate 1 (informativo, no decisorio)
    bb = config.raw.get("robustness", {}).get("block_bootstrap", {})
    d_var = config.get("gate1", "D_variant"); d_thr = float(config.get("gate1", "D_threshold_abs"))
    hits = hits_series(target, d_var, d_thr)
    boot_p = None
    if len(hits) > 0 and bb:
        boot_p = block_bootstrap_pvalue(hits.tolist(),
                                        int(bb.get("block_size_windows", 10)),
                                        int(bb.get("n_resamples", 10000)),
                                        int(bb.get("seed", 42)))

    summary = consolidate(
        gate_results=gates, config_version=config.config_version, input_hash=data.input_hash,
        n_total_complete=data.n_total_complete, n_after_filter=data.n_after_filter,
        min_n_for_verdict=min_n,
        extra={
            "run_at_utc": utc_now(), "split_method": args.split, "evaluated_on": args.on,
            "n_train": len(train), "n_holdout": len(holdout),
            "gate1_bootstrap_p_robustness": boot_p,
            "kfold_accuracy": kfold,
            "bonferroni": {"alpha_uncorrected": alpha, "n_tests": n_tests, "alpha_corrected": alpha_corr},
        },
    )

    print(json.dumps({k: summary[k] for k in ["project_verdict", "n_after_filter", "output_hash"]}, indent=2))
    print(f"gate1 accuracy={gates[0].primary_metric:.4f} verdict={gates[0].verdict} | bootstrap_p={boot_p}")
    for g in gates:
        print(f"  {g.name}: {g.verdict} (metric={g.primary_metric})")

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nReporte: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
