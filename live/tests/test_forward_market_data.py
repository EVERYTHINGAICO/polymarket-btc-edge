from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from src.forward_market_data import (
    initialize_forward_market_data_tables,
    insert_orderbook_snapshot,
    insert_spot_price,
    parse_book_top,
)


class ForwardMarketDataTests(unittest.TestCase):
    def test_forward_tables_are_additive(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Path(tmpdir) / "observations.db"
            initialize_forward_market_data_tables(db)
            insert_spot_price(db, timestamp_ms=1, asset="BTC", source="chainlink_polygon_latest", price=65000.0, captured_at_ms=2)
            insert_orderbook_snapshot(
                db,
                {
                    "window_id": "btc-updown-15m-1",
                    "t_seconds": 10,
                    "timestamp_ms": 3,
                    "sampled_at_utc": "2026-06-03T00:00:10Z",
                    "up_token_id": "up",
                    "down_token_id": "down",
                    "best_bid_up": 0.49,
                    "best_ask_up": 0.51,
                    "best_bid_down": 0.48,
                    "best_ask_down": 0.52,
                    "bid_size_up": 100.0,
                    "ask_size_up": 200.0,
                    "bid_size_down": 300.0,
                    "ask_size_down": 400.0,
                },
            )
            conn = sqlite3.connect(db)
            try:
                spot_count = conn.execute("SELECT COUNT(*) FROM spot_prices").fetchone()[0]
                book_count = conn.execute("SELECT COUNT(*) FROM orderbook").fetchone()[0]
            finally:
                conn.close()
        self.assertEqual(1, spot_count)
        self.assertEqual(1, book_count)

    def test_parse_book_top_uses_max_bid_and_min_ask(self) -> None:
        top = parse_book_top(
            {
                "bids": [{"price": "0.40", "size": "10"}, {"price": "0.45", "size": "20"}],
                "asks": [{"price": "0.60", "size": "30"}, {"price": "0.55", "size": "40"}],
            }
        )
        self.assertEqual(0.45, top.best_bid)
        self.assertEqual(20.0, top.bid_size)
        self.assertEqual(0.55, top.best_ask)
        self.assertEqual(40.0, top.ask_size)


if __name__ == "__main__":
    unittest.main()
