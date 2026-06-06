"""Helpers estadisticos deterministas: binomtest, bonferroni, kfold."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Iterator

import pandas as pd
from scipy.stats import binomtest


@dataclass(frozen=True)
class BinomialResult:
    n: int
    successes: int
    accuracy: float
    p_value_two_sided: float
    ci95_low: float
    ci95_high: float


def binomial_accuracy_test(successes: int, n: int, p_null: float = 0.5) -> BinomialResult:
    """Test binomial sobre accuracy direccional. Deterministico."""
    if n == 0:
        return BinomialResult(0, 0, float('nan'), float('nan'), float('nan'), float('nan'))
    res = binomtest(successes, n, p=p_null, alternative='two-sided')
    ci = res.proportion_ci(confidence_level=0.95, method='exact')
    return BinomialResult(
        n=n,
        successes=successes,
        accuracy=successes / n,
        p_value_two_sided=float(res.pvalue),
        ci95_low=float(ci.low),
        ci95_high=float(ci.high),
    )


def bonferroni_alpha(alpha: float, n_tests: int) -> float:
    """Corrige alpha por multiple testing. n_tests=1 devuelve alpha sin cambio."""
    if n_tests < 1:
        raise ValueError('n_tests debe ser >= 1')
    return alpha / n_tests


def deterministic_kfold_indices(n_rows: int, n_splits: int, seed: int) -> list[tuple[list[int], list[int]]]:
    """K-fold split deterministico sin sklearn. Usa random.Random(seed) puro.

    Devuelve lista de (train_idx, test_idx) para cada fold.
    """
    if n_splits < 2:
        raise ValueError('n_splits debe ser >= 2')
    indices = list(range(n_rows))
    rng = random.Random(seed)
    rng.shuffle(indices)
    fold_size = n_rows // n_splits
    folds: list[list[int]] = []
    for i in range(n_splits):
        start = i * fold_size
        end = start + fold_size if i < n_splits - 1 else n_rows
        folds.append(indices[start:end])
    splits = []
    for i in range(n_splits):
        test_idx = sorted(folds[i])
        train_idx = sorted(idx for j, fold in enumerate(folds) if j != i for idx in fold)
        splits.append((train_idx, test_idx))
    return splits


def deterministic_train_holdout_split(df: pd.DataFrame, ratio: float, seed: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split estable: mismo df + mismo seed = mismas filas en train/holdout."""
    if not 0.0 < ratio < 1.0:
        raise ValueError('ratio debe estar en (0, 1)')
    indices = list(range(len(df)))
    rng = random.Random(seed)
    rng.shuffle(indices)
    cutoff = int(len(df) * ratio)
    train_idx = sorted(indices[:cutoff])
    holdout_idx = sorted(indices[cutoff:])
    return df.iloc[train_idx].reset_index(drop=True), df.iloc[holdout_idx].reset_index(drop=True)
