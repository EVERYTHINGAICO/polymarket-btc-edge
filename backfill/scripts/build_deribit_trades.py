"""EXP2-4 — Descarga trades historicos de opciones BTC de Deribit.

Fuente: history.deribit.com (retencion profunda; www.deribit.com NO sirve, solo
~1 dia). Read-only, sin keys. Trae por trade: timestamp, instrument_name,
direction, amount, iv, index_price, price (todo lo que D necesita; delta/moneyness
se recomputan despues en build_deribit_features).

Estrategia determinista y reanudable:
  - Itera por bloques DIARIOS sobre el periodo de las ventanas.
  - Dentro de cada dia, pagina por start_timestamp creciente hasta has_more=False.
  - Guarda un JSONL por dia en data/raw/deribit/ + un .sha256 al lado.
  - Si el JSONL del dia ya existe, lo salta (reanuda).

Uso:
    py scripts/build_deribit_trades.py                 # todo el periodo
    py scripts/build_deribit_trades.py --start 2026-04-06 --end 2026-04-07  # rango
    py scripts/build_deribit_trades.py --days 1        # solo 1er dia (prueba)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import duckdb

from src.data_sources.sources_config import DERIBIT_TRADES_URL

RAW = ROOT / "data" / "raw" / "polymarket_markets_btc15m.parquet"
OUT_DIR = ROOT / "data" / "raw" / "deribit"
COUNT = 1000  # max trades por request


def fetch_block(start_ms: int, end_ms: int, retries: int = 4, timeout: int = 30) -> list[dict]:
    """Trae todos los trades en [start_ms, end_ms) paginando por timestamp."""
    trades: list[dict] = []
    cursor = start_ms
    while cursor < end_ms:
        url = (
            f"{DERIBIT_TRADES_URL}?currency=BTC&kind=option"
            f"&start_timestamp={cursor}&end_timestamp={end_ms}"
            f"&count={COUNT}&sorting=asc"
        )
        payload = None
        for attempt in range(retries):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    payload = json.load(resp)
                break
            except Exception:
                if attempt == retries - 1:
                    raise
                time.sleep(0.5 * (attempt + 1))
        res = payload.get("result", {})
        batch = res.get("trades", [])
        if not batch:
            break
        trades.extend(batch)
        last_ts = batch[-1]["timestamp"]
        if not res.get("has_more") or last_ts < cursor:
            # avanzar igual para no loopear; si no hay mas, cortar
            if not res.get("has_more"):
                break
        cursor = last_ts + 1  # siguiente pagina
        time.sleep(0.1)
    return trades


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default=None, help="YYYY-MM-DD (default: min de ventanas)")
    parser.add_argument("--end", default=None, help="YYYY-MM-DD exclusivo (default: max de ventanas)")
    parser.add_argument("--days", type=int, default=None, help="limitar a N dias desde el inicio (prueba)")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.start and args.end:
        d0 = datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc)
        d1 = datetime.fromisoformat(args.end).replace(tzinfo=timezone.utc)
    else:
        rng = duckdb.sql(f"SELECT MIN(start_ts), MAX(end_ts) FROM '{RAW.as_posix()}'").fetchone()
        d0 = datetime.fromtimestamp(rng[0], timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        d1 = datetime.fromtimestamp(rng[1], timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)

    if args.days:
        d1 = min(d1, d0 + timedelta(days=args.days))

    print(f"Periodo: {d0.date()} .. {d1.date()} | fuente: {DERIBIT_TRADES_URL}")

    day = d0
    total_trades = 0
    total_days = 0
    while day < d1:
        next_day = day + timedelta(days=1)
        out_path = OUT_DIR / f"deribit_btc_options_{day.date()}.jsonl"
        if out_path.exists():
            day = next_day
            continue
        start_ms = int(day.timestamp() * 1000)
        end_ms = int(next_day.timestamp() * 1000)
        trades = fetch_block(start_ms, end_ms)
        # ordenar determinista por (timestamp, trade_id) antes de escribir
        trades.sort(key=lambda t: (t["timestamp"], str(t.get("trade_id"))))
        lines = "\n".join(json.dumps(t, sort_keys=True) for t in trades)
        data = lines.encode("utf-8")
        out_path.write_bytes(data)
        (OUT_DIR / f"{out_path.name}.sha256").write_text(sha256_bytes(data), encoding="utf-8")
        total_trades += len(trades)
        total_days += 1
        print(f"  {day.date()}: {len(trades)} trades  sha={sha256_bytes(data)[:12]}")
        day = next_day

    print(f"\nListo. Dias nuevos: {total_days} | trades nuevos: {total_trades}")
    print(f"Salida: {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
