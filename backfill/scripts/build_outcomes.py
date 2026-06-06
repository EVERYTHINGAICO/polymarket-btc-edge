"""EXP2-4 — Outcome AUTORIDAD via Polymarket CLOB API (por condition_id).

Regla dura (decidida con Pedro): el outcome NO se deriva del ultimo precio
(last-tick flips ~6% en Exp1, sesgo en ventanas apretadas). La autoridad es la
resolucion oficial del oraculo, expuesta por CLOB como tokens[].winner.

Lee data/raw/polymarket_markets_btc15m.parquet, consulta CLOB por cada
condition_id, y escribe data/interim/outcomes.parquet con:
    window_id (slug), condition_id, outcome ('Up'|'Down'|None), closed,
    outcome_source ('clob_winner'), resolved (bool)

Robusto: cache en disco (JSONL) para reanudar sin re-consultar; reintentos;
read-only; sin keys. Determinista en el resultado (mismo condition_id -> mismo
outcome; el orden de escritura final se ordena por window_id).

Uso:
    py scripts/build_outcomes.py            # procesa todo (reanuda desde cache)
    py scripts/build_outcomes.py --limit 50 # prueba
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import duckdb

from src.data_sources.sources_config import POLYMARKET_CLOB_MARKET_URL

RAW = ROOT / "data" / "raw" / "polymarket_markets_btc15m.parquet"
CACHE = ROOT / "data" / "interim" / "clob_cache.jsonl"
OUT = ROOT / "data" / "interim" / "outcomes.parquet"


def fetch_clob(condition_id: str, retries: int = 3, timeout: int = 15) -> dict | None:
    url = POLYMARKET_CLOB_MARKET_URL.format(condition_id=condition_id)
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.load(resp)
        except Exception:
            if attempt == retries - 1:
                return None
            time.sleep(0.5 * (attempt + 1))
    return None


def parse_outcome(payload: dict | None) -> tuple[str | None, bool]:
    """Devuelve (outcome, closed). outcome = 'Up'/'Down' solo si hay winner claro."""
    if not payload:
        return None, False
    closed = bool(payload.get("closed"))
    winners = [t.get("outcome") for t in payload.get("tokens", []) if t.get("winner")]
    if len(winners) == 1 and winners[0] in ("Up", "Down"):
        return winners[0], closed
    return None, closed


def load_cache() -> dict[str, dict]:
    cache: dict[str, dict] = {}
    if CACHE.exists():
        with open(CACHE, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                    cache[rec["condition_id"]] = rec
                except Exception:
                    continue
    return cache


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--sleep", type=float, default=0.15, help="pausa entre requests (rate limit)")
    args = parser.parse_args()

    CACHE.parent.mkdir(parents=True, exist_ok=True)

    rows = duckdb.sql(
        f"SELECT slug, condition_id FROM '{RAW.as_posix()}' "
        f"WHERE condition_id IS NOT NULL ORDER BY start_ts, market_id"
    ).fetchall()
    if args.limit:
        rows = rows[: args.limit]

    cache = load_cache()
    total = len(rows)
    done = 0
    fetched = 0
    print(f"Ventanas a resolver: {total} | en cache: {len(cache)}")

    with open(CACHE, "a", encoding="utf-8") as cf:
        for slug, cid in rows:
            done += 1
            if cid in cache:
                continue
            payload = fetch_clob(cid)
            outcome, closed = parse_outcome(payload)
            rec = {
                "condition_id": cid,
                "slug": slug,
                "outcome": outcome,
                "closed": closed,
                "outcome_source": "clob_winner",
            }
            cache[cid] = rec
            cf.write(json.dumps(rec) + "\n")
            cf.flush()
            fetched += 1
            if fetched % 100 == 0:
                resolved = sum(1 for r in cache.values() if r.get("outcome"))
                print(f"  {done}/{total} procesadas | {fetched} nuevas | {resolved} resueltas")
            time.sleep(args.sleep)

    # Escribir parquet final ordenado por slug (determinista)
    recs = [cache[cid] for _, cid in rows if cid in cache]
    import pandas as pd
    df = pd.DataFrame(recs).sort_values("slug").reset_index(drop=True)
    df.to_parquet(OUT, index=False)

    resolved = int(df["outcome"].notna().sum())
    print(f"\nGuardado: {OUT}")
    print(f"Total: {len(df)} | resueltas (Up/Down): {resolved} | sin resolver: {len(df) - resolved}")
    print(f"distribucion: {df['outcome'].value_counts(dropna=False).to_dict()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
