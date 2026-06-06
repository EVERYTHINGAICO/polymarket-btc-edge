"""Tests para src/signal_bs76.py: Black-76 delta + D/V calculation paralelo.

Validacion de:
1. Parser de instrument_name (strike, expiry, tipo).
2. Black-76 delta vs valor analitico conocido (ATM => |delta|~0.5).
3. moneyness_bucket cortes correctos.
4. compute_signal_for_window con trades sinteticos: resultado conocido.
5. Filtro de IV corrupta.
6. Cutoff de ventana temporal (5m/10m/15m).
"""

from __future__ import annotations

import math
import unittest
from datetime import datetime, timezone

from src.signal_bs76 import (
    DOTM_RANGE,
    OTM_RANGE,
    ATM_RANGE,
    RawTrade,
    black76_delta,
    compute_delta_for_trade,
    compute_signal_for_window,
    moneyness_bucket,
    norm_cdf,
    parse_instrument,
    signed_pressure_for_trade,
)


def _ts_ms(year: int, month: int, day: int, hour: int = 0, minute: int = 0, sec: int = 0) -> int:
    return int(datetime(year, month, day, hour, minute, sec, tzinfo=timezone.utc).timestamp() * 1000)


class NormCdfTests(unittest.TestCase):
    def test_norm_cdf_zero(self):
        self.assertAlmostEqual(norm_cdf(0.0), 0.5, places=10)

    def test_norm_cdf_extremes(self):
        self.assertLess(norm_cdf(-5.0), 1e-6)
        self.assertGreater(norm_cdf(5.0), 1 - 1e-6)

    def test_norm_cdf_symmetry(self):
        # N(-x) = 1 - N(x)
        for x in (0.3, 1.0, 2.5):
            self.assertAlmostEqual(norm_cdf(-x), 1 - norm_cdf(x), places=10)


class ParseInstrumentTests(unittest.TestCase):
    def test_parses_call(self):
        out = parse_instrument('BTC-26JUN26-60000-C')
        assert out is not None
        strike, expiry, opt = out
        self.assertEqual(strike, 60000.0)
        self.assertEqual(expiry, datetime(2026, 6, 26, 8, 0, 0, tzinfo=timezone.utc))
        self.assertEqual(opt, 'call')

    def test_parses_put_with_short_day(self):
        out = parse_instrument('BTC-4JUN26-64000-P')
        assert out is not None
        strike, expiry, opt = out
        self.assertEqual(strike, 64000.0)
        self.assertEqual(expiry, datetime(2026, 6, 4, 8, 0, 0, tzinfo=timezone.utc))
        self.assertEqual(opt, 'put')

    def test_rejects_bad_format(self):
        self.assertIsNone(parse_instrument('ETH-26JUN26-3000-C'))
        self.assertIsNone(parse_instrument('BTC-PERPETUAL'))
        self.assertIsNone(parse_instrument(''))
        self.assertIsNone(parse_instrument('BTC-32MAR26-60000-C'))  # day=32 invalido


class Black76DeltaTests(unittest.TestCase):
    def test_atm_call_delta_near_half(self):
        # ATM (F=K), sigma 0.5, T 30 dias: delta de call cerca de 0.5
        F = 60000.0
        K = 60000.0
        T = 30.0 / 365.0
        sigma = 0.5
        d = black76_delta(F, K, T, sigma, is_call=True)
        assert d is not None
        self.assertGreater(d, 0.5)
        self.assertLess(d, 0.6)

    def test_atm_put_delta_near_neg_half(self):
        F = 60000.0
        K = 60000.0
        T = 30.0 / 365.0
        sigma = 0.5
        d = black76_delta(F, K, T, sigma, is_call=False)
        assert d is not None
        self.assertGreater(d, -0.5)
        self.assertLess(d, -0.4)

    def test_deep_otm_call_delta_low(self):
        # F=60k, K=120k (deep OTM): call delta ~ 0
        d = black76_delta(60000.0, 120000.0, 30.0 / 365.0, 0.5, is_call=True)
        assert d is not None
        self.assertLess(d, 0.05)

    def test_deep_itm_call_delta_high(self):
        # F=60k, K=30k (deep ITM): call delta ~ 1
        d = black76_delta(60000.0, 30000.0, 30.0 / 365.0, 0.5, is_call=True)
        assert d is not None
        self.assertGreater(d, 0.95)

    def test_invalid_params_return_none(self):
        self.assertIsNone(black76_delta(60000, 60000, 0.0, 0.5, True))    # T=0
        self.assertIsNone(black76_delta(60000, 60000, 0.1, 0.0, True))    # sigma=0
        self.assertIsNone(black76_delta(0, 60000, 0.1, 0.5, True))         # F=0
        self.assertIsNone(black76_delta(60000, 0, 0.1, 0.5, True))         # K=0

    def test_put_call_relation(self):
        # call_delta - put_delta = 1 (Black-76, sin descuento r=0)
        F, K, T, sigma = 60000.0, 65000.0, 30.0 / 365.0, 0.6
        cd = black76_delta(F, K, T, sigma, True)
        pd = black76_delta(F, K, T, sigma, False)
        assert cd is not None and pd is not None
        self.assertAlmostEqual(cd - pd, 1.0, places=10)


