"""Carga read-only de SQLite + hash SHA256 del input.

Cualquier dos corridas con misma DB deben producir mismo input_hash.
Distinto hash = los datos cambiaron, conclusiones anteriores invalidas.
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from src.analysis.config import AnalysisConfig


@dataclass(frozen=True)
class LoadedData:
    observations: pd.DataFrame
    trajectory: pd.DataFrame
    input_hash: str
    n_total_complete: int
    n_after_filter: int


def _hash_dataframe(df: pd.DataFrame) -> str:
    """SHA256 sobre el CSV ordenado del DataFrame. Deterministico."""
    sorted_df = df.sort_index(axis=1).sort_values(list(df.columns)).reset_index(drop=True)
    csv_bytes = sorted_df.to_csv(index=False).encode('utf-8')
    return hashlib.sha256(csv_bytes).hexdigest()


def load_data(config: AnalysisConfig, db_path_override: str | Path | None = None) -> LoadedData:
    db_path = Path(db_path_override) if db_path_override is not None else Path(config.get('data', 'db_path_relative'))
    if not db_path.exists():
        raise FileNotFoundError(f'SQLite no encontrada: {db_path}')

    conn = sqlite3.connect(db_path)
    try:
        observations_all = pd.read_sql_query('SELECT * FROM observations', conn)
        trajectory_all = pd.read_sql_query('SELECT * FROM observations_intrawindow', conn)
    finally:
        conn.close()

    outcome_in = tuple(config.get('data', 'filter_outcome_in'))
    is_incomplete_filter = config.get('data', 'filter_is_incomplete')
    exclude_window_id = config.get('data', 'exclude_window_id')
    min_n_trades = config.get('data', 'min_n_trades_15m')

    n_total_complete = int(
        observations_all.query(
            "outcome in @outcome_in and is_incomplete == @is_incomplete_filter and window_id != @exclude_window_id",
            local_dict={'outcome_in': outcome_in, 'is_incomplete_filter': is_incomplete_filter, 'exclude_window_id': exclude_window_id},
        ).shape[0]
    )

    obs_filtered = observations_all.query(
        "outcome in @outcome_in and is_incomplete == @is_incomplete_filter and window_id != @exclude_window_id and n_trades_15m >= @min_n_trades",
        local_dict={
            'outcome_in': outcome_in,
            'is_incomplete_filter': is_incomplete_filter,
            'exclude_window_id': exclude_window_id,
            'min_n_trades': min_n_trades,
        },
    ).reset_index(drop=True)

    valid_windows = set(obs_filtered['window_id'])
    traj_filtered = trajectory_all[trajectory_all['window_id'].isin(valid_windows)].reset_index(drop=True)

    h_obs = _hash_dataframe(obs_filtered)
    h_traj = _hash_dataframe(traj_filtered)
    input_hash = hashlib.sha256((h_obs + h_traj).encode('utf-8')).hexdigest()

    return LoadedData(
        observations=obs_filtered,
        trajectory=traj_filtered,
        input_hash=input_hash,
        n_total_complete=n_total_complete,
        n_after_filter=int(obs_filtered.shape[0]),
    )
