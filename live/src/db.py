"""Persistencia SQLite para snapshots de observaciones."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Final

OBSERVATIONS_TABLE: Final[str] = "observations"
INTRAWINDOW_TABLE: Final[str] = "observations_intrawindow"

INTRAWINDOW_SCHEMA_SQL: Final[str] = f"""
CREATE TABLE IF NOT EXISTS {INTRAWINDOW_TABLE} (
    window_id TEXT NOT NULL,
    t_seconds INTEGER NOT NULL,
    pm_up_price REAL,
    sampled_at_utc TEXT,
    PRIMARY KEY (window_id, t_seconds)
);
CREATE INDEX IF NOT EXISTS idx_intrawindow_window_id ON {INTRAWINDOW_TABLE}(window_id);
""".strip()

SCHEMA_SQL: Final[str] = f"""
CREATE TABLE IF NOT EXISTS {OBSERVATIONS_TABLE} (
    window_id TEXT PRIMARY KEY,
    ts_open TEXT,
    price_to_beat REAL,
    pm_up_price_open REAL,
    deribit_index_open REAL,
    D_5m_otm_dotm REAL,
    D_10m_otm_dotm REAL,
    D_15m_otm_dotm REAL,
    D_5m_atm REAL,
    D_10m_atm REAL,
    D_15m_atm REAL,
    V_5m_otm_dotm REAL,
    V_10m_otm_dotm REAL,
    V_15m_otm_dotm REAL,
    n_trades_5m INTEGER,
    n_trades_10m INTEGER,
    n_trades_15m INTEGER,
    ts_close TEXT,
    deribit_index_close REAL,
    chainlink_close REAL,
    outcome TEXT CHECK (outcome IN ('Up', 'Down') OR outcome IS NULL),
    pm_up_price_close REAL,
    is_incomplete INTEGER DEFAULT 0,
    insufficient_flow INTEGER DEFAULT 0,
    notes TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_observations_ts_open ON observations(ts_open);
""".strip()

OPEN_COLUMNS = [
    'window_id','ts_open','price_to_beat','pm_up_price_open','deribit_index_open',
    'D_5m_otm_dotm','D_10m_otm_dotm','D_15m_otm_dotm',
    'D_5m_atm','D_10m_atm','D_15m_atm',
    'V_5m_otm_dotm','V_10m_otm_dotm','V_15m_otm_dotm',
    'n_trades_5m','n_trades_10m','n_trades_15m',
    'is_incomplete','insufficient_flow','notes'
]
CLOSE_COLUMNS = ['ts_close','deribit_index_close','chainlink_close','outcome','pm_up_price_close','is_incomplete','insufficient_flow','notes']


def connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(path)


def initialize_database(db_path: str | Path) -> Path:
    path = Path(db_path)
    with connect(path) as connection:
        connection.executescript(SCHEMA_SQL)
        connection.executescript(INTRAWINDOW_SCHEMA_SQL)
        connection.commit()
    return path


def insert_intrawindow_sample(db_path: str | Path, window_id: str, t_seconds: int, pm_up_price: float | None, sampled_at_utc: str | None) -> None:
    with connect(db_path) as connection:
        connection.execute(
            f"INSERT OR REPLACE INTO {INTRAWINDOW_TABLE} (window_id, t_seconds, pm_up_price, sampled_at_utc) VALUES (?, ?, ?, ?)",
            (window_id, int(t_seconds), pm_up_price, sampled_at_utc),
        )
        connection.commit()


def fetch_intrawindow(db_path: str | Path, window_id: str) -> list[dict]:
    with connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            f"SELECT * FROM {INTRAWINDOW_TABLE} WHERE window_id = ? ORDER BY t_seconds",
            (window_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def get_observations_columns(connection: sqlite3.Connection) -> list[str]:
    rows = connection.execute(f"PRAGMA table_info({OBSERVATIONS_TABLE})").fetchall()
    return [str(row[1]) for row in rows]


def insert_open_snapshot(db_path: str | Path, snapshot: dict) -> None:
    initialize_database(db_path)
    insert_values = [snapshot.get(column) for column in OPEN_COLUMNS]
    placeholders = ', '.join(['?'] * len(OPEN_COLUMNS))
    columns = ', '.join(OPEN_COLUMNS)
    update_assignments = ', '.join(
        f"{column} = COALESCE({OBSERVATIONS_TABLE}.{column}, excluded.{column})" if column in {'ts_open', 'price_to_beat', 'pm_up_price_open', 'deribit_index_open'}
        else f"{column} = CASE WHEN {OBSERVATIONS_TABLE}.ts_close IS NULL THEN excluded.{column} ELSE {OBSERVATIONS_TABLE}.{column} END"
        for column in OPEN_COLUMNS
        if column != 'window_id'
    )
    sql = (
        f"INSERT INTO {OBSERVATIONS_TABLE} ({columns}) VALUES ({placeholders}) "
        f"ON CONFLICT(window_id) DO UPDATE SET {update_assignments}"
    )
    with connect(db_path) as connection:
        connection.execute(sql, insert_values)
        connection.commit()


def update_close_snapshot(db_path: str | Path, window_id: str, snapshot: dict) -> None:
    assignments = ', '.join(f"{column} = ?" for column in CLOSE_COLUMNS)
    values = [snapshot.get(column) for column in CLOSE_COLUMNS] + [window_id]
    with connect(db_path) as connection:
        connection.execute(
            f"UPDATE {OBSERVATIONS_TABLE} SET {assignments} WHERE window_id = ?",
            values,
        )
        connection.commit()


def update_outcome(db_path: str | Path, window_id: str, outcome: str | None, *, is_incomplete: int = 0, notes: str | None = None) -> None:
    """Update only outcome/is_incomplete/notes for a window already-written row."""
    sets = ['outcome = ?', 'is_incomplete = ?']
    values: list = [outcome, int(is_incomplete)]
    if notes is not None:
        sets.append('notes = ?')
        values.append(notes)
    values.append(window_id)
    sql = f"UPDATE {OBSERVATIONS_TABLE} SET {', '.join(sets)} WHERE window_id = ?"
    with connect(db_path) as connection:
        connection.execute(sql, values)
        connection.commit()


def fetch_observation(db_path: str | Path, window_id: str) -> dict | None:
    with connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            f"SELECT * FROM {OBSERVATIONS_TABLE} WHERE window_id = ?",
            (window_id,),
        ).fetchone()
        return dict(row) if row else None


def list_observations(db_path: str | Path, *, limit: int | None = None) -> list[dict]:
    query = f"SELECT * FROM {OBSERVATIONS_TABLE} ORDER BY ts_open, window_id"
    params: tuple = ()
    if limit is not None:
        query += " LIMIT ?"
        params = (limit,)
    with connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(query, params).fetchall()
        return [dict(row) for row in rows]
