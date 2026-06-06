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
    """Split ALEATORIO estable (Exp1; en Exp2 es solo comparativo secundario)."""
    if not 0.0 < ratio < 1.0:
        raise ValueError('ratio debe estar en (0, 1)')
    indices = list(range(len(df)))
    rng = random.Random(seed)
    rng.shuffle(indices)
    cutoff = int(len(df) * ratio)
    train_idx = sorted(indices[:cutoff])
    holdout_idx = sorted(indices[cutoff:])
    return df.iloc[train_idx].reset_index(drop=True), df.iloc[holdout_idx].reset_index(drop=True)


def temporal_train_holdout_split(df: pd.DataFrame, ratio: float, time_col: str = 'ts_open') -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split TEMPORAL (Exp2 OFICIAL): train = primeros `ratio` por tiempo; holdout = resto (más reciente).

    Anti-leakage: el holdout es estrictamente posterior al train. Determinista (ordena por tiempo).
    """
    if not 0.0 < ratio < 1.0:
        raise ValueError('ratio debe estar en (0, 1)')
    ordered = df.sort_values(time_col, kind='stable').reset_index(drop=True)
    cutoff = int(len(ordered) * ratio)
    return ordered.iloc[:cutoff].reset_index(drop=True), ordered.iloc[cutoff:].reset_index(drop=True)


def block_bootstrap_pvalue(hits, block_size: int, n_resamples: int, seed: int) -> float:
    """p-value de dos colas robusto a autocorrelación (H0: accuracy = 0.5).

    hits = secuencia 1/0 (acierto direccional) en orden temporal. Método: moving-block
    bootstrap (Künsch 1989) — remuestrea bloques contiguos circulares (preserva la
    dependencia serial). Construye la distribución bootstrap de la media; el p-value es
    2× la cola: P(media_bootstrap se aleja de obs en dirección de 0.5). Determinista (seed).
    """
    import numpy as np
    arr = np.asarray(hits, dtype=float)
    n = len(arr)
    if n == 0:
        return float('nan')
    obs = arr.mean()
    rng = np.random.default_rng(seed)
    n_blocks = int(np.ceil(n / block_size))
    idx = np.arange(n)
    means = np.empty(n_resamples)
    for r in range(n_resamples):
        starts = rng.integers(0, n, size=n_blocks)
        take = np.concatenate([np.mod(np.arange(s, s + block_size), n) for s in starts])[:n]
        means[r] = arr[take].mean()
    # SE bootstrap de la media; z bajo H0 (0.5). p de dos colas vía normal sobre el SE empírico.
    se = means.std(ddof=1)
    if se == 0:
        return 0.0 if obs != 0.5 else 1.0
    from scipy.stats import norm
    z = abs(obs - 0.5) / se
    return float(2.0 * (1.0 - norm.cdf(z)))
