"""Sub-analisis EXPLORATORIOS sobre los datos.

NO son parte de los 5 gates oficiales (pre-registro v1.0.0). Estos analisis
documentan observaciones sobre los datos pero NO contribuyen al veredicto
EDGE_VALIDATED / NO_EDGE_FIN. Si en Fase 7 alguno revela un patron fuerte,
justificaria un proyecto siguiente con nuevo pre-registro.

Read-only. Deterministico. Sin randomness.
"""

from __future__ import annotations

import pandas as pd

D_VARIANTS = [
    'D_5m_otm_dotm', 'D_10m_otm_dotm', 'D_15m_otm_dotm',
    'D_5m_atm', 'D_10m_atm', 'D_15m_atm',
]


def _accuracy_for_d(df: pd.DataFrame, d_var: str, threshold: float = 0.0) -> dict:
    """Calcula accuracy direccional de una variante de D opcionalmente con filtro |D|>threshold."""
    if d_var not in df.columns:
        return {'n': 0, 'accuracy': None, 'reason': 'column missing'}
    sub = df[df[d_var].notna()]
    if threshold > 0:
        sub = sub[sub[d_var].abs() > threshold]
    else:
        sub = sub[sub[d_var] != 0]
    if len(sub) == 0:
        return {'n': 0, 'accuracy': None}
    pred = sub[d_var].apply(lambda x: 'Up' if x > 0 else 'Down')
    correct = int((pred == sub['outcome']).sum())
    return {'n': int(len(sub)), 'successes': correct, 'accuracy': correct / len(sub)}


def analyze_d_variants_accuracy(observations: pd.DataFrame) -> dict:
    """Compara accuracy direccional de las 6 variantes de D.

    NO se usa para decidir cual variante usar (eso violaria el pre-registro v1.0.0).
    Es solo informativo: documenta si hay variantes con accuracy notablemente
    distinta a la pre-registrada (D_15m_otm_dotm).
    """
    valid = observations.dropna(subset=['outcome'])
    valid = valid[valid['outcome'].isin(['Up', 'Down'])]
    if len(valid) == 0:
        return {'n_evaluated': 0}
    out = {'n_evaluated': int(len(valid)), 'variants': {}}
    for var in D_VARIANTS:
        out['variants'][var] = {
            'all': _accuracy_for_d(valid, var, threshold=0.0),
            'strong_abs_gt_5': _accuracy_for_d(valid, var, threshold=5.0),
        }
        # distribucion basica
        if var in valid.columns:
            col = valid[var].dropna()
            if len(col):
                out['variants'][var]['distribution'] = {
                    'min': float(col.min()),
                    'max': float(col.max()),
                    'mean': float(col.mean()),
                    'median': float(col.median()),
                    'stdev': float(col.std()) if len(col) > 1 else 0.0,
                }
    return out


def analyze_d_brackets(observations: pd.DataFrame, d_variant: str = 'D_15m_otm_dotm') -> dict:
    """Accuracy por bracket de |D| para detectar sweet spots no monotonicos."""
    valid = observations.dropna(subset=['outcome', d_variant])
    valid = valid[valid['outcome'].isin(['Up', 'Down'])]
    if len(valid) == 0:
        return {'d_variant': d_variant, 'n_evaluated': 0}
    brackets = [(0, 2), (2, 5), (5, 10), (10, 20), (20, 100), (100, 1e9)]
    out = {'d_variant': d_variant, 'n_evaluated': int(len(valid)), 'brackets': []}
    for lo, hi in brackets:
        sub = valid[(valid[d_variant].abs() >= lo) & (valid[d_variant].abs() < hi)]
        if len(sub) == 0:
            out['brackets'].append({'lo': lo, 'hi': hi, 'n': 0, 'accuracy': None})
            continue
        pred = sub[d_variant].apply(lambda x: 'Up' if x > 0 else 'Down')
        correct = int((pred == sub['outcome']).sum())
        out['brackets'].append({
            'lo': lo, 'hi': hi if hi < 1e9 else None,
            'n': int(len(sub)),
            'wins': correct,
            'accuracy': correct / len(sub),
        })
    return out


def analyze_pm_open_brackets(observations: pd.DataFrame, d_variant: str = 'D_15m_otm_dotm', d_threshold: float = 5.0) -> dict:
    """Accuracy de D por bracket de pm_up_price_open (con filtro |D|>threshold)."""
    valid = observations.dropna(subset=['outcome', d_variant, 'pm_up_price_open'])
    valid = valid[valid['outcome'].isin(['Up', 'Down'])]
    valid = valid[valid[d_variant].abs() > d_threshold]
    if len(valid) == 0:
        return {'d_variant': d_variant, 'd_threshold': d_threshold, 'n_evaluated': 0}
    brackets = [(0.0, 0.4), (0.4, 0.45), (0.45, 0.55), (0.55, 0.6), (0.6, 1.0)]
    out = {
        'd_variant': d_variant,
        'd_threshold': d_threshold,
        'n_evaluated': int(len(valid)),
        'brackets': [],
    }
    for lo, hi in brackets:
        sub = valid[(valid['pm_up_price_open'] >= lo) & (valid['pm_up_price_open'] < hi)]
        if len(sub) == 0:
            out['brackets'].append({'lo': lo, 'hi': hi, 'n': 0, 'accuracy': None})
            continue
        pred = sub[d_variant].apply(lambda x: 'Up' if x > 0 else 'Down')
        correct = int((pred == sub['outcome']).sum())
        out['brackets'].append({
            'lo': lo, 'hi': hi,
            'n': int(len(sub)),
            'wins': correct,
            'accuracy': correct / len(sub),
        })
    return out


