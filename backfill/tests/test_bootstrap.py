"""EXP2-8 — Tests del block_bootstrap (TDD: definen qué es correcto ANTES de arreglar).

Propiedades que un p-value de block bootstrap (H0: accuracy=0.5, dos colas) DEBE cumplir:
  1. Señal fuerte (60%, n grande, sin autocorrelación) -> p muy bajo (<0.01).
  2. Sin señal (50%) -> p alto (>0.10), no rechaza.
  3. Sin autocorrelación, debe APROXIMAR al binomtest exacto (mismo orden de magnitud).
  4. Determinista: mismo seed + mismos datos -> mismo p.
  5. Con autocorrelación positiva, el p NO debe ser MENOR que el binomtest
     (el bootstrap debe ser más conservador, no inflar la significancia).
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
from scipy.stats import binomtest

from src.analysis.stats import block_bootstrap_pvalue


def _binom_p(hits):
    return binomtest(int(sum(hits)), len(hits), 0.5).pvalue


class TestBlockBootstrap(unittest.TestCase):
    def setUp(self):
        self.rng = np.random.default_rng(0)

    def test_strong_signal_low_p(self):
        """60% aciertos, n=1730, SIN autocorrelación -> p muy bajo."""
        hits = self.rng.binomial(1, 0.60, 1730).tolist()
        p = block_bootstrap_pvalue(hits, block_size=20, n_resamples=2000, seed=42)
        self.assertLess(p, 0.01, f"60% n=1730 debería ser muy significativo, p={p}")

    def test_no_signal_high_p(self):
        """50% aciertos -> p alto (no rechaza)."""
        hits = self.rng.binomial(1, 0.50, 1730).tolist()
        p = block_bootstrap_pvalue(hits, block_size=20, n_resamples=2000, seed=42)
        self.assertGreater(p, 0.10, f"50% no debería ser significativo, p={p}")

    def test_approximates_binomtest_iid(self):
        """Sin autocorrelación, bootstrap ~ binomtest (mismo orden de magnitud)."""
        hits = self.rng.binomial(1, 0.56, 1500).tolist()
        p_boot = block_bootstrap_pvalue(hits, block_size=20, n_resamples=3000, seed=42)
        p_binom = _binom_p(hits)
        # ambos en el mismo régimen (los dos < 0.05 o los dos > 0.05)
        self.assertEqual(p_boot < 0.05, p_binom < 0.05,
                         f"bootstrap={p_boot:.4f} vs binom={p_binom:.4f} discrepan de régimen")

    def test_deterministic(self):
        hits = self.rng.binomial(1, 0.58, 800).tolist()
        p1 = block_bootstrap_pvalue(hits, 20, 2000, 42)
        p2 = block_bootstrap_pvalue(hits, 20, 2000, 42)
        self.assertEqual(p1, p2)

    def test_autocorr_not_more_significant_than_binom(self):
        """Con autocorrelación positiva, el bootstrap NO debe dar p MENOR que binomtest
        (debe ser igual o más conservador; nunca inflar significancia)."""
        # construir serie con bloques correlacionados al 58%
        blocks = self.rng.binomial(1, 0.58, 100)
        hits = np.repeat(blocks, 15)[:1500].tolist()  # bloques de 15 iguales -> autocorr fuerte
        p_boot = block_bootstrap_pvalue(hits, block_size=15, n_resamples=3000, seed=42)
        p_binom = _binom_p(hits)
        self.assertGreaterEqual(p_boot, p_binom * 0.5,
                                f"bootstrap {p_boot:.4f} no debería inflar vs binom {p_binom:.4f}")


if __name__ == "__main__":
    unittest.main()
