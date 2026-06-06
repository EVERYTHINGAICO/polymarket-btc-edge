"""Sidecar collector for forward-only missing data.

Runs beside the existing continuous logger. It does not touch orders, keys,
wallets, PROJECT_DESIGN.md, or .env.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.chainlink_feed import fetch_chainlink_btc_usd_close_fast
from src.db import insert_intrawindow_sample
from src.forward_market_data import (
    fetch_binance_btcusdt_price,
    initialize_forward_market_data_tables,
    insert_orderbook_snapshot,
    insert_spot_price,
    now_ms,
    parse_book_top,
    utc_now_iso,
)
from src.polymarket_feed import PolymarketReadOnlyClient, current_open_epoch, midpoint_to_float


def emit(log_path: Path, event: str, **payload) -> None:
    record = {"ts_utc": utc_now_iso(), "event": event, **payload}
    line = json.dumps(record, ensure_ascii=False)
    print(line, flush=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def sample_spot(db_path: Path, log_path: Path, *, use_chainlink: bool, use_binance: bool) -> None:
    ts_ms = now_ms()
    if use_chainlink:
        price, diag = fetch_chainlink_btc_usd_close_fast()
        if price is not None:
            insert_spot_price(
                db_path,
                timestamp_ms=ts_ms,
                asset="BTC",
                source="chainlink_polygon_latest",
                price=price,
                captured_at_ms=now_ms(),
            )
            emit(log_path, "spot_sample_ok", source="chainlink_polygon_latest", asset="BTC", price=price)
        else:
            emit(log_path, "spot_sample_failed", source="chainlink_polygon_latest", diag=diag)
    if use_binance:
        price = fetch_binance_btcusdt_price()
        if price is not None:
            insert_spot_price(
                db_path,
                timestamp_ms=ts_ms,
                asset="BTC",
                source="binance_btcusdt",
                price=price,
                captured_at_ms=now_ms(),
            )
            emit(log_path, "spot_sample_ok", source="binance_btcusdt", asset="BTC", price=price)
        else:
            emit(log_path, "spot_sample_failed", source="binance_btcusdt")


def sample_orderbook_and_midpoint(db_path: Path, log_path: Path, client: PolymarketReadOnlyClient, *, orderbook_max_seconds: int) -> None:
    ts = time.time()
    open_epoch = current_open_epoch(ts)
    t_seconds = int(ts - open_epoch)
    if t_seconds < 0 or t_seconds > orderbook_max_seconds:
        return
    try:
        market = client.fetch_market_by_open_epoch(open_epoch)
    except Exception as exc:
        emit(log_path, "orderbook_discovery_failed", open_epoch=open_epoch, error=repr(exc))
        return
    sampled_at = utc_now_iso()
    timestamp_ms = now_ms()
    try:
        up_mid = midpoint_to_float(client.fetch_midpoint(market.up_token_id))
        insert_intrawindow_sample(db_path, market.window_id, t_seconds, up_mid, sampled_at)
    except Exception as exc:
        emit(log_path, "intrawindow_sample_failed", window_id=market.window_id, t_seconds=t_seconds, error=repr(exc))
    try:
        up_top = parse_book_top(client.fetch_book(market.up_token_id))
        down_top = parse_book_top(client.fetch_book(market.down_token_id))
        insert_orderbook_snapshot(
            db_path,
            {
                "window_id": market.window_id,
                "t_seconds": t_seconds,
                "timestamp_ms": timestamp_ms,
                "sampled_at_utc": sampled_at,
                "up_token_id": market.up_token_id,
                "down_token_id": market.down_token_id,
                "best_bid_up": up_top.best_bid,
                "best_ask_up": up_top.best_ask,
                "best_bid_down": down_top.best_bid,
                "best_ask_down": down_top.best_ask,
                "bid_size_up": up_top.bid_size,
                "ask_size_up": up_top.ask_size,
                "bid_size_down": down_top.bid_size,
                "ask_size_down": down_top.ask_size,
            },
        )
        emit(log_path, "orderbook_sample_ok", window_id=market.window_id, t_seconds=t_seconds, best_ask_up=up_top.best_ask, best_ask_down=down_top.best_ask)
    except Exception as exc:
        emit(log_path, "orderbook_sample_failed", window_id=market.window_id, t_seconds=t_seconds, error=repr(exc))


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect forward-only spot/orderbook/high-frequency midpoint data.")
    parser.add_argument("--db", required=True)
    parser.add_argument("--log-path", default="reports/live/forward_market_data.log")
    parser.add_argument("--spot-interval-seconds", type=float, default=60.0)
    parser.add_argument("--orderbook-interval-seconds", type=float, default=5.0)
    parser.add_argument("--orderbook-max-seconds", type=int, default=120)
    parser.add_argument("--run-seconds", type=float, default=None, help="Optional bounded run for smoke/testing.")
    parser.add_argument("--no-chainlink", action="store_true")
    parser.add_argument("--no-binance", action="store_true")
    parser.add_argument("--no-orderbook", action="store_true")
    args = parser.parse_args()

    db_path = Path(args.db)
    log_path = Path(args.log_path)
    if not db_path.exists():
        print(f"ERROR: DB no existe: {db_path}", file=sys.stderr)
        return 1
    initialize_forward_market_data_tables(db_path)
    client = PolymarketReadOnlyClient()
    started = time.time()
    next_spot = 0.0
    next_orderbook = 0.0
    emit(
        log_path,
        "forward_market_data_collector_started",
        db=str(db_path),
        spot_interval_seconds=args.spot_interval_seconds,
        orderbook_interval_seconds=args.orderbook_interval_seconds,
        orderbook_max_seconds=args.orderbook_max_seconds,
    )
    try:
        while True:
            now = time.time()
            if args.run_seconds is not None and (now - started) >= args.run_seconds:
                break
            if now >= next_spot:
                sample_spot(db_path, log_path, use_chainlink=not args.no_chainlink, use_binance=not args.no_binance)
                next_spot = now + max(1.0, args.spot_interval_seconds)
            if not args.no_orderbook and now >= next_orderbook:
                sample_orderbook_and_midpoint(db_path, log_path, client, orderbook_max_seconds=args.orderbook_max_seconds)
                next_orderbook = now + max(1.0, args.orderbook_interval_seconds)
            time.sleep(0.5)
    except KeyboardInterrupt:
        emit(log_path, "forward_market_data_collector_keyboard_interrupt")
    finally:
        emit(log_path, "forward_market_data_collector_stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
