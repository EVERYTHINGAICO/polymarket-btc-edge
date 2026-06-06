"""Los 4 gates de PROJECT_DESIGN seccion 7.B. Funciones puras deterministas."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

from src.analysis.config import AnalysisConfig
from src.analysis.stats import (
    BinomialResult,
    binomial_accuracy_test,
    deterministic_kfold_indices,
)

Verdict = Literal['AVANZA', 'FIN', 'INSUFICIENTE']


@dataclass(frozen=True)
class GateResult:
    name: str
    verdict: Verdict
    primary_metric: float
    detail: dict


def _verdict_from_test(
    n: int,
    accuracy: float,
    p_value: float,
    min_n: int,
    min_accuracy: float,
    alpha_corrected: float,
) -> Verdict:
    if n < min_n:
        return 'INSUFICIENTE'
    if accuracy >= min_accuracy and p_value < alpha_corrected:
        return 'AVANZA'
    return 'FIN'


def gate1_d_vs_coin(
    df: pd.DataFrame,
    config: AnalysisConfig,
    alpha_corrected: float,
    min_n_for_verdict: int,
) -> GateResult:
    """7.B Gate 1: D vs la moneda. Filtrar |D|>umbral, accuracy + binomtest."""
    d_var = config.get('gate1', 'D_variant')
    d_thr = config.get('gate1', 'D_threshold_abs')
    min_acc = config.get('gate1', 'min_accuracy_to_advance')

    sub = df[df[d_var].abs() > d_thr].reset_index(drop=True)
    if len(sub) == 0:
        return GateResult('Gate 1', 'INSUFICIENTE', float('nan'), {'n': 0, 'reason': 'no rows pass threshold'})

    sign_d = sub[d_var].apply(lambda x: 'Up' if x > 0 else 'Down')
    successes = int((sign_d == sub['outcome']).sum())
    test = binomial_accuracy_test(successes, len(sub))
    verdict = _verdict_from_test(len(sub), test.accuracy, test.p_value_two_sided, min_n_for_verdict, min_acc, alpha_corrected)
    return GateResult(
        name='Gate 1',
        verdict=verdict,
        primary_metric=test.accuracy,
        detail={
            'D_variant': d_var,
            'D_threshold_abs': d_thr,
            'n': test.n,
            'successes': test.successes,
            'accuracy': test.accuracy,
            'p_value_two_sided': test.p_value_two_sided,
            'ci95': [test.ci95_low, test.ci95_high],
            'alpha_corrected': alpha_corrected,
            'min_accuracy_required': min_acc,
        },
    )


def gate2_d_vs_market(
    df: pd.DataFrame,
    config: AnalysisConfig,
    alpha_corrected: float,
    min_n_for_verdict: int,
) -> GateResult:
    """7.B Gate 2: D vs mercado indeciso. Filtrar pm_up_price_open in [a,b], accuracy + binomtest."""
    d_var = config.get('gate2', 'D_variant')
    d_thr = config.get('gate2', 'D_threshold_abs')
    rng = config.get('gate2', 'indecisive_range_inclusive')
    min_acc = config.get('gate2', 'min_accuracy_to_advance')

    lo, hi = float(rng[0]), float(rng[1])
    sub = df[(df['pm_up_price_open'] >= lo) & (df['pm_up_price_open'] <= hi) & (df[d_var].abs() > d_thr)].reset_index(drop=True)
    if len(sub) == 0:
        return GateResult('Gate 2', 'INSUFICIENTE', float('nan'), {'n': 0, 'reason': 'no rows pass indecisive+threshold'})

    sign_d = sub[d_var].apply(lambda x: 'Up' if x > 0 else 'Down')
    successes = int((sign_d == sub['outcome']).sum())
    test = binomial_accuracy_test(successes, len(sub))
    implied_edge_mean = float((sub['pm_up_price_open'] - 0.5).abs().mean())
    verdict = _verdict_from_test(len(sub), test.accuracy, test.p_value_two_sided, min_n_for_verdict, min_acc, alpha_corrected)
    return GateResult(
        name='Gate 2',
        verdict=verdict,
        primary_metric=test.accuracy,
        detail={
            'indecisive_range': [lo, hi],
            'D_variant': d_var,
            'D_threshold_abs': d_thr,
            'n': test.n,
            'successes': test.successes,
            'accuracy': test.accuracy,
            'p_value_two_sided': test.p_value_two_sided,
            'ci95': [test.ci95_low, test.ci95_high],
            'implied_edge_mean_abs': implied_edge_mean,
            'alpha_corrected': alpha_corrected,
            'min_accuracy_required': min_acc,
        },
    )


def gate3_lead_lag(
    df: pd.DataFrame,
    trajectory: pd.DataFrame,
    config: AnalysisConfig,
    min_n_for_verdict: int,
) -> GateResult:
    """7.B Gate 3: D se adelanta o es contemporanea? Lead-lag con trayectoria."""
    move_thr = float(config.get('gate3', 'move_threshold_abs'))
    min_t_move = float(config.get('gate3', 'min_t_move_seconds_to_advance'))

    if len(trajectory) == 0:
        return GateResult('Gate 3', 'INSUFICIENTE', float('nan'), {'reason': 'no trajectory'})

    merged = trajectory.merge(df[['window_id', 'pm_up_price_open']], on='window_id', how='inner')
    merged['abs_move'] = (merged['pm_up_price'] - merged['pm_up_price_open']).abs()
    moves = merged[merged['abs_move'] > move_thr].groupby('window_id', as_index=False).agg(t_move=('t_seconds', 'min'))

    n = len(moves)
    if n == 0:
        return GateResult('Gate 3', 'INSUFICIENTE', float('nan'), {'reason': 'no windows with intra-window move beyond threshold', 'n_windows_evaluated': int(df['window_id'].nunique())})

    median_t_move = float(moves['t_move'].median())
    p25 = float(moves['t_move'].quantile(0.25))
    p75 = float(moves['t_move'].quantile(0.75))

    if n < min_n_for_verdict:
        verdict: Verdict = 'INSUFICIENTE'
    elif median_t_move >= min_t_move:
        verdict = 'AVANZA'
    else:
        verdict = 'FIN'

    return GateResult(
        name='Gate 3',
        verdict=verdict,
        primary_metric=median_t_move,
        detail={
            'move_threshold_abs': move_thr,
            'n_windows_with_move': n,
            'median_t_move_seconds': median_t_move,
            'p25_t_move_seconds': p25,
            'p75_t_move_seconds': p75,
            'min_t_move_required_seconds': min_t_move,
        },
    )


def gate4a_chainlink_deribit(
    df: pd.DataFrame,
    config: AnalysisConfig,
    min_n_for_verdict: int,
) -> GateResult:
    """7.B Gate 4a: desfase deribit_index_open vs chainlink_close menor que movimiento tipico?"""
    ratio_thr = float(config.get('gate4a', 'ratio_threshold_to_advance'))

    sub = df.dropna(subset=['deribit_index_open', 'chainlink_close', 'price_to_beat']).reset_index(drop=True)
    if len(sub) == 0:
        return GateResult('Gate 4a', 'INSUFICIENTE', float('nan'), {'reason': 'no rows with all 3 prices'})

    gap = (sub['deribit_index_open'] - sub['chainlink_close']).abs()
    typical_move = (sub['chainlink_close'] - sub['price_to_beat']).abs()
    valid = typical_move > 0
    if not valid.any():
        return GateResult('Gate 4a', 'INSUFICIENTE', float('nan'), {'reason': 'typical move zero'})
    ratios = gap[valid] / typical_move[valid]
    median_ratio = float(ratios.median())

    if len(sub) < min_n_for_verdict:
        verdict: Verdict = 'INSUFICIENTE'
    elif median_ratio < ratio_thr:
        verdict = 'AVANZA'
    else:
        verdict = 'FIN'

    return GateResult(
        name='Gate 4a',
        verdict=verdict,
        primary_metric=median_ratio,
        detail={
            'n': int(len(sub)),
            'median_gap_chainlink_deribit_abs': float(gap.median()),
            'median_typical_move_abs': float(typical_move.median()),
            'median_ratio_gap_over_move': median_ratio,
            'ratio_threshold_required': ratio_thr,
        },
    )


def gate4b_costs(
    df: pd.DataFrame,
    config: AnalysisConfig,
    alpha_corrected: float,
    min_n_for_verdict: int,
) -> GateResult:
    """7.B Gate 4b: backtest con spread + fees. EV neto positivo?"""
    d_var = config.get('gate1', 'D_variant')
    d_thr = config.get('gate1', 'D_threshold_abs')
    fee = float(config.get('gate4b', 'polymarket_taker_fee_rate'))
    spread = float(config.get('gate4b', 'spread_estimate'))
    slippage = float(config.get('gate4b', 'slippage_estimate'))
    min_ev = float(config.get('gate4b', 'min_ev_per_bet_to_advance'))

    sub = df[df[d_var].abs() > d_thr].reset_index(drop=True)
    if len(sub) == 0:
        return GateResult('Gate 4b', 'INSUFICIENTE', float('nan'), {'reason': 'no rows pass threshold'})

    sub = sub.copy()
    sub['side'] = sub[d_var].apply(lambda x: 'Up' if x > 0 else 'Down')
    sub['entry_price'] = sub.apply(
        lambda r: r['pm_up_price_open'] if r['side'] == 'Up' else (1 - r['pm_up_price_open']),
        axis=1,
    )
    sub['entry_price_with_costs'] = sub['entry_price'] + spread + slippage
    sub['win'] = (sub['side'] == sub['outcome']).astype(int)
    sub['payoff_if_win'] = 1.0
    sub['payoff_if_lose'] = 0.0
    sub['gross_pnl'] = sub['win'] * sub['payoff_if_win'] - sub['entry_price_with_costs']
    sub['fees'] = fee * sub['entry_price_with_costs']
    sub['net_pnl'] = sub['gross_pnl'] - sub['fees']

    n = len(sub)
    ev_per_bet = float(sub['net_pnl'].mean())
    win_rate = float(sub['win'].mean())

    if n < min_n_for_verdict:
        verdict: Verdict = 'INSUFICIENTE'
    elif ev_per_bet >= min_ev:
        verdict = 'AVANZA'
    else:
        verdict = 'FIN'

    return GateResult(
        name='Gate 4b',
        verdict=verdict,
        primary_metric=ev_per_bet,
        detail={
            'n_bets': n,
            'win_rate': win_rate,
            'taker_fee_rate': fee,
            'spread_estimate': spread,
            'slippage_estimate': slippage,
            'ev_net_per_bet': ev_per_bet,
            'min_ev_required': min_ev,
            'total_net_pnl': float(sub['net_pnl'].sum()),
        },
    )


def kfold_accuracy(df: pd.DataFrame, d_variant: str, d_threshold: float, n_splits: int, seed: int) -> dict:
    """Calcula accuracy via K-fold sobre Gate 1. Devuelve mean/std/folds."""
    if len(df) == 0:
        return {'n_splits': 0, 'mean_accuracy': float('nan'), 'std_accuracy': float('nan'), 'fold_accuracies': []}
    splits = deterministic_kfold_indices(len(df), n_splits, seed)
    accuracies: list[float] = []
    for _, test_idx in splits:
        fold = df.iloc[test_idx]
        sub = fold[fold[d_variant].abs() > d_threshold]
        if len(sub) == 0:
            accuracies.append(float('nan'))
            continue
        sign_d = sub[d_variant].apply(lambda x: 'Up' if x > 0 else 'Down')
        accuracies.append(float((sign_d == sub['outcome']).sum() / len(sub)))
    valid_accs = [a for a in accuracies if a == a]  # remove nan
    if not valid_accs:
        return {'n_splits': n_splits, 'mean_accuracy': float('nan'), 'std_accuracy': float('nan'), 'fold_accuracies': accuracies}
    mean = sum(valid_accs) / len(valid_accs)
    var = sum((a - mean) ** 2 for a in valid_accs) / max(1, len(valid_accs) - 1)
    return {
        'n_splits': n_splits,
        'mean_accuracy': mean,
        'std_accuracy': var ** 0.5,
        'fold_accuracies': accuracies,
    }
