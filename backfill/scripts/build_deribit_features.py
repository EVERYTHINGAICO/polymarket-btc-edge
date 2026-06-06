"""EXP2-5 — Construye la señal D por ventana de 15 min desde los trades Deribit.

Replica src/signal.py de Exp1:
  signed_pressure = sign(direction) * amount * delta_abs   (+1 buyer, -1 seller)
  por bucket de moneyness (otm_dotm / atm) y tipo (call/put):
    A_C = Σ signed_pressure calls ; A_P = Σ signed_pressure puts
    D = (A_C - A_P)/2 ;  V = (A_C + A_P)/2
  variantes: ventana {5,10,15}m x bucket {otm_dotm, atm}

Convenciones CONGELADAS (ver docs/AUDITORIA_PROTOCOLO.md):
  - delta: recomputado Black-76 (histórico no trae delta).
      d1=(ln(F/K)+0.5 sig^2 T)/(sig sqrt(T)); call delta=N(d1), put=N(d1)-1
      F=index_price, K=strike (del instrument_name), T=ACT/365, sig=iv/100, r=0
  - moneyness por |delta| (cortes Exp1):
      DOTM (0.02,0.125] · OTM (0.125,0.375] · ATM (0.375,0.625] · resto IGNORED
  - IV inválida: descartar trade si iv<=0 o iv>300 (<0.5%, corrupto)
  - ventana PREDICTIVA: para una window [ts_open, ts_close), los trades de la
    variante Xm son los de [ts_open - X*60, ts_open). Nunca usar trades con
    timestamp >= ts_open para construir D.

Determinista. Lee data/raw/deribit/*.jsonl + data/raw/polymarket_markets_btc15m.parquet.
Escribe data/interim/deribit_features.parquet (1 fila por ventana) + hash.

Uso:
    py scripts/build_deribit_features.py
"""

from __future__ import annotations

import hashlib
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import duckdb
import pandas as pd

RAW_TRADES = (ROOT / "data" / "raw" / "deribit").as_posix()
WINDOWS = (ROOT / "data" / "raw" / "polymarket_markets_btc15m.parquet").as_posix()
OUT = ROOT / "data" / "interim" / "deribit_features.parquet"

