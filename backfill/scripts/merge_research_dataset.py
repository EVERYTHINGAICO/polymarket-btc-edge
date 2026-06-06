"""EXP2-5 — Merge final: research_dataset_v1.parquet (1 fila por ventana).

Une todas las piezas por window_id (=condition_id):
  - deribit_features (D/V/n)            [build_deribit_features]
  - outcomes (Up/Down autoridad CLOB)   [build_outcomes]
  - pm_open (pm_up_price_open)          [build_polymarket_prices]
  - chainlink_refs (price_to_beat, chainlink_close)  [build_chainlink_refs]
  - deribit_index_open/close            (del index_price de los trades, aquí)

Regla ventana: ts_close=end_ts, ts_open=end_ts-900. SIN lookahead (todas las
piezas ya respetan timestamp < ts_close). NO aplica filtros de gate (eso es del
config en data.py). Determinista: ORDER BY window_id + hash.

Salida: data/processed/research_dataset_v1.parquet

Uso: py scripts/merge_research_dataset.py
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import duckdb

WINDOWS = (ROOT / "data" / "raw" / "polymarket_markets_btc15m.parquet").as_posix()
FEAT = (ROOT / "data" / "interim" / "deribit_features.parquet").as_posix()
OUTC = (ROOT / "data" / "interim" / "outcomes.parquet").as_posix()
PMOPEN = (ROOT / "data" / "interim" / "pm_open.parquet").as_posix()
CLREFS = (ROOT / "data" / "interim" / "chainlink_refs.parquet")
DERIBIT = (ROOT / "data" / "raw" / "deribit" / "*.jsonl").as_posix()
OUT = ROOT / "data" / "processed" / "research_dataset_v1.parquet"


def file_sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()

    # deribit_index_open/close: primer/último index_price dentro de la ventana
    con.execute(f"""
        CREATE VIEW idx AS
        WITH w AS (SELECT condition_id wid, (end_ts-900)*1000 o, end_ts*1000 c FROM '{WINDOWS}'),
        tr AS (SELECT timestamp ts, index_price FROM read_json_auto('{DERIBIT}',
               format='newline_delimited', columns={{'timestamp':'BIGINT','index_price':'DOUBLE'}}, ignore_errors=true))
        SELECT w.wid AS window_id,
               first(tr.index_price ORDER BY tr.ts ASC) AS deribit_index_open,
               last(tr.index_price ORDER BY tr.ts ASC) AS deribit_index_close
        FROM w JOIN tr ON tr.ts>=w.o AND tr.ts<w.c GROUP BY w.wid
    """)

    has_chainlink = CLREFS.exists()
    cl_join = f"LEFT JOIN '{CLREFS.as_posix()}' cl ON f.window_id=cl.window_id" if has_chainlink else ""
    cl_cols = "cl.price_to_beat, cl.chainlink_close," if has_chainlink else "CAST(NULL AS DOUBLE) price_to_beat, CAST(NULL AS DOUBLE) chainlink_close,"

    con.execute(f"""
        COPY (
          SELECT
            f.window_id,
            to_timestamp(w.end_ts-900) AS ts_open,
            to_timestamp(w.end_ts)     AS ts_close,
            {cl_cols}
            pm.pm_up_price_open,
            idx.deribit_index_open,
            idx.deribit_index_close,
            f.D_5m_otm_dotm, f.D_10m_otm_dotm, f.D_15m_otm_dotm,
            f.D_5m_atm, f.D_10m_atm, f.D_15m_atm,
            f.V_5m_otm_dotm, f.V_10m_otm_dotm, f.V_15m_otm_dotm,
            f.n_trades_5m, f.n_trades_10m, f.n_trades_15m,
            o.outcome
          FROM '{FEAT}' f
          JOIN '{OUTC}' o ON f.window_id=o.condition_id
          LEFT JOIN '{PMOPEN}' pm ON f.window_id=pm.window_id
          LEFT JOIN idx ON f.window_id=idx.window_id
          LEFT JOIN '{WINDOWS}' w ON f.window_id=w.condition_id
          {cl_join}
          ORDER BY f.window_id
        ) TO '{OUT.as_posix()}' (FORMAT PARQUET)
    """)

    n = con.execute(f"SELECT COUNT(*) FROM '{OUT.as_posix()}'").fetchone()[0]
    complete = con.execute(f"""
        SELECT COUNT(*) FROM '{OUT.as_posix()}'
        WHERE outcome IS NOT NULL AND pm_up_price_open IS NOT NULL
          AND deribit_index_open IS NOT NULL AND D_15m_otm_dotm IS NOT NULL
          {'AND price_to_beat IS NOT NULL AND chainlink_close IS NOT NULL' if has_chainlink else ''}
    """).fetchone()[0]

    print(f"Guardado: {OUT}")
    print(f"chainlink incluido: {has_chainlink}")
    print(f"ventanas: {n:,} | completas (todas las cols clave no-nulas): {complete:,}")
    print(f"file_sha256: {file_sha256(OUT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