def analyze_running_accuracy(observations: pd.DataFrame, d_variant: str = 'D_15m_otm_dotm', d_threshold: float = 5.0, window_size: int = 50) -> dict:
    """Running accuracy en ventanas de N para detectar degradacion temporal del edge."""
    valid = observations.dropna(subset=['outcome', d_variant, 'ts_open'])
    valid = valid[valid['outcome'].isin(['Up', 'Down'])]
    valid = valid[valid[d_variant].abs() > d_threshold]
    valid = valid.sort_values('ts_open').reset_index(drop=True)
    if len(valid) < window_size:
        return {
            'd_variant': d_variant,
            'd_threshold': d_threshold,
            'window_size': window_size,
            'n_total': int(len(valid)),
            'reason': f'n<{window_size}, no se puede calcular running',
            'chunks': [],
        }
    out = {
        'd_variant': d_variant,
        'd_threshold': d_threshold,
        'window_size': window_size,
        'n_total': int(len(valid)),
        'chunks': [],
    }
    stride = max(1, window_size // 2)
    i = 0
    while i + window_size <= len(valid):
        chunk = valid.iloc[i:i + window_size]
        pred = chunk[d_variant].apply(lambda x: 'Up' if x > 0 else 'Down')
        wins = int((pred == chunk['outcome']).sum())
        out['chunks'].append({
            'start_idx': int(i),
            'end_idx': int(i + window_size),
            'ts_open_first': str(chunk['ts_open'].iloc[0]),
            'ts_open_last': str(chunk['ts_open'].iloc[-1]),
            'wins': wins,
            'accuracy': wins / window_size,
        })
        i += stride
    return out


def analyze_chainlink_vs_polymarket_flips(observations: pd.DataFrame) -> dict:
    """Detecta last-tick risk / oracle pinning observable en nuestro setup.

    Como muestreamos Chainlink via aggregator on-chain (lag minutos) mientras
    Polymarket usa Data Streams (sub-segundo), las discrepancias entre
    sign(chainlink_close - price_to_beat) y outcome oficial revelan ventanas
    donde el ultimo tick decidio la resolucion.

    Devuelve estadisticas; NO afecta veredicto de gates oficiales.
    """
    required_cols = ['outcome', 'deribit_index_open', 'deribit_index_close',
                     'price_to_beat', 'chainlink_close', 'D_15m_otm_dotm']
    valid = observations.dropna(subset=required_cols).copy()
    valid = valid[valid['outcome'].isin(['Up', 'Down'])]

    if len(valid) == 0:
        return {'n_evaluated': 0, 'reason': 'no rows with all required columns'}

    valid['deribit_dir'] = (valid['deribit_index_close'] >= valid['deribit_index_open']).map({True: 'Up', False: 'Down'})
    valid['chainlink_dir'] = (valid['chainlink_close'] >= valid['price_to_beat']).map({True: 'Up', False: 'Down'})
    valid['chainlink_move_abs'] = (valid['chainlink_close'] - valid['price_to_beat']).abs()
    valid['deribit_move_abs'] = (valid['deribit_index_close'] - valid['deribit_index_open']).abs()
    valid['chainlink_flip'] = valid['chainlink_dir'] != valid['outcome']
    valid['deribit_flip'] = valid['deribit_dir'] != valid['outcome']

    n = int(len(valid))
    n_chainlink_flips = int(valid['chainlink_flip'].sum())
    n_deribit_flips = int(valid['deribit_flip'].sum())

    stable = valid[~valid['chainlink_flip']]
    flippy = valid[valid['chainlink_flip']]

    def _d_accuracy(sub: pd.DataFrame, d_threshold: float = 0.0) -> dict:
        sub_filt = sub[sub['D_15m_otm_dotm'].abs() > d_threshold] if d_threshold > 0 else sub
        if len(sub_filt) == 0:
            return {'n': 0, 'accuracy': None}
        sign_d = sub_filt['D_15m_otm_dotm'].apply(lambda x: 'Up' if x > 0 else 'Down')
        successes = int((sign_d == sub_filt['outcome']).sum())
        return {'n': int(len(sub_filt)), 'accuracy': successes / len(sub_filt), 'successes': successes}

    return {
        'n_evaluated': n,
        'chainlink_flips': {
            'count': n_chainlink_flips,
            'rate': n_chainlink_flips / n if n else 0.0,
        },
        'deribit_flips': {
            'count': n_deribit_flips,
            'rate': n_deribit_flips / n if n else 0.0,
        },
        'movement_magnitude': {
            'chainlink_move_median_stable': float(stable['chainlink_move_abs'].median()) if len(stable) else None,
            'chainlink_move_median_flippy': float(flippy['chainlink_move_abs'].median()) if len(flippy) else None,
            'deribit_move_median_stable': float(stable['deribit_move_abs'].median()) if len(stable) else None,
            'deribit_move_median_flippy': float(flippy['deribit_move_abs'].median()) if len(flippy) else None,
        },
        'd_accuracy_conditional': {
            'all_D_stable_windows': _d_accuracy(stable),
            'all_D_flippy_windows': _d_accuracy(flippy),
            'strong_D_stable_windows': _d_accuracy(stable, d_threshold=5.0),
            'strong_D_flippy_windows': _d_accuracy(flippy, d_threshold=5.0),
        },
        '_doc': 'EXPLORATORIO. NO parte del pre-registro v1.0.0. Solo para documentar last-tick risk observado.',
    }
