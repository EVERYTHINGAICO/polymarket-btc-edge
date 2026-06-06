"""EXP2-6 — Carga research_dataset_v1 + trayectoria a observations_exp2.db.

Mapea a las 25 columnas EXACTAS de Exp1 (para que src/analysis/data.py funcione
sin cambios). NO descarta filas: marca is_incomplete/insufficient_flow; los
filtros de gate los aplica el config vía data.py.

  - observations: 1 fila por ventana (las 25 columnas de Exp1).
  - observations_intrawindow: trayectoria (window_id, t_seconds, pm_up_price).
  - backfill_provenance: origen + outcome_source por ventana.

Idempotente: recrea la DB desde cero (init_db) y vuelve a cargar. Determinista.

Uso: py scripts/load_to_db.py
"""

from __future__ import annotations

import hashlib
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import duckdb

from scripts.init_db import init_db

DB = ROOT / "data" / "observations_exp2.db"
DATASET = (ROOT / "data" / "processed" / "research_dataset_v1.parquet").as_posix()
TRAJ = (ROOT / "data" / "interim" / "pm_trajectory.parquet").as_posix()
OUTCOMES = (ROOT / "data" / "interim" / "outcomes.parquet").as_posix()
REV = "ba1ad37cbcdd720cced20f1cdc97c2cf347cad6c"


def db_sha256() -> str:
    return hashlib.sha256(DB.read_bytes()).hexdigest()


def main() -> int:
    # recrear DB limpia (idempotente)
    if DB.exists():
        DB.unlink()
    init_db(DB)

    df = duckdb.sql(f"SELECT * FROM '{DATASET}'").df()
    # ISO UTC para ts_open/ts_close (vienen como timestamp de duckdb)
    import pandas as pd
    df["ts_open"] = pd.to_datetime(df["ts_open"], utc=True).dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    df["ts_close"] = pd.to_datetime(df["ts_close"], utc=True).dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    # flags
    df["is_incomplete"] = df["outcome"].isna().astype(int)
    df["insufficient_flow"] = (df["n_trades_15m"] < 1).astype(int)
    df["pm_up_price_close"] = None  # no se usa en gates; informativo
    df["notes"] = "exp2_backfill"

    cols_25 = [
        "window_id", "ts_open", "price_to_beat", "pm_up_price_open", "deribit_index_open",
        "D_5m_otm_dotm", "D_10m_otm_dotm", "D_15m_otm_dotm",
        "D_5m_atm", "D_10m_atm", "D_15m_atm",
        "V_5m_otm_dotm", "V_10m_otm_dotm", "V_15m_otm_dotm",
        "n_trades_5m", "n_trades_10m", "n_trades_15m",
        "ts_close", "deribit_index_close", "chainlink_close", "outcome",
        "pm_up_price_close", "is_incomplete", "insufficient_flow", "notes",
    ]

    conn = sqlite3.connect(DB)
    try:
        conn.executemany(
            f"INSERT INTO observations ({','.join(cols_25)}) VALUES ({','.join(['?']*25)})",
            df[cols_25].itertuples(index=False, name=None),
        )
        # trayectoria
        traj = duckdb.sql(f"SELECT window_id, t_seconds, pm_up_price FROM '{TRAJ}' ORDER BY window_id, t_seconds").df()
        conn.executemany(
            "INSERT OR REPLACE INTO observations_intrawindow (window_id, t_seconds, pm_up_price) VALUES (?,?,?)",
            traj.itertuples(index=False, name=None),
        )
        # provenance (outcome_source = clob_winner para todas)
        prov = duckdb.sql(f"SELECT condition_id, outcome_source FROM '{OUTCOMES}'").df()
        conn.executemany(
            "INSERT OR REPLACE INTO backfill_provenance (window_id, source_dataset, source_revision, outcome_source) VALUES (?,?,?,?)",
            [(r.condition_id, "aliplayer1/polymarket-crypto-updown", REV, r.outcome_source) for r in prov.itertuples()],
        )
        conn.commit()
    finally:
        conn.close()

    # verificación con el loader REAL de Exp1
    sys.path.insert(0, str(ROOT))
    from src.analysis.config import load_config
    from src.analysis.data import load_data
    cfg = load_config(str(ROOT / "analysis_config.json"))
    data = load_data(cfg, db_path_override=str(DB))

    print(f"DB poblada: {DB}")
    print(f"  observations: {len(df):,} filas")
    print(f"  intrawindow:  {len(traj):,} ticks")
    print(f"  data.py n_total_complete: {data.n_total_complete:,}")
    print(f"  data.py n_after_filter (outcome+is_incomplete=0+n>=30): {data.n_after_filter:,}  (umbral 1000)")
    print(f"  input_hash: {data.input_hash}")
    print(f"  db_sha256:  {db_sha256()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
