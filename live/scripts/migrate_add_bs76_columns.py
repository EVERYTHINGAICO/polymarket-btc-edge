"""Migration script: agrega columnas *_bs76 a observations + crea tabla deribit_trades_raw.

Aditivo, no destructivo. Se puede correr con el logger live corriendo;
SQLite tolera ALTER TABLE ADD COLUMN con la DB abierta por otros clients.

Reglas duras (PROJECT_DESIGN seccion 0):
- READ-ONLY sobre Deribit/Polymarket externos. Esto SOLO toca la DB local.
- No modifica ninguna columna ni fila existente.

Uso:
    py scripts/migrate_add_bs76_columns.py --db data/observations.db
    py scripts/migrate_add_bs76_columns.py --db data/observations.db --dry-run
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

# Las 14 columnas nuevas en observations (3 ventanas * 4 columnas + provenance)
BS76_COLUMNS = [
    ('D_5m_otm_dotm_bs76', 'REAL'),
    ('D_10m_otm_dotm_bs76', 'REAL'),
    ('D_15m_otm_dotm_bs76', 'REAL'),
    ('D_5m_atm_bs76', 'REAL'),
    ('D_10m_atm_bs76', 'REAL'),
    ('D_15m_atm_bs76', 'REAL'),
    ('V_5m_otm_dotm_bs76', 'REAL'),
    ('V_10m_otm_dotm_bs76', 'REAL'),
    ('V_15m_otm_dotm_bs76', 'REAL'),
    ('n_trades_5m_bs76', 'INTEGER'),
    ('n_trades_10m_bs76', 'INTEGER'),
    ('n_trades_15m_bs76', 'INTEGER'),
    ('bs76_computed_at_utc', 'TEXT'),
    ('bs76_source', 'TEXT'),  # 'backfill_history' o 'live_raw_logger'
]

CREATE_RAW_TRADES = """
CREATE TABLE IF NOT EXISTS deribit_trades_raw (
    trade_id        TEXT PRIMARY KEY,
    timestamp_ms    INTEGER NOT NULL,
    instrument_name TEXT NOT NULL,
    direction       TEXT NOT NULL,
    iv              REAL,
    index_price     REAL,
    amount          REAL,
    price           REAL,
    captured_at_ms  INTEGER NOT NULL
);
"""

CREATE_INDEX_TS = """
CREATE INDEX IF NOT EXISTS idx_trades_raw_ts
ON deribit_trades_raw(timestamp_ms);
"""

CREATE_INDEX_INSTR = """
CREATE INDEX IF NOT EXISTS idx_trades_raw_instrument
ON deribit_trades_raw(instrument_name);
"""


def existing_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {r[1] for r in rows}


def main() -> int:
    parser = argparse.ArgumentParser(description='Agrega columnas _bs76 y tabla deribit_trades_raw.')
    parser.add_argument('--db', required=True, help='Path to observations.db')
    parser.add_argument('--dry-run', action='store_true', help='Solo imprime SQL, no ejecuta')
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f'ERROR: DB no existe: {db_path}', file=sys.stderr)
        return 1

    statements: list[str] = []

    # Conectar para inspeccionar columnas existentes (read-only inspeccion)
    conn = sqlite3.connect(db_path)
    try:
        existing = existing_columns(conn, 'observations')
    finally:
        conn.close()

    for col, dtype in BS76_COLUMNS:
        if col in existing:
            print(f'[skip] columna {col} ya existe')
            continue
        statements.append(f'ALTER TABLE observations ADD COLUMN {col} {dtype};')

    statements.append(CREATE_RAW_TRADES.strip())
    statements.append(CREATE_INDEX_TS.strip())
    statements.append(CREATE_INDEX_INSTR.strip())

    if args.dry_run:
        print('--- DRY RUN: SQL que se ejecutaria ---')
        for s in statements:
            print(s)
        print(f'--- {len(statements)} statements ---')
        return 0

    if not statements:
        print('Nada que hacer: todas las columnas ya existen.')
        return 0

    conn = sqlite3.connect(db_path)
    try:
        conn.execute('PRAGMA journal_mode=WAL')  # WAL ya esta activo si el logger lo configuro
        for s in statements:
            print(f'>> {s.splitlines()[0]}...')
            conn.execute(s)
        conn.commit()
    finally:
        conn.close()

    # Verificacion
    conn = sqlite3.connect(db_path)
    try:
        after = existing_columns(conn, 'observations')
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    finally:
        conn.close()

    missing = [col for col, _ in BS76_COLUMNS if col not in after]
    if missing:
        print(f'ERROR: columnas faltantes despues de migrate: {missing}', file=sys.stderr)
        return 2
    if 'deribit_trades_raw' not in tables:
        print('ERROR: tabla deribit_trades_raw no se creo', file=sys.stderr)
        return 2

    print()
    print('OK migrate completo:')
    print(f'  + {len(BS76_COLUMNS)} columnas en observations')
    print(f'  + tabla deribit_trades_raw (con 2 indices)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
