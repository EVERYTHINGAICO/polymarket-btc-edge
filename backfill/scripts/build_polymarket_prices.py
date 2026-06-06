"""EXP2-5 — pm_up_price_open + trayectoria intra-ventana desde Polymarket `prices`.

Regla de ventana (corregida): ts_close = end_ts, ts_open = end_ts - 900.
No-lookahead: solo se usan ticks con ts_open <= timestamp < ts_close.

Salidas:
  data/interim/pm_open.parquet        (window_id, pm_up_price_open)
  data/interim/pm_trajectory.parquet  (window_id, t_seconds, pm_up_price)  [para Gate 3]

Fuente: subset `prices` (revision FIJA). Clave del dataset = market_id;
se mapea a condition_id (=window_id) via markets.parquet. Determinista (ORDER BY).

Uso: py scripts/build_polymarket_prices.py
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import duckdb

from src.data_sources.sources_config import POLYMARKET, hf_path

WINDOWS = (ROOT / "data" / "raw" / "polymarket_markets_btc15m.parquet").as_posix()
OUT_OPEN = ROOT / "data" / "interim" / "pm_open.parquet"
OUT_TRAJ = ROOT / "data" / "interim" / "pm_trajectory.parquet"


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    OUT_OPEN.parent.mkdir(parents=True, exist_ok=True)
    prices_path = hf_path(POLYMARKET, "prices/**/*.parquet")

    con = duckdb.connect()
    # ventanas: clave condition_id, ts_close=end_ts, ts_open=end_ts-900 (segundos)
    con.execute(f"""
        CREATE VIEW win AS
        SELECT condition_id AS window_id, market_id, end_ts AS ts_close, end_ts-900 AS ts_open
        FROM '{WINDOWS}'
    """)
    # prices BTC 15m (filtrado), join por market_id, SIN lookahead
    con.execute(f"""
        CREATE VIEW px AS
        SELECT p.market_id, p.timestamp AS ts, p.up_price
        FROM '{prices_path}' p
        WHERE p.crypto='BTC' AND p.timeframe='15-minute'
    """)

    print("Calculando pm_up_price_open (primer tick >= ts_open, < ts_close)...")
    con.execute(f"""
        COPY (
          SELECT window_id, up_price AS pm_up_price_open FROM (
            SELECT w.window_id, px.up_price,
                   ROW_NUMBER() OVER (PARTITION BY w.window_id ORDER BY px.ts ASC) rn
            FROM win w JOIN px ON px.market_id = w.market_id
              AND px.ts >= w.ts_open AND px.ts < w.ts_close
          ) WHERE rn = 1
          ORDER BY window_id
        ) TO '{OUT_OPEN.as_posix()}' (FORMAT PARQUET)
    """)

    print("Calculando trayectoria intra-ventana (t_seconds desde ts_open)...")
    con.execute(f"""
        COPY (
          SELECT w.window_id, CAST(px.ts - w.ts_open AS INTEGER) AS t_seconds, px.up_price AS pm_up_price
          FROM win w JOIN px ON px.market_id = w.market_id
            AND px.ts >= w.ts_open AND px.ts < w.ts_close
          ORDER BY w.window_id, t_seconds
        ) TO '{OUT_TRAJ.as_posix()}' (FORMAT PARQUET)
    """)

    n_open = con.execute(f"SELECT COUNT(*) FROM '{OUT_OPEN.as_posix()}'").fetchone()[0]
    n_traj = con.execute(f"SELECT COUNT(*) FROM '{OUT_TRAJ.as_posix()}'").fetchone()[0]
    n_win_traj = con.execute(f"SELECT COUNT(DISTINCT window_id) FROM '{OUT_TRAJ.as_posix()}'").fetchone()[0]

    print(f"\npm_open:       {n_open:,} ventanas con pm_up_price_open  | sha={file_sha256(OUT_OPEN)[:12]}")
    print(f"pm_trajectory: {n_traj:,} ticks en {n_win_traj:,} ventanas | sha={file_sha256(OUT_TRAJ)[:12]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
