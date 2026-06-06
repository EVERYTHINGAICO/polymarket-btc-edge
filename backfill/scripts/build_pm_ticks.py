"""ETAPA 1A — Descarga ticks (trades reales) de Polymarket BTC 15m.

Un solo escaneo DuckDB sobre HF (revision fija). Filtra:
  - crypto=BTC, timeframe=15-minute
  - timestamp_ms valido (descarta basura con ts<dic-2025)
  - price en (0,1) (un trade valido cotiza dentro del rango)
Guarda data/raw/pm_ticks.parquet (ordenado, determinista) + hash.

COBERTURA REAL (verificada 2026-06-03): el subset ticks BTC 15m solo
existe para 2026-03 y 2026-04 (~20.5M filas, ~3.800 markets). NO hay
dic-2025..feb-2026 (eso venia de otro subset, prices/trayectoria).

spot_price_usdt: presente casi 100% en abril (4.8M) pero solo ~1.4%
en marzo. NO se filtra por spot (eso tiraba 15.4M ticks de marzo que
son order flow valido: side/size/precio del contrato). spot queda
nullable; se usa donde exista (abril = momentum fino).

Cada tick: trade real del contrato (precio EJECUTABLE, lado, tamaño) +
spot BTC en ms cuando disponible. Base del analisis fino de microestructura.

Uso: py scripts/build_pm_ticks.py
"""

from __future__ import annotations

import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import duckdb

from src.data_sources.sources_config import POLYMARKET, hf_path

OUT = ROOT / "data" / "raw" / "pm_ticks.parquet"
# inicio real del periodo (dic 2025); descarta timestamps basura (1970, etc.)
MIN_TS_MS = int(datetime(2025, 12, 1, tzinfo=timezone.utc).timestamp() * 1000)


def file_sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    ticks_path = hf_path(POLYMARKET, "ticks/**/*.parquet")
    print(f"Fuente: {POLYMARKET.repo_id}@{POLYMARKET.revision[:12]}")
    print(f"Filtro: BTC / 15-minute / ts>={MIN_TS_MS} / price in (0,1). spot NULLABLE.")
    print("Escaneando ticks (1 pasada)...")

    duckdb.sql(f"""
        COPY (
            SELECT timestamp_ms, market_id, token_id, outcome, side, price,
                   size_usdc, spot_price_usdt, spot_price_ts_ms, source
            FROM '{ticks_path}'
            WHERE crypto = 'BTC' AND timeframe = '15-minute'
              AND timestamp_ms >= {MIN_TS_MS}
              AND price > 0 AND price < 1
            ORDER BY market_id, timestamp_ms
        ) TO '{OUT.as_posix()}' (FORMAT PARQUET)
    """)

    rng = duckdb.sql(f"""
        SELECT COUNT(*) n, MIN(timestamp_ms) lo, MAX(timestamp_ms) hi,
               COUNT(DISTINCT market_id) mk,
               SUM(CASE WHEN spot_price_usdt > 0 THEN 1 ELSE 0 END) con_spot
        FROM '{OUT.as_posix()}'
    """).fetchone()
    print(f"\nGuardado: {OUT}")
    print(f"  ticks: {rng[0]:,}")
    print(f"  periodo: {datetime.fromtimestamp(rng[1]/1000,timezone.utc).date()} .. {datetime.fromtimestamp(rng[2]/1000,timezone.utc).date()}")
    print(f"  markets: {rng[3]:,}")
    print(f"  con spot>0: {rng[4]:,} ({100*rng[4]/rng[0]:.1f}%)  [resto: order flow sin spot, util igual]")
    print(f"  tamaño: {OUT.stat().st_size/1e6:.1f} MB")
    print(f"  file_sha256: {file_sha256(OUT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
