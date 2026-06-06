from __future__ import annotations

import unittest

from src.signal import RollingSignalBuffer, SignalTrade, aggregate_window, bucket_for_trade, compute_signal_metrics


class SignalBufferTests(unittest.TestCase):
    def test_bucket_mapping_groups_otm_and_dotm(self) -> None:
        self.assertEqual("otm_dotm", bucket_for_trade(SignalTrade(0, "buyer", "call", "DOTM", 1.0, 0.1)))
        self.assertEqual("otm_dotm", bucket_for_trade(SignalTrade(0, "buyer", "call", "OTM", 1.0, 0.2)))
        self.assertEqual("atm", bucket_for_trade(SignalTrade(0, "buyer", "call", "ATM", 1.0, 0.5)))
        self.assertIsNone(bucket_for_trade(SignalTrade(0, "buyer", "call", "IGNORED", 1.0, 0.8)))

    def test_aggregate_window_tracks_call_put_pressure_and_count(self) -> None:
        trades = [
            SignalTrade(0, "buyer", "call", "DOTM", 2.0, 0.10),
            SignalTrade(1, "seller", "put", "OTM", 1.0, 0.20),
            SignalTrade(2, "buyer", "call", "ATM", 3.0, 0.50),
        ]
        aggregates = aggregate_window(trades)
        self.assertAlmostEqual(0.20, aggregates["otm_dotm"]["A_C"])
        self.assertAlmostEqual(-0.20, aggregates["otm_dotm"]["A_P"])
        self.assertEqual(2.0, aggregates["otm_dotm"]["n_trades"])
        self.assertAlmostEqual(1.50, aggregates["atm"]["A_C"])

    def test_t2_case_positive_100_buyer_calls_and_no_puts_produces_large_positive_d(self) -> None:
        trades = [SignalTrade(index, "buyer", "call", "OTM", 1.0, 0.20) for index in range(100)]
        metrics = compute_signal_metrics(trades)
        self.assertAlmostEqual(20.0, metrics["otm_dotm"]["A_C"])
        self.assertAlmostEqual(0.0, metrics["otm_dotm"]["A_P"])
        self.assertAlmostEqual(10.0, metrics["otm_dotm"]["D"])
        self.assertAlmostEqual(10.0, metrics["otm_dotm"]["V"])
        self.assertGreater(metrics["otm_dotm"]["D"], 0.0)

    def test_t2_case_balanced_50_calls_50_puts_produces_d_near_zero_and_large_v(self) -> None:
        trades = [
            *[SignalTrade(index, "buyer", "call", "OTM", 1.0, 0.20) for index in range(50)],
            *[SignalTrade(100 + index, "buyer", "put", "OTM", 1.0, 0.20) for index in range(50)],
        ]
        metrics = compute_signal_metrics(trades)
        self.assertAlmostEqual(10.0, metrics["otm_dotm"]["A_C"])
        self.assertAlmostEqual(10.0, metrics["otm_dotm"]["A_P"])
        self.assertAlmostEqual(0.0, metrics["otm_dotm"]["D"], places=9)
        self.assertAlmostEqual(10.0, metrics["otm_dotm"]["V"])
        self.assertGreater(metrics["otm_dotm"]["V"], 0.0)

    def test_t2_trade_older_than_16_minutes_does_not_count_in_15_minute_window(self) -> None:
        buffer = RollingSignalBuffer()
        now = 16 * 60 * 1000
        buffer.add_trade(SignalTrade(0, "buyer", "call", "OTM", 10.0, 0.20))
        buffer.add_trade(SignalTrade(15 * 60 * 1000, "buyer", "put", "ATM", 1.0, 0.50))
        buffer.prune(now, window_seconds=15 * 60)
        trades = buffer.trades_in_window(now, 15 * 60)
        self.assertEqual(1, len(trades))
        self.assertEqual("ATM", trades[0].moneyness)

    def test_snapshot_returns_5_10_15m_metrics(self) -> None:
        buffer = RollingSignalBuffer()
        now = 15 * 60 * 1000
        buffer.add_trade(SignalTrade(now - 2 * 60 * 1000, "buyer", "call", "DOTM", 10.0, 0.10))
        buffer.add_trade(SignalTrade(now - 7 * 60 * 1000, "buyer", "put", "OTM", 10.0, 0.10))
        buffer.add_trade(SignalTrade(now - 12 * 60 * 1000, "buyer", "call", "ATM", 10.0, 0.50))
        snapshot = buffer.snapshot(now)
        self.assertIn("D_5m_otm_dotm", snapshot)
        self.assertIn("D_10m_atm", snapshot)
        self.assertIn("V_15m_otm_dotm", snapshot)
        self.assertEqual(1.0, snapshot["n_trades_5m"])
        self.assertEqual(2.0, snapshot["n_trades_10m"])
        self.assertEqual(3.0, snapshot["n_trades_15m"])


if __name__ == "__main__":
    unittest.main()