class MoneynessBucketTests(unittest.TestCase):
    def test_dotm_classifies_otm_dotm(self):
        self.assertEqual(moneyness_bucket(0.05), 'otm_dotm')   # DOTM
        self.assertEqual(moneyness_bucket(0.125), 'otm_dotm')  # boundary DOTM

    def test_otm_classifies_otm_dotm(self):
        self.assertEqual(moneyness_bucket(0.20), 'otm_dotm')   # OTM
        self.assertEqual(moneyness_bucket(0.375), 'otm_dotm')  # boundary OTM

    def test_atm(self):
        self.assertEqual(moneyness_bucket(0.50), 'atm')
        self.assertEqual(moneyness_bucket(0.625), 'atm')  # boundary ATM

    def test_below_dotm_excluded(self):
        self.assertIsNone(moneyness_bucket(0.01))
        self.assertIsNone(moneyness_bucket(0.02))  # exclusive boundary

    def test_above_atm_excluded(self):
        self.assertIsNone(moneyness_bucket(0.7))
        self.assertIsNone(moneyness_bucket(0.95))


class IvFilterTests(unittest.TestCase):
    def test_iv_zero_rejected(self):
        trade = RawTrade(
            trade_id='t1', timestamp_ms=_ts_ms(2026, 6, 1),
            instrument_name='BTC-26JUN26-60000-P',
            direction='buy', iv=0.0, index_price=60000.0, amount=1.0,
        )
        delta, opt = compute_delta_for_trade(trade)
        self.assertIsNone(delta)

    def test_iv_too_high_rejected(self):
        trade = RawTrade(
            trade_id='t1', timestamp_ms=_ts_ms(2026, 6, 1),
            instrument_name='BTC-26JUN26-60000-P',
            direction='buy', iv=301.0, index_price=60000.0, amount=1.0,
        )
        delta, opt = compute_delta_for_trade(trade)
        self.assertIsNone(delta)

    def test_iv_300_accepted(self):
        trade = RawTrade(
            trade_id='t1', timestamp_ms=_ts_ms(2026, 6, 1),
            instrument_name='BTC-26JUN26-60000-P',
            direction='buy', iv=300.0, index_price=60000.0, amount=1.0,
        )
        delta, opt = compute_delta_for_trade(trade)
        self.assertIsNotNone(delta)


class SignedPressureTests(unittest.TestCase):
    def _make_call_otm(self, direction: str, amount: float = 1.0) -> RawTrade:
        # call OTM: F=60000, K=65000 (~24 dias), iv=60% -> delta ~0.35 (OTM bucket)
        return RawTrade(
            trade_id='t', timestamp_ms=_ts_ms(2026, 6, 1),
            instrument_name='BTC-26JUN26-65000-C',
            direction=direction, iv=60.0, index_price=60000.0, amount=amount,
        )

    def test_buy_positive_pressure(self):
        trade = self._make_call_otm('buy', amount=1.0)
        pressure, bucket, opt = signed_pressure_for_trade(trade)
        self.assertIsNotNone(pressure)
        assert pressure is not None
        self.assertGreater(pressure, 0)
        self.assertEqual(bucket, 'otm_dotm')
        self.assertEqual(opt, 'call')

    def test_sell_negative_pressure(self):
        trade = self._make_call_otm('sell', amount=1.0)
        pressure, bucket, opt = signed_pressure_for_trade(trade)
        self.assertIsNotNone(pressure)
        assert pressure is not None
        self.assertLess(pressure, 0)

    def test_amount_scales_pressure(self):
        a = signed_pressure_for_trade(self._make_call_otm('buy', amount=1.0))[0]
        b = signed_pressure_for_trade(self._make_call_otm('buy', amount=3.0))[0]
        assert a is not None and b is not None
        self.assertAlmostEqual(b / a, 3.0, places=6)


