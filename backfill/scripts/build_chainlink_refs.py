"""EXP2-5 — Precios de referencia Chainlink para Gate 4a (price_to_beat, chainlink_close).

Oráculo Chainlink BTC/USD en Polygon (0xc907E116054Ad103354f2D350FD2514433D57F6f, mismo Exp1).
Para cada ventana: round vigente en ts_open (price_to_beat) y ts_close (chainlink_close).

Algoritmo (AUDITORIA_DATOS_vs_PLAN 2c): BÚSQUEDA BINARIA PURA, sin estado —
round vigente = último con updatedAt <= T (no-lookahead). updatedAt monótono con roundId.

Optimización (decisión de caso): BATCH JSON-RPC — las búsquedas binarias de TODAS las
ventanas avanzan "en lockstep"; en cada nivel se agrupan las lecturas pendientes en un
solo POST HTTP. Sin concurrencia (secuencial, auditable). Resultado bit-idéntico a la
versión 1xRPC. Caché compartida de rounds (reanudable).

Robustez (Exp1): User-Agent Mozilla + RPCs fallback.

Salida: data/interim/chainlink_refs.parquet + chainlink_round_cache.jsonl
Uso: py scripts/build_chainlink_refs.py [--limit N]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import duckdb

WINDOWS = (ROOT / "data" / "raw" / "polymarket_markets_btc15m.parquet").as_posix()
OUT = ROOT / "data" / "interim" / "chainlink_refs.parquet"
CACHE = ROOT / "data" / "interim" / "chainlink_round_cache.jsonl"

AGG = "0xc907E116054Ad103354f2D350FD2514433D57F6f"
RPCS = ["https://polygon-bor-rpc.publicnode.com", "https://polygon.drpc.org", "https://1rpc.io/matic"]
SEL_LATEST = "0xfeaf968c"
SEL_GETROUND = "0x9a6fc8f5"


class Chainlink:
    def __init__(self) -> None:
        self.cache: dict[int, tuple[float, int] | None] = {}
        self.calls = 0
        self._load_cache()
        cur = int(self._batch([("latest", SEL_LATEST)])["latest"][2:][:64], 16)
        self.phase = cur >> 64
        self.agg_max = cur & ((1 << 64) - 1)

    def _load_cache(self) -> None:
        if CACHE.exists():
            for line in open(CACHE, encoding="utf-8"):
                try:
                    r = json.loads(line)
                    self.cache[int(r["agg"])] = (r["price"], r["updatedAt"])
                except Exception:
                    pass

    def _post(self, batch: list[dict]) -> list:
        payload = json.dumps(batch).encode()
        last = None
        for rpc in RPCS:
            for attempt in range(3):
                try:
                    req = urllib.request.Request(rpc, data=payload,
                        headers={"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"})
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        out = json.load(resp)
                    return out if isinstance(out, list) else [out]
                except Exception as e:
                    last = e; time.sleep(0.4 * (attempt + 1))
        raise RuntimeError(f"RPC fail: {last}")

    def _batch(self, items: list[tuple]) -> dict:
        """items = [(key, dataHex)]. Devuelve {key: resultHex}."""
        reqs = [{"jsonrpc": "2.0", "id": k, "method": "eth_call",
                 "params": [{"to": AGG, "data": d}, "latest"]} for k, d in items]
        resp = self._post(reqs)
        by_id = {o.get("id"): o.get("result", "") for o in resp}
        return {k: by_id.get(k, "") for k, _ in items}

    def _decode(self, res: str) -> tuple[float, int] | None:
        body = res[2:] if res.startswith("0x") else res
        if len(body) < 64 * 4:
            return None
        w = [body[i:i+64] for i in range(0, len(body), 64)]
        price = int(w[1], 16) / 1e8
        updated = int(w[3], 16)
        return (price, updated) if price > 0 and updated > 0 else None

    def fetch_rounds(self, agg_ids: list[int]) -> None:
        """Trae en batch los agg_ids que no estén en caché; los guarda."""
        pending = [a for a in set(agg_ids) if a not in self.cache and 1 <= a <= self.agg_max]
        if not pending:
            return
        CHUNK = 200
        for s in range(0, len(pending), CHUNK):
            chunk = pending[s:s+CHUNK]
            items = [(a, SEL_GETROUND + hex((self.phase << 64) | a)[2:].zfill(64)) for a in chunk]
            results = self._batch(items)
            self.calls += len(chunk)
            with open(CACHE, "a", encoding="utf-8") as f:
                for a in chunk:
                    dec = self._decode(results.get(a, ""))
                    self.cache[a] = dec
                    if dec is not None:
                        f.write(json.dumps({"agg": a, "price": dec[0], "updatedAt": dec[1]}) + "\n")

    def round_at_many(self, targets: list[int]) -> list[tuple[float, int] | None]:
        """Búsqueda binaria en lockstep para muchos targets a la vez (batch por nivel)."""
        lo = [1] * len(targets)
        hi = [self.agg_max] * len(targets)
        active = list(range(len(targets)))
        while active:
            mids = {i: (lo[i] + hi[i] + 1) // 2 for i in active}
            self.fetch_rounds(list(mids.values()))
            still = []
            for i in active:
                r = self.cache.get(mids[i])
                if r is None:
                    hi[i] = mids[i] - 1
                elif r[1] <= targets[i]:
                    lo[i] = mids[i]
                else:
                    hi[i] = mids[i] - 1
                if lo[i] < hi[i]:
                    still.append(i)
            active = still
        # resolver final
        self.fetch_rounds([lo[i] for i in range(len(targets))])
        out = []
        for i in range(len(targets)):
            r = self.cache.get(lo[i])
            out.append(r if (r is not None and r[1] <= targets[i]) else None)
        return out


def file_sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    OUT.parent.mkdir(parents=True, exist_ok=True)

    wins = duckdb.sql(
        f"SELECT condition_id AS window_id, end_ts AS ts_close, end_ts-900 AS ts_open "
        f"FROM '{WINDOWS}' ORDER BY end_ts, condition_id"
    ).df()
    if args.limit:
        wins = wins.head(args.limit)

    cl = Chainlink()
    print(f"phase={cl.phase} agg_max={cl.agg_max:,} | ventanas={len(wins):,} | cache inicial={len(cl.cache):,}")

    ts_open = wins["ts_open"].astype(int).tolist()
    ts_close = wins["ts_close"].astype(int).tolist()
    print("Resolviendo price_to_beat (ts_open)...")
    ro = cl.round_at_many(ts_open)
    print("Resolviendo chainlink_close (ts_close)...")
    rc = cl.round_at_many(ts_close)

    import pandas as pd
    df = pd.DataFrame({
        "window_id": wins["window_id"].values,
        "price_to_beat": [r[0] if r else None for r in ro],
        "chainlink_close": [r[0] if r else None for r in rc],
        "updatedAt_open": [r[1] if r else None for r in ro],
        "updatedAt_close": [r[1] if r else None for r in rc],
        "ts_open": ts_open, "ts_close": ts_close,
    }).sort_values("window_id").reset_index(drop=True)
    df.to_parquet(OUT, index=False)

    ok_o = (df["updatedAt_open"].fillna(-1) <= df["ts_open"]).all()
    ok_c = (df["updatedAt_close"].fillna(-1) <= df["ts_close"]).all()
    print(f"\nGuardado: {OUT} | RPC calls: {cl.calls}")
    print(f"price_to_beat: {df['price_to_beat'].notna().sum():,}/{len(df):,} | chainlink_close: {df['chainlink_close'].notna().sum():,}/{len(df):,}")
    print(f"NO-LOOKAHEAD open:{'OK' if ok_o else 'FALLA'} close:{'OK' if ok_c else 'FALLA'}")
    print(f"price_to_beat rango: {df['price_to_beat'].min():.0f}..{df['price_to_beat'].max():.0f}")
    print(f"file_sha256: {file_sha256(OUT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