IV_MAX = 300.0  # % — congelado
MONTHS = {"JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
          "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12}


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def black76_delta(F: float, K: float, T: float, sigma: float, is_call: bool) -> float | None:
    """Delta Black-76 sobre forward. sigma en decimal (iv/100). r=0."""
    if sigma <= 0 or T <= 0 or F <= 0 or K <= 0:
        return None
    d1 = (math.log(F / K) + 0.5 * sigma * sigma * T) / (sigma * math.sqrt(T))
    delta = _norm_cdf(d1) if is_call else _norm_cdf(d1) - 1.0
    return round(delta, 6)


def expiry_ts(exp_code: str) -> float | None:
    m = re.match(r"(\d+)([A-Z]{3})(\d{2})", exp_code)
    if not m:
        return None
    day, mon, yr = int(m.group(1)), MONTHS[m.group(2)], 2000 + int(m.group(3))
    return datetime(yr, mon, day, 8, 0, 0, tzinfo=timezone.utc).timestamp()


def moneyness_bucket(delta_abs: float) -> str | None:
    if 0.02 < delta_abs <= 0.125:
        return "otm_dotm"  # DOTM
    if 0.125 < delta_abs <= 0.375:
        return "otm_dotm"  # OTM
    if 0.375 < delta_abs <= 0.625:
        return "atm"
    return None  # IGNORED (deep-OTM ruido o ITM)


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)

    # 1) cargar ventanas (clave=condition_id; ts_close=end_ts; ts_open=end_ts-900)
    win = duckdb.sql(
        f"SELECT condition_id, end_ts-900 AS ts_open_s, end_ts AS ts_close_s FROM '{WINDOWS}'"
    ).df()

    # 2) cargar todos los trades de opciones (solo campos necesarios), via DuckDB
    print("Cargando trades Deribit...")
    trades = duckdb.sql(f"""
        SELECT timestamp AS ts, instrument_name, direction, amount, iv, index_price
        FROM read_json_auto('{RAW_TRADES}/*.jsonl', format='newline_delimited',
            columns={{'timestamp':'BIGINT','instrument_name':'VARCHAR','direction':'VARCHAR',
                      'amount':'DOUBLE','iv':'DOUBLE','index_price':'DOUBLE'}}, ignore_errors=true)
        WHERE iv > 0 AND iv <= {IV_MAX}
    """).df()
    print(f"  trades con IV válida: {len(trades):,}")

    # 3) parsear instrument + recomputar delta + bucket (vectorizado-ish)
    parts = trades["instrument_name"].str.split("-", expand=True)
    trades["K"] = pd.to_numeric(parts[2], errors="coerce")
    trades["is_call"] = parts[3] == "C"
    trades["exp_ts"] = parts[1].map(lambda s: expiry_ts(s) if isinstance(s, str) else None)
    trades = trades.dropna(subset=["K", "exp_ts"])

    sec_per_year = 365 * 86400
    deltas, buckets = [], []
    for ts, F, K, iv, isc, ex in zip(
        trades["ts"], trades["index_price"], trades["K"], trades["iv"], trades["is_call"], trades["exp_ts"]
    ):
        T = (ex - ts / 1000.0) / sec_per_year
        d = black76_delta(F, K, T, iv / 100.0, bool(isc))
        if d is None:
            deltas.append(None); buckets.append(None); continue
        deltas.append(abs(d))
        buckets.append(moneyness_bucket(abs(d)))
    trades["delta_abs"] = deltas
    trades["bucket"] = buckets
    trades["sign"] = trades["direction"].map({"buy": 1.0, "sell": -1.0})
    trades["is_call_f"] = trades["is_call"].astype(float)
    trades = trades.dropna(subset=["bucket", "delta_abs", "sign"])
    trades["signed_pressure"] = trades["sign"] * trades["amount"] * trades["delta_abs"]
    print(f"  trades clasificados (bucket válido): {len(trades):,}")

    # 4) por ventana y variante temporal, agregar D/V/n
    # Regla anti-lookahead: D se calcula con trades ANTES de ts_open.
    # Para la ventana de resultado [ts_open, ts_close), usamos:
    #   15m: [ts_open-900, ts_open)
    #   10m: [ts_open-600, ts_open)
    #    5m: [ts_open-300, ts_open)
    con = duckdb.connect()
    con.register("tr", trades[["ts", "bucket", "is_call", "signed_pressure"]])
    con.register("w", win[["condition_id", "ts_open_s", "ts_close_s"]])

    rows = con.execute("""
        WITH x AS (
          SELECT w.condition_id, w.ts_open_s, w.ts_close_s,
                 (w.ts_open_s*1000 - tr.ts)/60000.0 AS mins_before_open,
                 tr.bucket, tr.is_call, tr.signed_pressure
          FROM w JOIN tr
            ON tr.ts >= (w.ts_open_s-900)*1000 AND tr.ts < w.ts_open_s*1000
        )
        SELECT condition_id,
          -- 15m
          SUM(CASE WHEN bucket='otm_dotm' AND is_call THEN signed_pressure ELSE 0 END) AS ac_od_15,
          SUM(CASE WHEN bucket='otm_dotm' AND NOT is_call THEN signed_pressure ELSE 0 END) AS ap_od_15,
          SUM(CASE WHEN bucket='atm' AND is_call THEN signed_pressure ELSE 0 END) AS ac_atm_15,
          SUM(CASE WHEN bucket='atm' AND NOT is_call THEN signed_pressure ELSE 0 END) AS ap_atm_15,
          COUNT(*) AS n15,
          -- 10m
          SUM(CASE WHEN mins_before_open<=10 AND bucket='otm_dotm' AND is_call THEN signed_pressure ELSE 0 END) AS ac_od_10,
          SUM(CASE WHEN mins_before_open<=10 AND bucket='otm_dotm' AND NOT is_call THEN signed_pressure ELSE 0 END) AS ap_od_10,
          SUM(CASE WHEN mins_before_open<=10 AND bucket='atm' AND is_call THEN signed_pressure ELSE 0 END) AS ac_atm_10,
          SUM(CASE WHEN mins_before_open<=10 AND bucket='atm' AND NOT is_call THEN signed_pressure ELSE 0 END) AS ap_atm_10,
          SUM(CASE WHEN mins_before_open<=10 THEN 1 ELSE 0 END) AS n10,
          -- 5m
          SUM(CASE WHEN mins_before_open<=5 AND bucket='otm_dotm' AND is_call THEN signed_pressure ELSE 0 END) AS ac_od_5,
          SUM(CASE WHEN mins_before_open<=5 AND bucket='otm_dotm' AND NOT is_call THEN signed_pressure ELSE 0 END) AS ap_od_5,
          SUM(CASE WHEN mins_before_open<=5 AND bucket='atm' AND is_call THEN signed_pressure ELSE 0 END) AS ac_atm_5,
          SUM(CASE WHEN mins_before_open<=5 AND bucket='atm' AND NOT is_call THEN signed_pressure ELSE 0 END) AS ap_atm_5,
          SUM(CASE WHEN mins_before_open<=5 THEN 1 ELSE 0 END) AS n5
        FROM x GROUP BY condition_id, ts_open_s, ts_close_s
    """).df()

    def D(ac, ap): return (rows[ac] - rows[ap]) / 2.0
    def V(ac, ap): return (rows[ac] + rows[ap]) / 2.0
    out = pd.DataFrame({"window_id": rows["condition_id"]})
    out["D_15m_otm_dotm"] = D("ac_od_15", "ap_od_15")
    out["D_10m_otm_dotm"] = D("ac_od_10", "ap_od_10")
    out["D_5m_otm_dotm"] = D("ac_od_5", "ap_od_5")
    out["D_15m_atm"] = D("ac_atm_15", "ap_atm_15")
    out["D_10m_atm"] = D("ac_atm_10", "ap_atm_10")
    out["D_5m_atm"] = D("ac_atm_5", "ap_atm_5")
    out["V_15m_otm_dotm"] = V("ac_od_15", "ap_od_15")
    out["V_10m_otm_dotm"] = V("ac_od_10", "ap_od_10")
    out["V_5m_otm_dotm"] = V("ac_od_5", "ap_od_5")
    out["n_trades_15m"] = rows["n15"].astype(int)
    out["n_trades_10m"] = rows["n10"].astype(int)
    out["n_trades_5m"] = rows["n5"].astype(int)

    out = out.sort_values("window_id").reset_index(drop=True)
    out.to_parquet(OUT, index=False)

    data = OUT.read_bytes()
    print(f"\nGuardado: {OUT}")
    print(f"ventanas con señal: {len(out):,}")
    print(f"file_sha256: {hashlib.sha256(data).hexdigest()}")
    print(f"\nresumen D_15m_otm_dotm: {out['D_15m_otm_dotm'].describe()[['mean','std','min','max']].to_dict()}")
    print(f"ventanas con |D_15m_otm_dotm|>5: {(out['D_15m_otm_dotm'].abs()>5).sum():,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
