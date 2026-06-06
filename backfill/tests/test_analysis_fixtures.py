"""Synthetic fixtures: gates con datos sinteticos donde sabemos la respuesta.

Si un gate falla aqui, hay bug en el codigo del gate. No tiene sentido
correr sobre datos reales si el gate falla sobre datos perfectos.
"""

from __future__ import annotations

import unittest
from pathlib import Path

import pandas as pd

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.analysis.config import load_config
from src.analysis.gates import (
    gate1_d_vs_coin,
    gate2_d_vs_market,
    gate3_lead_lag,
    gate4a_chainlink_deribit,
    gate4b_costs,
    kfold_accuracy,
)
from src.analysis.stats import (
    binomial_accuracy_test,
    bonferroni_alpha,
    deterministic_kfold_indices,
    deterministic_train_holdout_split,
)


def make_perfect_signal_dataset(n: int = 200) -> pd.DataFrame:
    """D positivo siempre coincide con Up, D negativo siempre con Down."""
    rows = []
    for i in range(n):
        d = 10.0 if i % 2 == 0 else -10.0
        outcome = 'Up' if d > 0 else 'Down'
        rows.append({
            'window_id': f'syn-{i}',
            'D_15m_otm_dotm': d,
            'D_5m_otm_dotm': d * 0.5,
            'D_10m_otm_dotm': d * 0.8,
            'D_5m_atm': 0.0,
            'D_10m_atm': 0.0,
            'D_15m_atm': 0.0,
            'V_5m_otm_dotm': 1.0,
            'V_10m_otm_dotm': 1.0,
            'V_15m_otm_dotm': 1.0,
            'n_trades_5m': 50,
            'n_trades_10m': 80,
            'n_trades_15m': 100,
            'pm_up_price_open': 0.50,
            'pm_up_price_close': 0.99 if outcome == 'Up' else 0.01,
            'deribit_index_open': 75048.0 if outcome == 'Up' else 74952.0,
            'deribit_index_close': 75100.0 if outcome == 'Up' else 74900.0,
            'price_to_beat': 75000.0,
            'chainlink_close': 75050.0 if outcome == 'Up' else 74950.0,
            'outcome': outcome,
            'is_incomplete': 0,
        })
    return pd.DataFrame(rows)


def make_random_signal_dataset(n: int = 200, seed: int = 42) -> pd.DataFrame:
    """D y outcome independientes. Accuracy debe estar cerca de 0.5."""
    import random
    rng = random.Random(seed)
    rows = []
    for i in range(n):
        d = (rng.random() - 0.5) * 30.0
        outcome = 'Up' if rng.random() > 0.5 else 'Down'
        rows.append({
            'window_id': f'rnd-{i}',
            'D_15m_otm_dotm': d,
            'pm_up_price_open': 0.5,
            'pm_up_price_close': 0.99 if outcome == 'Up' else 0.01,
            'deribit_index_open': 75000.0,
            'deribit_index_close': 75050.0,
            'price_to_beat': 75000.0,
            'chainlink_close': 75050.0,
            'outcome': outcome,
            'is_incomplete': 0,
            'n_trades_15m': 100,
        })
    return pd.DataFrame(rows)


def make_perfect_trajectory(window_ids: list[str], move_at_t: int = 120) -> pd.DataFrame:
    """Trayectoria que se mueve >0.05 exactamente en t=move_at_t."""
    rows = []
    for wid in window_ids:
        for t in range(0, 901, 30):
            price = 0.5 if t < move_at_t else 0.6
            rows.append({'window_id': wid, 't_seconds': t, 'pm_up_price': price})
    return pd.DataFrame(rows)


