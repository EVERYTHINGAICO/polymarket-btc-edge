from __future__ import annotations

import json
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.db import fetch_observation, get_observations_columns, initialize_database, connect
from src.deribit_feed import collect_live_deribit_trades, deribit_ws_healthcheck, fetch_deribit_index_price
from src.logger import CloseContext, OpenContext, RuntimeStatus, SupervisedLoggerRuntime
from src.chainlink_feed import fetch_chainlink_btc_usd_close
from src.intrawindow_sampler import IntrawindowSampler
from src.polymarket_feed import ActiveWindowSnapshot, PolymarketReadOnlyClient, current_open_epoch, midpoint_to_float, resolve_outcome_with_retries
from src.signal import RollingSignalBuffer, SignalTrade


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def _sleep_until(epoch_seconds: int) -> None:
    while True:
        now = time.time()
        remaining = epoch_seconds - now
        if remaining <= 0:
            return
        time.sleep(min(remaining, 1.0))


def _to_signal_trade(trade) -> SignalTrade:
    return SignalTrade(
        timestamp_ms=trade.timestamp_ms,
        direction=trade.direction,
        option_type=trade.option_type,
        moneyness=trade.moneyness,
        amount=trade.amount,
        delta_abs=trade.delta_abs,
    )


def _append_note(notes: list[str], value: str | None) -> None:
    if value and value not in notes:
        notes.append(value)


def export_row_sample(db_path: Path, window_id: str) -> dict:
    row = fetch_observation(db_path, window_id)
    with connect(db_path) as connection:
        columns = get_observations_columns(connection)
    return {'row': row, 'columns': columns}