class ComputeWindowTests(unittest.TestCase):
    def test_call_buy_dominant_gives_positive_D_otm(self):
        # ts_open = 2026-06-01 12:00, ventana 15min termina 12:15
        end_ms = _ts_ms(2026, 6, 1, 12, 15)
        # 3 trades de calls OTM (buy) + 1 de put OTM (buy) -> A_C >> A_P pero ambos signed +
        # En realidad para D queremos clarity: calls buy + puts sell -> D positivo
        trades = [
            RawTrade('1', _ts_ms(2026, 6, 1, 12, 5), 'BTC-26JUN26-65000-C', 'buy', 60.0, 60000.0, 2.0),
            RawTrade('2', _ts_ms(2026, 6, 1, 12, 7), 'BTC-26JUN26-65000-C', 'buy', 60.0, 60000.0, 1.5),
            RawTrade('3', _ts_ms(2026, 6, 1, 12, 9), 'BTC-26JUN26-65000-C', 'buy', 60.0, 60000.0, 1.0),
            RawTrade('4', _ts_ms(2026, 6, 1, 12, 11), 'BTC-26JUN26-55000-P', 'sell', 60.0, 60000.0, 1.0),
        ]
        result = compute_signal_for_window(trades, end_ms, 15)
        self.assertGreater(result['otm_dotm']['D'], 0)
        self.assertEqual(result['otm_dotm']['n_trades'], 4)

    def test_cutoff_excludes_old_trades(self):
        end_ms = _ts_ms(2026, 6, 1, 12, 15)
        # Trade a 12:10 (dentro de 5m) y otro a 12:00 (fuera de 5m, dentro de 15m)
        trades = [
            RawTrade('in', _ts_ms(2026, 6, 1, 12, 12), 'BTC-26JUN26-65000-C', 'buy', 60.0, 60000.0, 1.0),
            RawTrade('out', _ts_ms(2026, 6, 1, 12, 5), 'BTC-26JUN26-65000-C', 'buy', 60.0, 60000.0, 1.0),
        ]
        r5 = compute_signal_for_window(trades, end_ms, 5)
        r15 = compute_signal_for_window(trades, end_ms, 15)
        self.assertEqual(r5['otm_dotm']['n_trades'], 1)
        self.assertEqual(r15['otm_dotm']['n_trades'], 2)

    def test_trade_at_or_after_end_excluded(self):
        end_ms = _ts_ms(2026, 6, 1, 12, 15)
        trades = [
            RawTrade('at_end', end_ms, 'BTC-26JUN26-65000-C', 'buy', 60.0, 60000.0, 1.0),
            RawTrade('after', end_ms + 1000, 'BTC-26JUN26-65000-C', 'buy', 60.0, 60000.0, 1.0),
            RawTrade('before', end_ms - 60_000, 'BTC-26JUN26-65000-C', 'buy', 60.0, 60000.0, 1.0),
        ]
        r = compute_signal_for_window(trades, end_ms, 15)
        self.assertEqual(r['otm_dotm']['n_trades'], 1)

    def test_atm_bucket_separate(self):
        end_ms = _ts_ms(2026, 6, 1, 12, 15)
        # ATM: F=60k, K=60k -> |delta| ~ 0.5 -> bucket atm
        trades = [
            RawTrade('a', _ts_ms(2026, 6, 1, 12, 10), 'BTC-26JUN26-60000-C', 'buy', 60.0, 60000.0, 1.0),
            RawTrade('o', _ts_ms(2026, 6, 1, 12, 10), 'BTC-26JUN26-65000-C', 'buy', 60.0, 60000.0, 1.0),
        ]
        r = compute_signal_for_window(trades, end_ms, 15)
        self.assertEqual(r['atm']['n_trades'], 1)
        self.assertEqual(r['otm_dotm']['n_trades'], 1)

    def test_empty_window_returns_zeros(self):
        end_ms = _ts_ms(2026, 6, 1, 12, 15)
        r = compute_signal_for_window([], end_ms, 15)
        self.assertEqual(r['otm_dotm']['D'], 0.0)
        self.assertEqual(r['otm_dotm']['V'], 0.0)
        self.assertEqual(r['otm_dotm']['n_trades'], 0)


class CrossCheckExp2Tests(unittest.TestCase):
    """Cross-check: el trade de muestra que el agente Exp2 documento.

    Sample real (capturado en chat 2026-06-02):
    timestamp=1780393167248 ms (2026-06-02T17:39:27Z aprox)
    iv=63.37 price=0.0007 amount=0.1 direction=sell
    index_price=69405.72 instrument_name=BTC-4JUN26-64000-P

    Verificamos:
    - parse_instrument: K=64000, expiry=2026-06-04 08:00 UTC, put.
    - black76_delta es negativo (put), |delta| pequeno (deep OTM put).
    """
    def test_sample_trade(self):
        trade = RawTrade(
            trade_id='431634482',
            timestamp_ms=1780393167248,
            instrument_name='BTC-4JUN26-64000-P',
            direction='sell',
            iv=63.37,
            index_price=69405.72,
            amount=0.1,
        )
        parsed = parse_instrument(trade.instrument_name)
        assert parsed is not None
        strike, expiry, opt = parsed
        self.assertEqual(strike, 64000.0)
        self.assertEqual(expiry, datetime(2026, 6, 4, 8, 0, 0, tzinfo=timezone.utc))
        self.assertEqual(opt, 'put')
        delta, _ = compute_delta_for_trade(trade)
        assert delta is not None
        # put deep OTM (K=64k, F=69.4k): delta negativo y pequeno en absoluto
        self.assertLess(delta, 0)
        self.assertGreater(delta, -0.5)


if __name__ == '__main__':
    unittest.main()
