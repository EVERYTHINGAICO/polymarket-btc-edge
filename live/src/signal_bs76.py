"""Calculo de senal D/V usando delta Black-76 al instante del trade.

Replica el metodo de Exp2 (D:\\EXPERIMENTOS BTC OPTIONS) tal como esta
documentado en REPORTE_PARA_EXP1_calculo_D.md.

Diferencias clave con src/signal.py (el original de Exp1):
- delta se RECOMPUTA con Black-76 usando iv + index_price del trade mismo,
  NO se toma del campo greeks.delta del payload ni del ticker endpoint.
- Filtra trades con iv <= 0 o iv > 300 (corrupcion).
- Parsea strike + expiry del instrument_name (formato BTC-DDMMMYY-K-{C,P}).
- Calcula T (time to expiry) en anios ACT/365.

Modulo PARALELO. No reemplaza a signal.py. Se calcula a posteriori sobre
trades crudos guardados con iv + index_price.

Cumple PROJECT_DESIGN seccion 0: read-only, sin trading.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone

# Cortes de moneyness (paper Alexander 2022, mismos que src/deribit_feed.py)
DOTM_RANGE = (0.02, 0.125)
OTM_RANGE = (0.125, 0.375)
ATM_RANGE = (0.375, 0.625)

# Validez de IV (de Exp2 REPORTE_PARA_EXP1_calculo_D.md paso 1)
IV_MIN_PCT = 0.0
IV_MAX_PCT = 300.0

# Tres meses de un anio expresado como dias (para parser de instrument)
_MONTHS = {
    'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
    'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12,
}
_INSTRUMENT_RE = re.compile(r'^BTC-(\d{1,2})([A-Z]{3})(\d{2})-(\d+)-([CP])$')

# Deribit BTC options expiran a las 08:00 UTC
_EXPIRY_HOUR_UTC = 8

# Ventanas temporales (igual que signal.py original)
WINDOW_MINUTES = (5, 10, 15)


@dataclass(frozen=True)
class RawTrade:
    """Trade crudo de Deribit con TODOS los campos necesarios para Black-76."""
    trade_id: str
    timestamp_ms: int
    instrument_name: str
    direction: str  # "buy" o "sell" (lado del taker, raw de Deribit)
    iv: float       # en porcentaje (63.37 = 63.37%)
    index_price: float
    amount: float


def norm_cdf(x: float) -> float:
    """N(x) usando math.erf, sin scipy."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def parse_instrument(instrument_name: str) -> tuple[float, datetime, str] | None:
    """Parsea 'BTC-26JUN26-60000-P' -> (60000.0, datetime expiry UTC, 'put').

    Devuelve None si el formato no matchea.
    """
    m = _INSTRUMENT_RE.match(instrument_name)
    if not m:
        return None
    day_s, mon_s, yr_s, strike_s, cp = m.groups()
    month = _MONTHS.get(mon_s)
    if month is None:
        return None
    try:
        day = int(day_s)
        year = 2000 + int(yr_s)
        strike = float(strike_s)
    except (TypeError, ValueError):
        return None
    try:
        expiry = datetime(year, month, day, _EXPIRY_HOUR_UTC, 0, 0, tzinfo=timezone.utc)
    except ValueError:
        return None
    option_type = 'call' if cp == 'C' else 'put'
    return strike, expiry, option_type


def black76_delta(F: float, K: float, T_years: float, sigma: float, is_call: bool) -> float | None:
    """Delta segun Black-76 (futures option model).

    F = forward/index price; K = strike; T = anios hasta expiracion; sigma = iv (decimal, no %); r = 0.
    Devuelve delta firmado: call positivo, put negativo. None si parametros invalidos.
    """
    if sigma <= 0 or T_years <= 0 or F <= 0 or K <= 0:
        return None
    try:
        d1 = (math.log(F / K) + 0.5 * sigma * sigma * T_years) / (sigma * math.sqrt(T_years))
    except (ValueError, ZeroDivisionError):
        return None
    if is_call:
        return norm_cdf(d1)
    return norm_cdf(d1) - 1.0


def moneyness_bucket(delta_abs: float) -> str | None:
    """Devuelve 'otm_dotm', 'atm' o None (ignorado: deep-OTM o ITM)."""
    if DOTM_RANGE[0] < delta_abs <= DOTM_RANGE[1]:
        return 'otm_dotm'
    if OTM_RANGE[0] < delta_abs <= OTM_RANGE[1]:
        return 'otm_dotm'
    if ATM_RANGE[0] < delta_abs <= ATM_RANGE[1]:
        return 'atm'
    return None


