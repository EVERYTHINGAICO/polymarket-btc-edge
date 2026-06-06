"""EXP2-4 — Descarga la tabla maestra de ventanas BTC 15m (Polymarket).

Baja el subset `markets` filtrado a BTC / 15-minute, FIJADO a la revision
congelada en sources_config (reproducibilidad). Lo guarda en data/raw/ como
parquet + imprime SHA256. Ordenado por start_ts (determinista).

NO decide el outcome aquí (eso es CLOB, paso aparte). Solo trae la estructura
de ventanas: window_id, ts_open, ts_close, condition_id, strike implícito, etc.

Uso:
    py scripts/build_windows.py
"""

from __future__ import annotations

import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import duckdb

from src.data_sources.sources_config import CRYPTO, POLYMARKET, TIMEFRAME, hf_path

RAW_DIR = ROOT / "data" / "raw"
OUT_PATH = RAW_DIR / "polymarket_markets_btc15m.parquet"


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    markets_path = hf_path(POLYMARKET, "markets.parquet")

    print(f"Fuente: {POLYMARKET.repo_id}@{POLYMARKET.revision[:12]} ({POLYMARKET.revision_date_utc})")
    print(f"Filtro: crypto={CRYPTO} timeframe={TIMEFRAME}")

    # Determinista: ORDER BY start_ts, window_id. COPY a parquet local.
    query = f"""
    COPY (
        SELECT
            slug,
            market_id,
            condition_id,
            crypto,
            timeframe,
            start_ts,
            end_ts,
            closed_ts,
            resolution,
            up_token_id,
            down_token_id,
            fee_rate_bps,
            question
        FROM '{markets_path}'
        WHERE crypto = '{CRYPTO}' AND timeframe = '{TIMEFRAME}'
        ORDER BY start_ts, market_id
    ) TO '{OUT_PATH.as_posix()}' (FORMAT PARQUET);
    """
    duckdb.sql(query)

    # Verificación + stats
    n = duckdb.sql(f"SELECT COUNT(*) FROM '{OUT_PATH.as_posix()}'").fetchone()[0]
    rng = duckdb.sql(
        f"SELECT MIN(start_ts), MAX(start_ts) FROM '{OUT_PATH.as_posix()}'"
    ).fetchone()
    res = duckdb.sql(
        f"SELECT resolution, COUNT(*) FROM '{OUT_PATH.as_posix()}' GROUP BY resolution ORDER BY resolution"
    ).fetchall()

    print(f"\nGuardado: {OUT_PATH}")
    print(f"Ventanas BTC 15m: {n}")
    print(f"start_ts rango: {rng[0]} .. {rng[1]} "
          f"({datetime.fromtimestamp(rng[0], timezone.utc).date()} .. "
          f"{datetime.fromtimestamp(rng[1], timezone.utc).date()})")
    print(f"resolution: {dict(res)}  (-1=unknown via dataset; se recupera via CLOB en build_outcomes)")
    print(f"file_sha256: {file_sha256(OUT_PATH)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
