from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.db import (
    OBSERVATIONS_TABLE,
    fetch_observation,
    get_observations_columns,
    initialize_database,
    insert_open_snapshot,
    list_observations,
    update_close_snapshot,
)


class DatabaseSchemaTests(unittest.TestCase):
    def test_initialize_database_creates_observations_table_with_expected_columns(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / 'observations.db'
            initialize_database(db_path)

            import sqlite3
            connection = sqlite3.connect(db_path)
            try:
                table_name = connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                    (OBSERVATIONS_TABLE,),
                ).fetchone()
                self.assertEqual((OBSERVATIONS_TABLE,), table_name)
                expected_columns = [
                    'window_id','ts_open','price_to_beat','pm_up_price_open','deribit_index_open',
                    'D_5m_otm_dotm','D_10m_otm_dotm','D_15m_otm_dotm','D_5m_atm','D_10m_atm','D_15m_atm',
                    'V_5m_otm_dotm','V_10m_otm_dotm','V_15m_otm_dotm','n_trades_5m','n_trades_10m','n_trades_15m',
                    'ts_close','deribit_index_close','chainlink_close','outcome','pm_up_price_close',
                    'is_incomplete','insufficient_flow','notes',
                ]
                self.assertEqual(expected_columns, get_observations_columns(connection))
            finally:
                connection.close()

    def test_initialize_database_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / 'observations.db'
            initialize_database(db_path)
            initialize_database(db_path)
            self.assertTrue(db_path.exists())

    def test_insert_open_and_update_close_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / 'observations.db'
            insert_open_snapshot(db_path, {
                'window_id': 'w1',
                'ts_open': '2026-05-25T06:00:00Z',
                'price_to_beat': 65000.0,
                'pm_up_price_open': 0.51,
                'deribit_index_open': 65010.0,
                'D_5m_otm_dotm': 1.0,
                'D_10m_otm_dotm': 2.0,
                'D_15m_otm_dotm': 3.0,
                'D_5m_atm': 0.5,
                'D_10m_atm': 0.6,
                'D_15m_atm': 0.7,
                'V_5m_otm_dotm': 1.5,
                'V_10m_otm_dotm': 2.5,
                'V_15m_otm_dotm': 3.5,
                'n_trades_5m': 5,
                'n_trades_10m': 10,
                'n_trades_15m': 15,
                'is_incomplete': 0,
                'insufficient_flow': 0,
                'notes': '',
            })
            update_close_snapshot(db_path, 'w1', {
                'ts_close': '2026-05-25T06:15:00Z',
                'deribit_index_close': 65020.0,
                'chainlink_close': 65018.0,
                'outcome': 'Up',
                'pm_up_price_close': 0.83,
                'is_incomplete': 0,
                'insufficient_flow': 0,
                'notes': 'closed cleanly',
            })
            row = fetch_observation(db_path, 'w1')
            self.assertIsNotNone(row)
            assert row is not None
            self.assertEqual('Up', row['outcome'])
            self.assertEqual(15, row['n_trades_15m'])
            self.assertEqual('closed cleanly', row['notes'])

    def test_open_twice_same_window_does_not_duplicate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / 'observations.db'
            snapshot = {
                'window_id': 'w1',
                'ts_open': '2026-05-25T06:00:00Z',
                'price_to_beat': 65000.0,
                'pm_up_price_open': 0.51,
                'deribit_index_open': 65010.0,
                'D_5m_otm_dotm': 1.0,
                'D_10m_otm_dotm': 2.0,
                'D_15m_otm_dotm': 3.0,
                'D_5m_atm': 0.5,
                'D_10m_atm': 0.6,
                'D_15m_atm': 0.7,
                'V_5m_otm_dotm': 1.5,
                'V_10m_otm_dotm': 2.5,
                'V_15m_otm_dotm': 3.5,
                'n_trades_5m': 5,
                'n_trades_10m': 10,
                'n_trades_15m': 15,
                'is_incomplete': 0,
                'insufficient_flow': 0,
                'notes': '',
            }
            insert_open_snapshot(db_path, snapshot)
            insert_open_snapshot(db_path, snapshot)
            rows = list_observations(db_path)
            self.assertEqual(1, len(rows))
            self.assertEqual('w1', rows[0]['window_id'])

    def test_open_does_not_overwrite_existing_close(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / 'observations.db'
            insert_open_snapshot(db_path, {
                'window_id': 'w1', 'ts_open': '2026-05-25T06:00:00Z', 'price_to_beat': 65000.0,
                'pm_up_price_open': 0.51, 'deribit_index_open': 65010.0,
                'D_5m_otm_dotm': 1.0, 'D_10m_otm_dotm': 2.0, 'D_15m_otm_dotm': 3.0,
                'D_5m_atm': 0.5, 'D_10m_atm': 0.6, 'D_15m_atm': 0.7,
                'V_5m_otm_dotm': 1.5, 'V_10m_otm_dotm': 2.5, 'V_15m_otm_dotm': 3.5,
                'n_trades_5m': 5, 'n_trades_10m': 10, 'n_trades_15m': 15,
                'is_incomplete': 0, 'insufficient_flow': 0, 'notes': 'open',
            })
            update_close_snapshot(db_path, 'w1', {
                'ts_close': '2026-05-25T06:15:00Z',
                'deribit_index_close': 65020.0,
                'chainlink_close': 65018.0,
                'outcome': 'Up',
                'pm_up_price_close': 0.83,
                'is_incomplete': 0,
                'insufficient_flow': 0,
                'notes': 'closed cleanly',
            })
            insert_open_snapshot(db_path, {
                'window_id': 'w1', 'ts_open': '2026-05-25T06:00:00Z', 'price_to_beat': 65100.0,
                'pm_up_price_open': 0.61, 'deribit_index_open': 65110.0,
                'D_5m_otm_dotm': 9.0, 'D_10m_otm_dotm': 9.0, 'D_15m_otm_dotm': 9.0,
                'D_5m_atm': 9.0, 'D_10m_atm': 9.0, 'D_15m_atm': 9.0,
                'V_5m_otm_dotm': 9.0, 'V_10m_otm_dotm': 9.0, 'V_15m_otm_dotm': 9.0,
                'n_trades_5m': 99, 'n_trades_10m': 99, 'n_trades_15m': 99,
                'is_incomplete': 1, 'insufficient_flow': 1, 'notes': 'retry open',
            })
            row = fetch_observation(db_path, 'w1')
            assert row is not None
            self.assertEqual('2026-05-25T06:15:00Z', row['ts_close'])
            self.assertEqual('Up', row['outcome'])
            self.assertEqual(65018.0, row['chainlink_close'])
            self.assertEqual('closed cleanly', row['notes'])
            self.assertEqual(15, row['n_trades_15m'])

    def test_close_updates_correct_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / 'observations.db'
            for window_id, ts_open in [('w1', '2026-05-25T06:00:00Z'), ('w2', '2026-05-25T06:15:00Z')]:
                insert_open_snapshot(db_path, {
                    'window_id': window_id, 'ts_open': ts_open, 'price_to_beat': 65000.0,
                    'pm_up_price_open': 0.51, 'deribit_index_open': 65010.0,
                    'D_5m_otm_dotm': 1.0, 'D_10m_otm_dotm': 2.0, 'D_15m_otm_dotm': 3.0,
                    'D_5m_atm': 0.5, 'D_10m_atm': 0.6, 'D_15m_atm': 0.7,
                    'V_5m_otm_dotm': 1.5, 'V_10m_otm_dotm': 2.5, 'V_15m_otm_dotm': 3.5,
                    'n_trades_5m': 5, 'n_trades_10m': 10, 'n_trades_15m': 15,
                    'is_incomplete': 0, 'insufficient_flow': 0, 'notes': '',
                })
            update_close_snapshot(db_path, 'w2', {
                'ts_close': '2026-05-25T06:30:00Z',
                'deribit_index_close': 65030.0,
                'chainlink_close': 65028.0,
                'outcome': 'Up',
                'pm_up_price_close': 0.77,
                'is_incomplete': 0,
                'insufficient_flow': 0,
                'notes': 'closed w2',
            })
            row1 = fetch_observation(db_path, 'w1')
            row2 = fetch_observation(db_path, 'w2')
            assert row1 is not None and row2 is not None
            self.assertIsNone(row1['ts_close'])
            self.assertEqual('2026-05-25T06:30:00Z', row2['ts_close'])

    def test_list_observations_orders_by_ts_open(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / 'observations.db'
            for window_id, ts_open in [('w2', '2026-05-25T06:15:00Z'), ('w1', '2026-05-25T06:00:00Z')]:
                insert_open_snapshot(db_path, {
                    'window_id': window_id, 'ts_open': ts_open, 'price_to_beat': 65000.0,
                    'pm_up_price_open': 0.51, 'deribit_index_open': 65010.0,
                    'D_5m_otm_dotm': 1.0, 'D_10m_otm_dotm': 2.0, 'D_15m_otm_dotm': 3.0,
                    'D_5m_atm': 0.5, 'D_10m_atm': 0.6, 'D_15m_atm': 0.7,
                    'V_5m_otm_dotm': 1.5, 'V_10m_otm_dotm': 2.5, 'V_15m_otm_dotm': 3.5,
                    'n_trades_5m': 5, 'n_trades_10m': 10, 'n_trades_15m': 15,
                    'is_incomplete': 0, 'insufficient_flow': 0, 'notes': '',
                })
            rows = list_observations(db_path)
            self.assertEqual(['w1', 'w2'], [row['window_id'] for row in rows])


if __name__ == '__main__':
    unittest.main()
