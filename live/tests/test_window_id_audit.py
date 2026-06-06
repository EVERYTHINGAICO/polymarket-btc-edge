from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.window_id_audit import audit_window_id, build_audit
from src.db import insert_open_snapshot


def open_snapshot(window_id: str, ts_open: str) -> dict:
    return {
        "window_id": window_id,
        "ts_open": ts_open,
        "price_to_beat": None,
        "pm_up_price_open": 0.51,
        "deribit_index_open": 76000.0,
        "D_5m_otm_dotm": 0.0,
        "D_10m_otm_dotm": 0.0,
        "D_15m_otm_dotm": 0.0,
        "D_5m_atm": 0.0,
        "D_10m_atm": 0.0,
        "D_15m_atm": 0.0,
        "V_5m_otm_dotm": 0.0,
        "V_10m_otm_dotm": 0.0,
        "V_15m_otm_dotm": 0.0,
        "n_trades_5m": 0,
        "n_trades_10m": 0,
        "n_trades_15m": 0,
        "is_incomplete": 0,
        "insufficient_flow": 0,
        "notes": "",
    }


class WindowIdAuditTests(unittest.TestCase):
    def test_validates_canonical_10_digit_open_epoch_window_id(self) -> None:
        result = audit_window_id(
            {
                "window_id": "btc-updown-15m-1779828300",
                "ts_open": "2026-05-26T20:45:00Z",
            }
        )
        self.assertTrue(result["valid"])
        self.assertEqual("VALID", result["status"])
        self.assertEqual(1779828300, result["open_epoch_seconds"])
        self.assertEqual("2026-05-26T20:45:00Z", result["expected_ts_open"])
        self.assertEqual([], result["issues"])

    def test_rejects_dropped_zero_epoch_typo(self) -> None:
        result = audit_window_id(
            {
                "window_id": "btc-updown-15m-177982830",
                "ts_open": "2026-05-26T20:45:00Z",
            }
        )
        self.assertFalse(result["valid"])
        self.assertEqual("INVALID", result["status"])
        self.assertIn("window_id_not_btc_updown_15m_10_digit_epoch", result["issues"])

    def test_skips_demo_window_ids_without_failing_real_audit(self) -> None:
        result = audit_window_id(
            {
                "window_id": "demo-window",
                "ts_open": "2026-05-25T20:30:00Z",
            }
        )
        self.assertFalse(result["valid"])
        self.assertEqual("SKIPPED", result["status"])
        self.assertIn("non_polymarket_btc_15m_window", result["issues"])

    def test_rejects_ts_open_mismatch(self) -> None:
        result = audit_window_id(
            {
                "window_id": "btc-updown-15m-1779828300",
                "ts_open": "2026-05-26T21:00:00Z",
            }
        )
        self.assertFalse(result["valid"])
        self.assertEqual("INVALID", result["status"])
        self.assertIn("ts_open_mismatch", result["issues"])

    def test_build_audit_reads_observations_in_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "observations.db"
            insert_open_snapshot(db_path, open_snapshot("btc-updown-15m-1779828300", "2026-05-26T20:45:00Z"))
            insert_open_snapshot(db_path, open_snapshot("btc-updown-15m-177982920", "2026-05-26T21:00:00Z"))

            audit = build_audit(db_path)

        self.assertEqual(2, audit["row_count"])
        self.assertEqual(1, audit["valid_count"])
        self.assertEqual(1, audit["invalid_count"])
        self.assertEqual(0, audit["skipped_count"])
        self.assertEqual("btc-updown-15m-1779828300", audit["rows"][0]["window_id"])
        self.assertEqual("btc-updown-15m-177982920", audit["rows"][1]["window_id"])


if __name__ == "__main__":
    unittest.main()