def run_one_window_pilot(db_path: Path, log_path: Path, *, with_trajectory: bool = False, interval_seconds: int = 30) -> dict:
    client = PolymarketReadOnlyClient()
    runtime = SupervisedLoggerRuntime(db_path, log_path)
    initialize_database(db_path)

    result: dict = {
        'started_at_utc': utc_now(),
        'db_path': str(db_path.relative_to(ROOT)),
        'log_path': str(log_path.relative_to(ROOT)),
    }

    market = client.discover_candidate_market()
    result['market'] = asdict(market)
    try:
        result['deribit_ws_healthcheck'] = deribit_ws_healthcheck()
        if not result['deribit_ws_healthcheck'].get('ok'):
            result['status'] = 'BLOCKED'
            result['reason'] = f"Deribit websocket healthcheck returned non-ok payload: {result['deribit_ws_healthcheck']}"
            return result
    except Exception as exc:
        result['deribit_ws_healthcheck'] = {'ok': False, 'error': repr(exc)}
        result['status'] = 'BLOCKED'
        result['reason'] = f'Deribit websocket healthcheck failed: {exc}'
        return result

    now = int(time.time())

    if market.open_epoch_seconds <= now:
        next_open_epoch = current_open_epoch(now) + 900
        next_market = client.fetch_market_by_open_epoch(next_open_epoch)
        if next_market.open_epoch_seconds <= now:
            result['status'] = 'READY_FOR_NEXT_WINDOW'
            result['reason'] = 'No future window with enough lead time was found.'
            return result
        market = next_market
        result['market'] = asdict(market)

    close_epoch = market.open_epoch_seconds + 900
    if close_epoch <= int(time.time()):
        result['status'] = 'BLOCKED'
        result['reason'] = 'Selected market is already closed.'
        return result

    result['selected_window_id'] = market.window_id
    result['ts_open'] = market.ts_open
    result['ts_close'] = market.ts_close

    health = client.healthcheck_market(market)
    result['healthcheck_pre_open'] = asdict(health)
    if any(issue for issue in health.issues if issue not in {'midpoint_failed', 'book_failed', 'price_buy_failed', 'price_sell_failed'}):
        result['status'] = 'BLOCKED'
        result['reason'] = f'Pre-open healthcheck failed: {health.issues}'
        return result

    prep_seconds = max(0, market.open_epoch_seconds - int(time.time()))
    if prep_seconds > 0:
        warmup_duration = min(900, prep_seconds)
        pre_capture = collect_live_deribit_trades(duration_seconds=warmup_duration)
        pre_trades, pre_counts = pre_capture.trades, pre_capture.counts
    else:
        pre_trades, pre_counts = [], {'messages': 0, 'normalized_trades': 0, 'skipped': 0}
    result['pre_window_deribit'] = {'counts': pre_counts}

    _sleep_until(market.open_epoch_seconds)

    health_at_open = client.healthcheck_market(market)
    result['healthcheck_at_open'] = asdict(health_at_open)
    if health_at_open.issues:
        result['status'] = 'BLOCKED'
        result['reason'] = f'Open healthcheck failed: {health_at_open.issues}'
        return result

    effective_price_to_beat = market.price_to_beat if market.price_to_beat is not None else fetch_chainlink_btc_usd_close()
    market = type(market)(**{**asdict(market), 'pm_up_price_open': midpoint_to_float(client.fetch_midpoint(market.up_token_id)), 'price_to_beat': effective_price_to_beat})

    signal_buffer = RollingSignalBuffer()
    for trade in pre_trades:
        signal_buffer.add_trade(_to_signal_trade(trade))
    signal_buffer.prune(market.open_epoch_seconds * 1000)

    deribit_index_open = fetch_deribit_index_price()
    runtime_status = RuntimeStatus(ok=True, is_incomplete=False, notes='')
    open_snapshot = runtime.open_window(
        OpenContext(
            window=ActiveWindowSnapshot(
                window_id=market.window_id,
                ts_open=market.ts_open,
                price_to_beat=market.price_to_beat,
                pm_up_price_open=market.pm_up_price_open,
            ),
            deribit_index_open=deribit_index_open,
            signal_timestamp_ms=market.open_epoch_seconds * 1000,
        ),
        signal_buffer,
        min_trades=1,
        runtime_status=runtime_status,
    )
    result['open_snapshot'] = open_snapshot

    sampler: IntrawindowSampler | None = None
    if with_trajectory:
        sampler = IntrawindowSampler(
            db_path=db_path,
            client=client,
            window_id=market.window_id,
            up_token_id=market.up_token_id,
            open_epoch_seconds=market.open_epoch_seconds,
            interval_seconds=interval_seconds,
        )
        sampler.start()

    try:
        window_duration = max(1, market.open_epoch_seconds + 900 - int(time.time()))
        window_capture = collect_live_deribit_trades(duration_seconds=window_duration)
        window_trades, window_counts = window_capture.trades, window_capture.counts
        for trade in window_trades:
            signal_buffer.add_trade(_to_signal_trade(trade))
        result['window_deribit'] = {'counts': window_counts}

        deribit_index_close = fetch_deribit_index_price()
        notes: list[str] = []
        if market.price_to_beat is None:
            _append_note(notes, 'missing_price_to_beat')
        pm_up_price_close = None
        try:
            pm_up_price_close = midpoint_to_float(client.fetch_midpoint(market.up_token_id))
        except Exception:
            _append_note(notes, 'missing_pm_up_price_close')

        outcome_override, resolution_payload = resolve_outcome_with_retries(client, market.slug)
        if outcome_override is None:
            _append_note(notes, 'missing_outcome_authority')

        chainlink_close = fetch_chainlink_btc_usd_close()
        if chainlink_close is None:
            _append_note(notes, 'chainlink_close_unavailable')

        if sampler is not None:
            sampler.stop()
            result['trajectory_samples'] = sampler.samples_taken
            result['trajectory_errors'] = sampler.errors

        close_snapshot = runtime.close_window(
            CloseContext(
                window_id=market.window_id,
                ts_close=market.ts_close,
                deribit_index_close=deribit_index_close,
                chainlink_close=chainlink_close,
                pm_up_price_close=pm_up_price_close,
            ),
            price_to_beat=market.price_to_beat,
            outcome_override=outcome_override,
            is_incomplete=(outcome_override is None),
            notes=','.join(notes),
            insufficient_flow=bool(window_counts.get('classified_trades', 0) == 0),
        )
        result['close_snapshot'] = close_snapshot
        result['resolution_payload'] = resolution_payload
    except Exception as exc:
        if sampler is not None:
            try:
                sampler.stop()
                result['trajectory_samples'] = sampler.samples_taken
                result['trajectory_errors'] = sampler.errors
            except Exception:
                pass
        cleanup_parts = ['runtime_error', 'missing_close_snapshot', 'deribit_ws_timeout']
        if market.price_to_beat is None:
            cleanup_parts.append('missing_price_to_beat')
        cleanup_parts.append('missing_outcome_authority')
        cleanup_notes = ','.join(cleanup_parts)
        cleaned = runtime.cleanup_post_open_failure(market.window_id, notes=cleanup_notes, insufficient_flow=True)
        result['status'] = 'FAIL'
        result['reason'] = repr(exc)
        result['cleanup_row'] = cleaned
        result['row_kind'] = 'INCOMPLETE_REAL'
        result['finished_at_utc'] = utc_now()
        return result

    sample = export_row_sample(db_path, market.window_id)
    row = sample['row']
    result['columns'] = sample['columns']
    result['row'] = row
    result['status'] = 'PASS'
    result['row_kind'] = 'REAL' if row and row.get('is_incomplete') == 0 else 'INCOMPLETE_REAL'
    result['finished_at_utc'] = utc_now()
    return result


if __name__ == '__main__':
    out = run_one_window_pilot(ROOT / 'data' / 'observations.db', ROOT / 'reports' / 'live' / 'one_window_pilot.log')
    print(json.dumps(out, indent=2, ensure_ascii=False))
