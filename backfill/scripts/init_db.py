"""EXP2-2 — Crea la DB canónica de Exp2: data/observations_exp2.db

Las tablas `observations` y `observations_intrawindow` son MIRROR EXACTO del
schema de Exp1 (D:\\openclaw\\PROJECT DESIGN\\src\\db.py) para que el núcleo
analítico clonado (`src/analysis/`) se reutilice sin cambios.

Se añade una tabla NUEVA `backfill_provenance` para trazabilidad del backfill
histórico (qué fila vino de qué dataset/revision, hash de bloque, fuente del
outcome, solape con Exp1).

Determinista e idempotente: `CREATE TABLE IF NOT EXISTS`. Correrlo dos veces deja
la DB en el mismo estado. Imprime el SHA256 del DDL aplicado (no de los datos:
la DB arranca vacía).

Uso:
    py scripts/init_db.py
    py scripts/init_db.py --db data/observations_exp2.db
"""

from __future__ import annotations

import argparse
import hashlib
import sqlite3
from pathlib import Path

OBSERVATIONS_TABLE = "observations"
INTRAWINDOW_TABLE = "observations_intrawindow"
PROVENANCE_TABLE = "backfill_provenance"

# --- MIRROR EXACTO de Exp1 (no modificar: src/analysis/data.py depende de estos nombres/orden) ---
OBSERVATIONS_SCHEMA_SQL = f"""
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
CREATE INDEX IF NOT EXISTS idx_observations_ts_open ON {OBSERVATIONS_TABLE}(ts_open);
""".strip()

INTRAWINDOW_SCHEMA_SQL = f"""
CREATE TABLE IF NOT EXISTS {INTRAWINDOW_TABLE} (
    window_id TEXT NOT NULL,
    t_seconds INTEGER NOT NULL,
    pm_up_price REAL,
    sampled_at_utc TEXT,
    PRIMARY KEY (window_id, t_seconds)
);
CREATE INDEX IF NOT EXISTS idx_intrawindow_window_id ON {INTRAWINDOW_TABLE}(window_id);
""".strip()

# --- NUEVA en Exp2: trazabilidad del backfill (no la usan los gates; es provenance) ---
PROVENANCE_SCHEMA_SQL = f"""
CREATE TABLE IF NOT EXISTS {PROVENANCE_TABLE} (
    window_id TEXT NOT NULL,
    source_dataset TEXT,
    source_revision TEXT,
    source_path TEXT,
    block_hash TEXT,
    downloaded_at_utc TEXT,
    outcome_source TEXT CHECK (outcome_source IN ('clob_winner', 'dataset_resolution') OR outcome_source IS NULL),
    overlaps_exp1 INTEGER DEFAULT 0,
    PRIMARY KEY (window_id, source_dataset)
);
CREATE INDEX IF NOT EXISTS idx_provenance_window_id ON {PROVENANCE_TABLE}(window_id);
""".strip()

ALL_DDL = "\n".join([OBSERVATIONS_SCHEMA_SQL, INTRAWINDOW_SCHEMA_SQL, PROVENANCE_SCHEMA_SQL])


def init_db(db_path: str | Path) -> Path:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.executescript(OBSERVATIONS_SCHEMA_SQL)
        conn.executescript(INTRAWINDOW_SCHEMA_SQL)
        conn.executescript(PROVENANCE_SCHEMA_SQL)
        conn.commit()
    return path


def schema_sha256() -> str:
    return hashlib.sha256(ALL_DDL.encode("utf-8")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Inicializa la DB canónica de Exp2 (mirror Exp1 + provenance).")
    parser.add_argument("--db", default="data/observations_exp2.db", help="Ruta de la SQLite a crear.")
    args = parser.parse_args()

    path = init_db(args.db)

    # Verificación: listar tablas creadas
    with sqlite3.connect(path) as conn:
        tables = sorted(
            r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        )

    print(f"DB inicializada: {path.resolve()}")
    print(f"Tablas: {tables}")
    print(f"schema_sha256: {schema_sha256()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