class TestStatsHelpers(unittest.TestCase):
    def test_binomial_perfect(self):
        result = binomial_accuracy_test(100, 100)
        self.assertEqual(result.accuracy, 1.0)
        self.assertLess(result.p_value_two_sided, 0.001)

    def test_binomial_random(self):
        result = binomial_accuracy_test(50, 100)
        self.assertEqual(result.accuracy, 0.5)
        self.assertGreater(result.p_value_two_sided, 0.5)

    def test_binomial_empty(self):
        result = binomial_accuracy_test(0, 0)
        self.assertEqual(result.n, 0)

    def test_bonferroni(self):
        self.assertAlmostEqual(bonferroni_alpha(0.05, 5), 0.01)
        self.assertEqual(bonferroni_alpha(0.05, 1), 0.05)
        with self.assertRaises(ValueError):
            bonferroni_alpha(0.05, 0)

    def test_kfold_deterministic(self):
        splits1 = deterministic_kfold_indices(100, 5, 42)
        splits2 = deterministic_kfold_indices(100, 5, 42)
        self.assertEqual(splits1, splits2)

    def test_kfold_coverage(self):
        splits = deterministic_kfold_indices(100, 5, 42)
        all_test = set()
        for _, test_idx in splits:
            all_test.update(test_idx)
        self.assertEqual(all_test, set(range(100)))

    def test_train_holdout_deterministic(self):
        df = pd.DataFrame({'x': list(range(100))})
        t1, h1 = deterministic_train_holdout_split(df, 0.7, 42)
        t2, h2 = deterministic_train_holdout_split(df, 0.7, 42)
        pd.testing.assert_frame_equal(t1, t2)
        pd.testing.assert_frame_equal(h1, h2)
        self.assertEqual(len(t1), 70)
        self.assertEqual(len(h1), 30)


class TestGates(unittest.TestCase):
    def setUp(self):
        self.config = load_config(Path(__file__).resolve().parents[1] / 'analysis_config.json')

    def test_gate1_perfect_signal_advances(self):
        df = make_perfect_signal_dataset(1500)
        result = gate1_d_vs_coin(df, self.config, alpha_corrected=0.01, min_n_for_verdict=1000)
        self.assertEqual(result.verdict, 'AVANZA')
        self.assertEqual(result.primary_metric, 1.0)

    def test_gate1_random_signal_fin(self):
        df = make_random_signal_dataset(2000, seed=42)
        result = gate1_d_vs_coin(df, self.config, alpha_corrected=0.01, min_n_for_verdict=1000)
        self.assertEqual(result.verdict, 'FIN')
        self.assertAlmostEqual(result.primary_metric, 0.5, delta=0.1)

    def test_gate1_small_sample_insuficiente(self):
        df = make_perfect_signal_dataset(50)
        result = gate1_d_vs_coin(df, self.config, alpha_corrected=0.01, min_n_for_verdict=1000)
        self.assertEqual(result.verdict, 'INSUFICIENTE')

    def test_gate2_perfect_signal_advances(self):
        df = make_perfect_signal_dataset(1500)
        result = gate2_d_vs_market(df, self.config, alpha_corrected=0.01, min_n_for_verdict=1000)
        self.assertEqual(result.verdict, 'AVANZA')

    def test_gate3_late_move_advances(self):
        df = make_perfect_signal_dataset(1500)
        traj = make_perfect_trajectory(list(df['window_id']), move_at_t=120)
        result = gate3_lead_lag(df, traj, self.config, min_n_for_verdict=1000)
        self.assertEqual(result.verdict, 'AVANZA')
        self.assertGreaterEqual(result.primary_metric, 30.0)

    def test_gate3_instant_move_fin(self):
        df = make_perfect_signal_dataset(1500)
        traj = make_perfect_trajectory(list(df['window_id']), move_at_t=0)
        result = gate3_lead_lag(df, traj, self.config, min_n_for_verdict=1000)
        self.assertEqual(result.verdict, 'FIN')

    def test_gate4a_synthetic_close_prices_advances(self):
        df = make_perfect_signal_dataset(1500)
        result = gate4a_chainlink_deribit(df, self.config, min_n_for_verdict=1000)
        self.assertEqual(result.verdict, 'AVANZA')

    def test_gate4b_perfect_signal_evaluates(self):
        df = make_perfect_signal_dataset(1500)
        result = gate4b_costs(df, self.config, alpha_corrected=0.01, min_n_for_verdict=1000)
        # con accuracy 1.0 y fees 7%, EV deberia ser positivo
        self.assertEqual(result.verdict, 'AVANZA')
        self.assertGreater(result.primary_metric, 0)

    def test_kfold_perfect_signal(self):
        df = make_perfect_signal_dataset(500)
        result = kfold_accuracy(df, 'D_15m_otm_dotm', 5.0, 5, 42)
        self.assertAlmostEqual(result['mean_accuracy'], 1.0, places=3)
        self.assertEqual(result['n_splits'], 5)


if __name__ == '__main__':
    unittest.main()
