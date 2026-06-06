from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.db import fetch_observation
from src.logger import CloseContext, OpenContext, RuntimeStatus, SupervisedLoggerRuntime, build_close_snapshot, build_open_snapshot, cleanup_incomplete_window, demo_runtime_once, record_close_window, record_open_window
from src.polymarket_feed import ActiveWindowSnapshot
from src.signal import RollingSignalBuffer, SignalTrade


class LoggerTests(unittest.TestCase):
    def make_buffer(self) -> RollingSignalBuffer:
        buffer = RollingSignalBuffer()
        now = 15 * 60 * 1000
        buffer.add_trade(SignalTrade(now - 60_000, 'buyer', 'call', 'OTM', 10.0, 0.10))
        buffer.add_trade(SignalTrade(now - 120_000, 'buyer', 'put', 'ATM', 6.0, 0.50))
        return buffer

    def test_build_open_snapshot_includes_signal_metrics(self) -> None:
        context = OpenContext(
            window=ActiveWindowSnapshot('w1', '2026-05-25T06:00:00Z', 65000.0, 0.51),
            deribit_index_open=65010.0,
            signal_timestamp_ms=15 * 60 * 1000,
        )
        snapshot = build_open_snapshot(context, self.make_buffer(), min_trades=3)
        self.assertEqual('w1', snapshot['window_id'])
        self.assertEqual(1, snapshot['insufficient_flow'])
        self.assertIn('D_15m_otm_dotm', snapshot)

    def test_build_open_snapshot_marks_incomplete_runtime(self) -> None:
        context = OpenContext(
            window=ActiveWindowSnapshot('w1', '2026-05-25T06:00:00Z', 65000.0, 0.51),
            deribit_index_open=65010.0,
            signal_timestamp_ms=15 * 60 * 1000,
        )
        snapshot = build_open_snapshot(context, self.make_buffer(), runtime_status=RuntimeStatus(ok=False, is_incomplete=True, notes='deribit_gap'))
        self.assertEqual(1, snapshot['is_incomplete'])
        self.assertIn('deribit_gap', snapshot['notes'])

    def test_build_close_snapshot_derives_outcome(self) -> None:
        close = CloseContext('w1', '2026-05-25T06:15:00Z', 65020.0, 64990.0, 0.12)
        snapshot = build_close_snapshot(close, price_to_beat=65000.0)
        self.assertEqual('Down', snapshot['outcome'])

    def test_record_open_and_close_window_persist_to_sqlite(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / 'observations.db'
            open_context = OpenContext(
                window=ActiveWindowSnapshot('w1', '2026-05-25T06:00:00Z', 65000.0, 0.51),
                deribit_index_open=65010.0,
                signal_timestamp_ms=15 * 60 * 1000,
            )
            record_open_window(db_path, open_context, self.make_buffer())
            record_close_window(db_path, CloseContext('w1', '2026-05-25T06:15:00Z', 65020.0, 65005.0, 0.78), price_to_beat=65000.0)
            row = fetch_observation(db_path, 'w1')
            self.assertIsNotNone(row)
            assert row is not None
            self.assertEqual('Up', row['outcome'])
            self.assertEqual(65010.0, row['deribit_index_open'])

    def test_record_close_window_can_mark_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / 'observations.db'
            open_context = OpenContext(
                window=ActiveWindowSnapshot('w2', '2026-05-25T06:00:00Z', 65000.0, 0.51),
                deribit_index_open=65010.0,
                signal_timestamp_ms=15 * 60 * 1000,
            )
            record_open_window(db_path, open_context, self.make_buffer())
            record_close_window(db_path, CloseContext('w2', '2026-05-25T06:15:00Z', 65020.0, 65005.0, 0.78), price_to_beat=65000.0, is_incomplete=True, notes='network_drop', insufficient_flow=True)
            row = fetch_observation(db_path, 'w2')
            assert row is not None
            self.assertEqual(1, row['is_incomplete'])
            self.assertEqual(1, row['insufficient_flow'])
            self.assertEqual('network_drop', row['notes'])

    def test_record_close_window_with_missing_chainlink_keeps_real_non_demo_window(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / 'observations.db'
            open_context = OpenContext(
                window=ActiveWindowSnapshot('btc-updown-15m-1779826500', '2026-05-26T20:15:00Z', None, 0.42),
                deribit_index_open=75944.42,
                signal_timestamp_ms=1779826500 * 1000,
            )
            record_open_window(db_path, open_context, self.make_buffer())
            record_close_window(db_path, CloseContext('btc-updown-15m-1779826500', '2026-05-26T20:30:00Z', 76000.0, None, 0.44), price_to_beat=None, is_incomplete=True, notes='pilot_live', insufficient_flow=False)
            row = fetch_observation(db_path, 'btc-updown-15m-1779826500')
            assert row is not None
            self.assertEqual('btc-updown-15m-1779826500', row['window_id'])
            self.assertEqual(1, row['is_incomplete'])
            self.assertIn('missing_price_to_beat', row['notes'])
            self.assertIn('missing_chainlink_close', row['notes'])
            self.assertNotEqual('demo-window', row['window_id'])

    def test_supervised_runtime_emits_utc_logs_and_marks_runtime_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / 'observations.db'
            log_path = Path(tmpdir) / 'runtime.log'
            runtime = SupervisedLoggerRuntime(db_path, log_path)
            runtime.open_window(
                OpenContext(
                    window=ActiveWindowSnapshot('w3', '2026-05-25T20:30:00Z', 65000.0, 0.51),
                    deribit_index_open=65010.0,
                    signal_timestamp_ms=15 * 60 * 1000,
                ),
                self.make_buffer(),
                min_trades=5,
            )
            runtime.mark_runtime_error('w3', ts_close='2026-05-25T20:45:00Z', price_to_beat=65000.0, notes='disconnect', insufficient_flow=True)
            lines = [json.loads(line) for line in log_path.read_text(encoding='utf-8').splitlines()]
            self.assertTrue(all(line['ts_utc'].endswith('Z') for line in lines))
            events = [line['event'] for line in lines]
            self.assertIn('window_opened', events)
            self.assertIn('runtime_error', events)
            self.assertIn('reconnect_observed', events)
            row = runtime.read_window('w3')
            assert row is not None
            self.assertEqual(1, row['is_incomplete'])
            self.assertEqual(1, row['insufficient_flow'])

    def test_cleanup_open_row_on_error_marks_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / 'observations.db'
            open_context = OpenContext(
                window=ActiveWindowSnapshot('w4', '2026-05-25T20:45:00Z', None, 0.57),
                deribit_index_open=75987.87,
                signal_timestamp_ms=15 * 60 * 1000,
            )
            record_open_window(db_path, open_context, self.make_buffer())
            row = cleanup_incomplete_window(db_path, 'w4', notes='runtime_error,missing_close_snapshot,deribit_ws_timeout,missing_chainlink_close', insufficient_flow=True)
            assert row is not None
            self.assertEqual(1, row['is_incomplete'])
            self.assertEqual(1, row['insufficient_flow'])
            self.assertIn('runtime_error', row['notes'])
            self.assertIn('missing_close_snapshot', row['notes'])
            self.assertIn('deribit_ws_timeout', row['notes'])
            self.assertIn('missing_chainlink_close', row['notes'])
            self.assertIsNone(row['ts_close'])

    def test_cleanup_does_not_overwrite_existing_close(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / 'observations.db'
            open_context = OpenContext(
                window=ActiveWindowSnapshot('w5', '2026-05-25T20:45:00Z', 65000.0, 0.57),
                deribit_index_open=75987.87,
                signal_timestamp_ms=15 * 60 * 1000,
            )
            record_open_window(db_path, open_context, self.make_buffer())
            record_close_window(db_path, CloseContext('w5', '2026-05-25T21:00:00Z', 76000.0, 65010.0, 0.66), price_to_beat=65000.0, is_incomplete=False, notes='closed', insufficient_flow=False)
            row = cleanup_incomplete_window(db_path, 'w5', notes='runtime_error,deribit_ws_timeout', insufficient_flow=True)
            assert row is not None
            self.assertEqual('2026-05-25T21:00:00Z', row['ts_close'])
            self.assertEqual('closed', row['notes'])
            self.assertEqual(0, row['is_incomplete'])

    def test_cleanup_notes_accumulate_cause(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / 'observations.db'
            open_context = OpenContext(
                window=ActiveWindowSnapshot('w6', '2026-05-25T20:45:00Z', None, 0.57),
                deribit_index_open=75987.87,
                signal_timestamp_ms=15 * 60 * 1000,
            )
            record_open_window(db_path, open_context, self.make_buffer(), runtime_status=RuntimeStatus(ok=False, is_incomplete=True, notes='preexisting'))
            row = cleanup_incomplete_window(db_path, 'w6', notes='runtime_error,missing_close_snapshot', insufficient_flow=True)
            assert row is not None
            self.assertIn('preexisting', row['notes'])
            self.assertIn('runtime_error', row['notes'])
            self.assertIn('missing_close_snapshot', row['notes'])

    def test_timeout_cleanup_via_runtime_helper_is_conservative(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / 'observations.db'
            log_path = Path(tmpdir) / 'runtime.log'
            runtime = SupervisedLoggerRuntime(db_path, log_path)
            runtime.open_window(
                OpenContext(
                    window=ActiveWindowSnapshot('w7', '2026-05-25T20:45:00Z', None, 0.57),
                    deribit_index_open=75987.87,
                    signal_timestamp_ms=15 * 60 * 1000,
                ),
                self.make_buffer(),
            )
            row = runtime.cleanup_post_open_failure('w7', notes='runtime_error,missing_close_snapshot,deribit_ws_timeout,missing_chainlink_close', insufficient_flow=True)
            assert row is not None
            self.assertEqual(1, row['is_incomplete'])
            self.assertEqual(1, row['insufficient_flow'])
            self.assertIn('deribit_ws_timeout', row['notes'])
            lines = [json.loads(line) for line in log_path.read_text(encoding='utf-8').splitlines()]
            self.assertIn('post_open_cleanup', [line['event'] for line in lines])

    def test_one_window_pilot_uses_canonical_deribit_capture_api(self) -> None:
        import scripts.one_window_pilot as pilot
        from src.polymarket_feed import MarketHealthcheck, PilotMarket
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / 'observations.db'
            log_path = Path(tmpdir) / 'runtime.log'
            fake_market = PilotMarket(
                slug='btc-updown-15m-2779829200',
                window_id='btc-updown-15m-2779829200',
                open_epoch_seconds=2779829200,
                ts_open='2058-02-03T04:46:40Z',
                ts_close='2058-02-03T05:01:40Z',
                active=True,
                closed=False,
                accepting_orders=True,
                up_token_id='up',
                down_token_id='down',
                price_to_beat=76000.0,
                pm_up_price_open=None,
                end_date='2058-02-03T05:01:40Z',
                event_payload={},
                market_payload={},
            )
            fake_health = MarketHealthcheck(fake_market.slug, True, False, True, True, True, True, True, True, True, [])
            fake_capture = type('Capture', (), {'trades': [], 'counts': {'messages': 0, 'normalized_trades': 0, 'skipped': 0, 'classified_trades': 0, 'timeouts': 0, 'reconnects': 0, 'errors': 0}})()
            with patch.object(pilot, 'ROOT', Path(tmpdir)), \
                 patch.object(pilot, 'deribit_ws_healthcheck', return_value={'ok': True}), \
                 patch.object(pilot.PolymarketReadOnlyClient, 'discover_candidate_market', return_value=fake_market), \
                 patch.object(pilot.PolymarketReadOnlyClient, 'healthcheck_market', return_value=fake_health), \
                 patch.object(pilot, '_sleep_until', return_value=None), \
                 patch.object(pilot, 'fetch_deribit_index_price', return_value=76010.0), \
                 patch.object(pilot, 'midpoint_to_float', return_value=0.55), \
                 patch.object(pilot.PolymarketReadOnlyClient, 'fetch_midpoint', return_value={'mid': '0.55'}), \
                 patch.object(pilot, 'collect_live_deribit_trades', side_effect=[fake_capture, RuntimeError('timeout')]) as collect_mock:
                result = pilot.run_one_window_pilot(db_path, log_path)
            self.assertEqual(2, collect_mock.call_count)
            self.assertEqual('FAIL', result['status'])
            self.assertEqual('INCOMPLETE_REAL', result['row_kind'])

    def test_demo_runtime_once_is_observable_and_consistent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / 'observations.db'
            log_path = Path(tmpdir) / 'runtime.log'
            result = demo_runtime_once(db_path, log_path)
            self.assertIn('open_snapshot', result)
            self.assertIn('close_snapshot', result)
            self.assertEqual('demo-window', result['row']['window_id'])
            self.assertEqual(1, result['row']['is_incomplete'])

    def test_t5_restart_persistence_keeps_prior_row_intact_without_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / 'observations.db'
            log_path = Path(tmpdir) / 'runtime.log'

            result_before = demo_runtime_once(db_path, log_path)
            row_before = result_before['row']
            self.assertIsNotNone(row_before)
            self.assertEqual('demo-window', row_before['window_id'])

            result_after = demo_runtime_once(db_path, log_path)
            row_after = result_after['row']
            self.assertIsNotNone(row_after)
            self.assertEqual(row_before['window_id'], row_after['window_id'])
            self.assertEqual(row_before['ts_open'], row_after['ts_open'])
            self.assertEqual(row_before['ts_close'], row_after['ts_close'])
            self.assertEqual(row_before['is_incomplete'], row_after['is_incomplete'])
            self.assertEqual(row_before['insufficient_flow'], row_after['insufficient_flow'])

            with sqlite3.connect(db_path) as connection:
                count = connection.execute("SELECT COUNT(*) FROM observations WHERE window_id = ?", ('demo-window',)).fetchone()[0]
            self.assertEqual(1, count)


if __name__ == '__main__':
    unittest.main()
