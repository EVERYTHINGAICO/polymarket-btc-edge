from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from src.analysis.forward_rules import evaluate_forward_rules


CONFIG = {
    "config_version": "test",
    "frozen_at_utc": "2026-06-03T00:00:00Z",
    "verdict_ceiling_without_orderbook": "proxy estadistico, no edge ejecutable",
    "data": {
        "forward_start_after_ts_open_utc": "2026-06-03T00:00:00Z",
        "filter_outcome_in": ["Up", "Down"],
        "filter_is_incomplete": 0,
        "exclude_window_id": "demo-window",
        "max_deribit_staleness_seconds": 60,
        "entry_window_seconds": 5,
        "min_n_for_report": 1000,
        "additional_days_for_report": 7,
    },
    "rules": [
        {"id": "RULE_A", "lookback_min": 1, "gap_min": 0, "threshold": 0.0005, "entry_t": 30}
    ],
}


class ForwardRulesTests(unittest.TestCase):
    def test_evaluates_only_frozen_rule_without_grid(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Path(tmpdir) / "observations.db"
            conn = sqlite3.connect(db)
            try:
                conn.execute(
                    """
                    CREATE TABLE observations (
                        window_id TEXT PRIMARY KEY,
                        ts_open TEXT,
                        outcome TEXT,
                        pm_up_price_open REAL,
                        is_incomplete INTEGER
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE observations_intrawindow (
                        window_id TEXT,
                        t_seconds INTEGER,
                        pm_up_price REAL,
                        sampled_at_utc TEXT
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE deribit_trades_raw (
                        trade_id TEXT PRIMARY KEY,
                        timestamp_ms INTEGER,
                        index_price REAL
                    )
                    """
                )
                conn.execute(
                    "INSERT INTO observations VALUES (?, ?, ?, ?, ?)",
                    ("btc-updown-15m-1780445700", "2026-06-03T00:15:00Z", "Up", 0.50, 0),
                )
                conn.execute(
                    "INSERT INTO observations_intrawindow VALUES (?, ?, ?, ?)",
                    ("btc-updown-15m-1780445700", 30, 0.52, "2026-06-03T00:15:30Z"),
                )
                # lag at 00:14:00 and signal at 00:15:00, both exactly fresh.
                conn.execute("INSERT INTO deribit_trades_raw VALUES (?, ?, ?)", ("lag", 1780445640000, 100.0))
                conn.execute("INSERT INTO deribit_trades_raw VALUES (?, ?, ?)", ("signal", 1780445700000, 101.0))
                conn.commit()
            finally:
                conn.close()
            result = evaluate_forward_rules(db, CONFIG)
        self.assertEqual("BTC_FORWARD_FROZEN_RULES_ONLY", result["analysis_type"])
        self.assertEqual(1, len(result["rules"]))
        rule = result["rules"][0]
        self.assertEqual("RULE_A", rule["rule_id"])
        self.assertEqual(1, rule["n"])
        self.assertGreater(rule["mean_net_pnl"], 0)


if __name__ == "__main__":
    unittest.main()
