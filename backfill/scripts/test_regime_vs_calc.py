"""TEST A/B/C — ¿el 51% de Exp1 vs 60% de Exp2 es por el CÁLCULO de D o por RÉGIMEN?

Plan (decidido con Pedro): usar los OUTCOMES de Exp1 (su DB, tal cual) + recalcular D
con el método de Exp2 (Black-76, mismos cortes moneyness, mismo filtro IV) sobre los
trades históricos del período de Exp1 (descargados de history.deribit.com).

Compara:
  (1) accuracy de Gate1 con MI D sobre outcomes de Exp1
  (2) por ventana: D_exp1 (registrado por Exp1) vs D_mio (recalculado)

Lectura:
  accuracy ~60% -> era el CÁLCULO (Exp1 medía D distinto). Edge generaliza.
  accuracy ~51% -> es RÉGIMEN. Edge no generaliza forward.
  + si D_exp1 y D_mio difieren mucho -> confirma diferencia de cálculo.

Reusa la lógica de build_deribit_features (Black-76, moneyness, IV<=300).
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import duckdb
import numpy as np
import pandas as pd
from scipy.stats import binomtest

# reusar funciones exactas de build_deribit_features
from scripts.build_deribit_features import black76_delta, expiry_ts, moneyness_bucket

EXP1_DB = "D:/openclaw/PROJECT DESIGN/data/observations.db"
TRADES = (ROOT / "data" / "raw" / "deribit" / "*.jsonl").as_posix()


def compute_D_15m(windows: pd.DataFrame) -> pd.DataFrame:
    """Calcula D_15m_otm_dotm con el método Exp2 para las ventanas dadas (ts_open/ts_close en epoch s)."""
    # cargar trades del rango
    tmin = int(windows["ts_open_s"].min()) * 1000
    tmax = int(windows["ts_close_s"].max()) * 1000
    trades = duckdb.sql(f"""
        SELECT timestamp ts, instrument_name, direction, amount, iv, index_price
        FROM read_json_auto('{TRADES}', format='newline_delimited',
            columns={{'timestamp':'BIGINT','instrument_name':'VARCHAR','direction':'VARCHAR',
                      'amount':'DOUBLE','iv':'DOUBLE','index_price':'DOUBLE'}}, ignore_errors=true)
        WHERE iv > 0 AND iv <= 300 AND timestamp >= {tmin} AND timestamp < {tmax}
    """).df()
    parts = trades["instrument_name"].str.split("-", expand=True)
    trades["K"] = pd.to_numeric(parts[2], errors="coerce")
    trades["is_call"] = parts[3] == "C"
    trades["exp_ts"] = parts[1].map(lambda s: expiry_ts(s) if isinstance(s, str) else None)
    trades = trades.dropna(subset=["K", "exp_ts"])
    spy = 365 * 86400
    dd, bk = [], []
    for ts, F, K, iv, isc, ex in zip(trades["ts"], trades["index_price"], trades["K"],
                                     trades["iv"], trades["is_call"], trades["exp_ts"]):
        T = (ex - ts / 1000.0) / spy
        d = black76_delta(F, K, T, iv / 100.0, bool(isc))
        if d is None:
            dd.append(None); bk.append(None); continue
        dd.append(abs(d)); bk.append(moneyness_bucket(abs(d)))
    trades["delta_abs"] = dd; trades["bucket"] = bk
    trades["sign"] = trades["direction"].map({"buy": 1.0, "sell": -1.0})
    trades = trades.dropna(subset=["bucket", "delta_abs", "sign"])
    trades["sp"] = trades["sign"] * trades["amount"] * trades["delta_abs"]
    odd = trades[trades["bucket"] == "otm_dotm"]

    con = duckdb.connect()
    con.register("tr", odd[["ts", "is_call", "sp"]])
    con.register("w", windows[["window_id", "ts_open_s", "ts_close_s"]])
    res = con.execute("""
        SELECT w.window_id,
          SUM(CASE WHEN tr.is_call THEN tr.sp ELSE 0 END) ac,
          SUM(CASE WHEN NOT tr.is_call THEN tr.sp ELSE 0 END) ap,
          COUNT(*) n
        FROM w JOIN tr ON tr.ts >= w.ts_open_s*1000 AND tr.ts < w.ts_close_s*1000
        GROUP BY w.window_id
    """).df()
    res["D_mio"] = (res["ac"] - res["ap"]) / 2.0
    return res[["window_id", "D_mio", "n"]]


def main() -> int:
    # outcomes + D_exp1 + ventana, de la DB de Exp1 (tal cual)
    con = sqlite3.connect(EXP1_DB)
    e1 = pd.read_sql_query(
        "SELECT window_id, ts_open, ts_close, outcome, D_15m_otm_dotm AS D_exp1, n_trades_15m "
        "FROM observations WHERE outcome IN ('Up','Down') AND is_incomplete=0", con)
    con.close()
    # ts a epoch s
    e1["ts_open_s"] = pd.to_datetime(e1["ts_open"], utc=True).astype("int64") // 10**9
    e1["ts_close_s"] = pd.to_datetime(e1["ts_close"], utc=True).astype("int64") // 10**9
    print(f"Exp1 ventanas (outcome, completa): {len(e1)}")

    mine = compute_D_15m(e1)
    m = e1.merge(mine, on="window_id", how="inner")
    print(f"ventanas con D recalculado: {len(m)}")
    print()

    # (1) accuracy Gate1 con MI D
    sub = m[(m["D_mio"].abs() > 5) & (m["n_trades_15m"] >= 30)]
    pred = np.where(sub["D_mio"] > 0, "Up", "Down")
    hits = (pred == sub["outcome"].values).astype(int)
    n = len(sub); acc = hits.mean() if n else float("nan")
    ci = binomtest(int(hits.sum()), n).proportion_ci(0.95) if n else None
    print("===== (1) ACCURACY con MI D (Black-76) sobre periodo Exp1 =====")
    print(f"  n={n}  accuracy={acc:.4f}  CI95=[{ci.low:.3f},{ci.high:.3f}]" if ci else f"  n={n}")
    print(f"  -> Exp2 historico dio 60.7%. Exp1 con su propio D daba ~51%.")
    print(f"  -> {'~60% = era el CALCULO (edge generaliza)' if acc>0.56 else '~51% = es REGIMEN (no generaliza)' if acc<0.54 else 'zona intermedia'}")
    print()

    # (2) D_exp1 vs D_mio por ventana
    cmp = m.dropna(subset=["D_exp1", "D_mio"])
    corr = cmp["D_exp1"].corr(cmp["D_mio"])
    # cuantas veces coincide el SIGNO (lo que importa para Gate1)
    same_sign = (np.sign(cmp["D_exp1"]) == np.sign(cmp["D_mio"])).mean()
    print("===== (2) D_exp1 (registrado) vs D_mio (recalculado) por ventana =====")
    print(f"  correlacion: {corr:.4f}")
    print(f"  coincidencia de SIGNO: {100*same_sign:.1f}%")
    print(f"  -> si corr alta y signo ~100%: el calculo es ~igual (no era el problema)")
    print(f"  -> si difieren: el calculo SI cambia -> explicaria la discrepancia")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