def compute_delta_for_trade(trade: RawTrade) -> tuple[float | None, str | None]:
    """Devuelve (delta_signed, option_type) o (None, None) si trade invalido.

    Aplica el filtro de IV de Exp2 (iv en (0, 300]).
    """
    if not (IV_MIN_PCT < trade.iv <= IV_MAX_PCT):
        return None, None
    parsed = parse_instrument(trade.instrument_name)
    if parsed is None:
        return None, None
    strike, expiry, option_type = parsed
    trade_dt = datetime.fromtimestamp(trade.timestamp_ms / 1000.0, tz=timezone.utc)
    T_years = (expiry - trade_dt).total_seconds() / (365.0 * 86400.0)
    sigma = trade.iv / 100.0
    delta = black76_delta(trade.index_price, strike, T_years, sigma, option_type == 'call')
    if delta is None:
        return None, None
    return delta, option_type


def signed_pressure_for_trade(trade: RawTrade) -> tuple[float | None, str | None, str | None]:
    """Calcula la contribucion firmada de un trade a D/V.

    Devuelve (signed_pressure, bucket, option_type) o (None, None, None) si se descarta.
    """
    delta_signed, option_type = compute_delta_for_trade(trade)
    if delta_signed is None or option_type is None:
        return None, None, None
    delta_abs = abs(delta_signed)
    bucket = moneyness_bucket(delta_abs)
    if bucket is None:
        return None, None, None
    sign = 1.0 if trade.direction == 'buy' else -1.0
    pressure = sign * trade.amount * delta_abs
    return pressure, bucket, option_type


def compute_signal_for_window(
    trades: list[RawTrade],
    window_end_ms: int,
    window_minutes: int,
) -> dict[str, dict[str, float]]:
    """Computa A_C, A_P, D, V, n_trades por bucket para una ventana.

    Filtra trades a [window_end_ms - window_minutes*60000, window_end_ms).
    """
    cutoff_ms = window_end_ms - window_minutes * 60_000
    aggregates: dict[str, dict[str, float]] = defaultdict(
        lambda: {'A_C': 0.0, 'A_P': 0.0, 'n_trades': 0}
    )
    for trade in trades:
        if trade.timestamp_ms < cutoff_ms or trade.timestamp_ms >= window_end_ms:
            continue
        pressure, bucket, option_type = signed_pressure_for_trade(trade)
        if pressure is None:
            continue
        key = 'A_C' if option_type == 'call' else 'A_P'
        aggregates[bucket][key] += pressure
        aggregates[bucket]['n_trades'] += 1
    result: dict[str, dict[str, float]] = {}
    for bucket in ('otm_dotm', 'atm'):
        agg = aggregates.get(bucket, {'A_C': 0.0, 'A_P': 0.0, 'n_trades': 0})
        a_c = agg['A_C']
        a_p = agg['A_P']
        result[bucket] = {
            'A_C': a_c,
            'A_P': a_p,
            'D': (a_c - a_p) / 2.0,
            'V': (a_c + a_p) / 2.0,
            'n_trades': agg['n_trades'],
        }
    return result


def flatten_metrics_bs76(
    metrics: dict[str, dict[str, float]],
    window_minutes: int,
) -> dict[str, float]:
    """Aplana en columnas con sufijo _bs76 listas para INSERT/UPDATE."""
    flat: dict[str, float] = {
        f'n_trades_{window_minutes}m_bs76': (
            metrics['otm_dotm']['n_trades'] + metrics['atm']['n_trades']
        ),
    }
    for bucket in ('otm_dotm', 'atm'):
        flat[f'D_{window_minutes}m_{bucket}_bs76'] = metrics[bucket]['D']
        if bucket == 'otm_dotm':
            flat[f'V_{window_minutes}m_{bucket}_bs76'] = metrics[bucket]['V']
    return flat


def compute_all_windows_bs76(
    trades: list[RawTrade],
    window_end_ms: int,
) -> dict[str, float]:
    """Computa todas las variantes (5m/10m/15m, otm_dotm/atm) y devuelve plano."""
    out: dict[str, float] = {}
    for minutes in WINDOW_MINUTES:
        metrics = compute_signal_for_window(trades, window_end_ms, minutes)
        out.update(flatten_metrics_bs76(metrics, minutes))
    return out
