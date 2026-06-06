"""Sidecar data capture for forward-only research.

Adds the missing raw data needed to move beyond proxy analysis:
- spot/Chainlink/Binance price samples
- Polymarket orderbook samples

All external calls are public read-only. No signing, wallets, secrets or orders.
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


SPOT_TABLE = "spot_prices"
ORDERBOOK_TABLE = "orderbook"

SPOT_SCHEMA_SQL = f"""
CREATE TABLE IF NOT EXISTS {SPOT_TABLE} (
    timestamp_ms INTEGER NOT NULL,
    asset TEXT NOT NULL,
    source TEXT NOT NULL,
    price REAL NOT NULL,
    captured_at_ms INTEGER NOT NULL,
    PRIMARY KEY (source, asset, timestamp_ms)
);
CREATE INDEX IF NOT EXISTS idx_spot_prices_asset_ts
ON {SPOT_TABLE}(asset, timestamp_ms);
""".strip()

ORDERBOOK_SCHEMA_SQL = f"""
CREATE TABLE IF NOT EXISTS {ORDERBOOK_TABLE} (
    window_id TEXT NOT NULL,
    t_seconds INTEGER NOT NULL,
    timestamp_ms INTEGER NOT NULL,
    sampled_at_utc TEXT NOT NULL,
    up_token_id TEXT,
    down_token_id TEXT,
    best_bid_up REAL,
    best_ask_up REAL,
    best_bid_down REAL,
    best_ask_down REAL,
    bid_size_up REAL,
    ask_size_up REAL,
    bid_size_down REAL,
    ask_size_down REAL,
    PRIMARY KEY (window_id, t_seconds)
);
CREATE INDEX IF NOT EXISTS idx_orderbook_window_id
ON {ORDERBOOK_TABLE}(window_id);
CREATE INDEX IF NOT EXISTS idx_orderbook_timestamp_ms
ON {ORDERBOOK_TABLE}(timestamp_ms);
""".strip()


@dataclass(frozen=True)
class BookTop:
    best_bid: float | None
    best_ask: float | None
    bid_size: float | None
    ask_size: float | None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def now_ms() -> int:
    return int(time.time() * 1000)


def initialize_forward_market_data_tables(db_path: str | Path) -> None:
    conn = sqlite3.connect(db_path, timeout=10.0)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SPOT_SCHEMA_SQL)
        conn.executescript(ORDERBOOK_SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()


def insert_spot_price(db_path: str | Path, *, timestamp_ms: int, asset: str, source: str, price: float, captured_at_ms: int | None = None) -> None:
    initialize_forward_market_data_tables(db_path)
    conn = sqlite3.connect(db_path, timeout=10.0)
    try:
        conn.execute(
            f"""
            INSERT OR IGNORE INTO {SPOT_TABLE}
                (timestamp_ms, asset, source, price, captured_at_ms)
            VALUES (?, ?, ?, ?, ?)
            """,
            (int(timestamp_ms), asset, source, float(price), int(captured_at_ms or now_ms())),
        )
        conn.commit()
    finally:
        conn.close()


def insert_orderbook_snapshot(db_path: str | Path, snapshot: dict[str, Any]) -> None:
    initialize_forward_market_data_tables(db_path)
    columns = [
        "window_id",
        "t_seconds",
        "timestamp_ms",
        "sampled_at_utc",
        "up_token_id",
        "down_token_id",
        "best_bid_up",
        "best_ask_up",
        "best_bid_down",
        "best_ask_down",
        "bid_size_up",
        "ask_size_up",
        "bid_size_down",
        "ask_size_down",
    ]
    placeholders = ", ".join("?" for _ in columns)
    assignments = ", ".join(f"{column}=excluded.{column}" for column in columns if column not in {"window_id", "t_seconds"})
    conn = sqlite3.connect(db_path, timeout=10.0)
    try:
        conn.execute(
            f"""
            INSERT INTO {ORDERBOOK_TABLE} ({", ".join(columns)})
            VALUES ({placeholders})
            ON CONFLICT(window_id, t_seconds) DO UPDATE SET {assignments}
            """,
            [snapshot.get(column) for column in columns],
        )
        conn.commit()
    finally:
        conn.close()


def _parse_float(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_book_top(payload: dict[str, Any]) -> BookTop:
    """Parse CLOB book top robustly from bids/asks arrays."""
    bids = payload.get("bids") if isinstance(payload, dict) else None
    asks = payload.get("asks") if isinstance(payload, dict) else None

    def _pairs(rows: Any) -> list[tuple[float, float | None]]:
        out: list[tuple[float, float | None]] = []
        if not isinstance(rows, list):
            return out
        for row in rows:
            if not isinstance(row, dict):
                continue
            price = _parse_float(row.get("price"))
            size = _parse_float(row.get("size"))
            if price is not None:
                out.append((price, size))
        return out

    bid_pairs = _pairs(bids)
    ask_pairs = _pairs(asks)
    best_bid_pair = max(bid_pairs, key=lambda item: item[0]) if bid_pairs else (None, None)
    best_ask_pair = min(ask_pairs, key=lambda item: item[0]) if ask_pairs else (None, None)
    return BookTop(
        best_bid=best_bid_pair[0],
        best_ask=best_ask_pair[0],
        bid_size=best_bid_pair[1],
        ask_size=best_ask_pair[1],
    )


def fetch_binance_btcusdt_price(timeout_seconds: float = 5.0) -> float | None:
    request = Request(
        "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT",
        headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None
    price = payload.get("price") if isinstance(payload, dict) else None
    return _parse_float(price)
