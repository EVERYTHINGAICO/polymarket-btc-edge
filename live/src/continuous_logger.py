"""Continuous live logger (Fase 6 modo continuo).

Mantiene una sola conexión Deribit WS, alimentando un RollingSignalBuffer
compartido. Un scheduler alineado al reloj UTC abre/cierra ventanas
Polymarket cada 15 min. Outcome de gamma se resuelve en background.

Read-only sobre Polymarket/Deribit/Chainlink. Sin signing, sin wallets.
Cumple PROJECT_DESIGN §0 (registra, no opera).
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

from src.chainlink_feed import fetch_chainlink_btc_usd_close, fetch_chainlink_btc_usd_close_fast
from src.db import update_outcome
from src.deribit_feed import fetch_deribit_index_price, stream_deribit_trades
from src.intrawindow_sampler import IntrawindowSampler
from src.logger import CloseContext, OpenContext, RuntimeStatus, SupervisedLoggerRuntime
from src.polymarket_feed import (
    ActiveWindowSnapshot,
    PolymarketReadOnlyClient,
    midpoint_to_float,
    resolve_outcome_with_retries,
)
from src.signal import RollingSignalBuffer, SignalTrade


def _normalized_to_signal(ntrade) -> SignalTrade:
    return SignalTrade(
        timestamp_ms=ntrade.timestamp_ms,
        direction=ntrade.direction,
        option_type=ntrade.option_type,
        moneyness=ntrade.moneyness,
        amount=ntrade.amount,
        delta_abs=ntrade.delta_abs,
    )


WINDOW_DURATION_SECONDS = 900


class ContinuousLogger:
    def __init__(
        self,
        db_path: str | Path,
        log_path: str | Path,
        *,
        interval_seconds: int = 30,
        with_trajectory: bool = True,
        resolver_poll_seconds: int = 60,
        resolver_giveup_seconds: int = 1800,
    ) -> None:
        self.db_path = Path(db_path)
        self.log_path = Path(log_path)
        self.interval_seconds = int(interval_seconds)
        self.with_trajectory = bool(with_trajectory)
        self.resolver_poll_seconds = int(resolver_poll_seconds)
        self.resolver_giveup_seconds = int(resolver_giveup_seconds)
        self.buffer = RollingSignalBuffer()
        self.client = PolymarketReadOnlyClient()
        self.runtime = SupervisedLoggerRuntime(self.db_path, self.log_path)
        self.stop_event = threading.Event()
        self.pending_lock = threading.Lock()
        self.pending_resolution: dict[str, dict] = {}
        self.active_window: dict | None = None
        self.active_sampler: IntrawindowSampler | None = None
        self._threads: list[threading.Thread] = []

    def _emit(self, event: str, **payload) -> None:
        try:
            self.runtime.json_logger.emit(event, **payload)
        except Exception:
            pass
        try:
            ts = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
            extras = ' '.join(f'{k}={v}' for k, v in payload.items())
            print(f'[{ts}] {event} {extras}', flush=True)
        except Exception:
            pass

    def start(self) -> None:
        t_deribit = threading.Thread(target=self._deribit_loop, daemon=True, name='deribit_stream')
        t_resolver = threading.Thread(target=self._resolver_loop, daemon=True, name='outcome_resolver')
        t_deribit.start()
        t_resolver.start()
        self._threads = [t_deribit, t_resolver]
        self._emit('continuous_logger_started', with_trajectory=self.with_trajectory, interval_seconds=self.interval_seconds)
        try:
            self._scheduler_loop()
        finally:
            self.stop()

    def stop(self) -> None:
        if self.stop_event.is_set():
            return
        self.stop_event.set()
        sampler = self.active_sampler
        if sampler is not None:
            try:
                sampler.stop()
            except Exception:
                pass
        self._emit('continuous_logger_stop_requested')

    def _deribit_loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                stream_deribit_trades(
                    on_trade=self._on_deribit_trade,
                    stop_event=self.stop_event,
                )
            except Exception as exc:
                self._emit('deribit_stream_error', error=repr(exc))
            if self.stop_event.is_set():
                return
            self.stop_event.wait(timeout=5)

    def _on_deribit_trade(self, ntrade) -> None:
        try:
            self.buffer.add_trade(_normalized_to_signal(ntrade))
        except Exception as exc:
            self._emit('buffer_add_error', error=repr(exc))

    def _scheduler_loop(self) -> None:
        while not self.stop_event.is_set():
            now = time.time()
            next_boundary = (int(now) // WINDOW_DURATION_SECONDS + 1) * WINDOW_DURATION_SECONDS
            wait = max(0.0, next_boundary - now)
            ts_next = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(next_boundary))
            print(f'[scheduler] Esperando próximo boundary {ts_next} ({wait:.0f}s)', flush=True)
            if self.stop_event.wait(timeout=wait):
                return
            try:
                self._on_boundary(next_boundary)
            except Exception as exc:
                self._emit('boundary_error', open_epoch=next_boundary, error=repr(exc))

    def _on_boundary(self, open_epoch_seconds: int) -> None:
        if self.active_window is not None:
            self._close_active_window()
        if self.stop_event.is_set():
            return
        try:
            market = self.client.fetch_market_by_open_epoch(open_epoch_seconds)
        except Exception as exc:
            self._emit('discover_failed', open_epoch=open_epoch_seconds, error=repr(exc))
            return
        try:
            pm_up_price_open = midpoint_to_float(self.client.fetch_midpoint(market.up_token_id))
        except Exception:
            pm_up_price_open = None
        if market.price_to_beat is not None:
            price_to_beat = market.price_to_beat
        else:
            price_to_beat, _chainlink_diag = fetch_chainlink_btc_usd_close_fast()
            if price_to_beat is None:
                self._emit('chainlink_open_failed', open_epoch=open_epoch_seconds, diag=_chainlink_diag)
            else:
                self._emit('chainlink_open_ok', open_epoch=open_epoch_seconds, price=price_to_beat, winning_rpc=_chainlink_diag.get('winning_rpc'), elapsed_attempts=len(_chainlink_diag.get('attempts', [])))
        try:
            deribit_index_open = fetch_deribit_index_price()
        except Exception:
            deribit_index_open = 0.0
        self.buffer.prune(open_epoch_seconds * 1000)
        open_context = OpenContext(
            window=ActiveWindowSnapshot(
                window_id=market.window_id,
                ts_open=market.ts_open,
                price_to_beat=price_to_beat,
                pm_up_price_open=pm_up_price_open,
            ),
            deribit_index_open=deribit_index_open,
            signal_timestamp_ms=open_epoch_seconds * 1000,
        )
        try:
            snapshot = self.runtime.open_window(open_context, self.buffer, min_trades=1, runtime_status=RuntimeStatus(ok=True))
        except Exception as exc:
            self._emit('open_window_error', window_id=market.window_id, error=repr(exc))
            return
        sampler = None
        if self.with_trajectory:
            sampler = IntrawindowSampler(
                db_path=self.db_path,
                client=self.client,
                window_id=market.window_id,
                up_token_id=market.up_token_id,
                open_epoch_seconds=open_epoch_seconds,
                interval_seconds=self.interval_seconds,
            )
            sampler.start()
        self.active_sampler = sampler
        self.active_window = {
            'market': market,
            'open_epoch': open_epoch_seconds,
            'price_to_beat': price_to_beat,
            'n_trades_15m_at_open': snapshot.get('n_trades_15m', 0) if isinstance(snapshot, dict) else 0,
        }
        self._emit(
            'window_opened_continuous',
            window_id=market.window_id,
            ts_open=market.ts_open,
            price_to_beat=price_to_beat,
            pm_up_price_open=pm_up_price_open,
            deribit_index_open=deribit_index_open,
            buffer_trades=self.active_window['n_trades_15m_at_open'],
        )

    def _close_active_window(self) -> None:
        sampler = self.active_sampler
        window = self.active_window
        self.active_sampler = None
        self.active_window = None
        if sampler is not None:
            try:
                sampler.stop()
            except Exception:
                pass
        if window is None:
            return
        market = window['market']
        try:
            deribit_index_close = fetch_deribit_index_price()
        except Exception:
            deribit_index_close = None
        chainlink_close, _chainlink_close_diag = fetch_chainlink_btc_usd_close_fast()
        if chainlink_close is None:
            self._emit('chainlink_close_failed', window_id=market.window_id, diag=_chainlink_close_diag)
        else:
            self._emit('chainlink_close_ok', window_id=market.window_id, price=chainlink_close, winning_rpc=_chainlink_close_diag.get('winning_rpc'))
        try:
            pm_up_price_close = midpoint_to_float(self.client.fetch_midpoint(market.up_token_id))
        except Exception:
            pm_up_price_close = None
        try:
            self.runtime.close_window(
                CloseContext(
                    window_id=market.window_id,
                    ts_close=market.ts_close,
                    deribit_index_close=deribit_index_close,
                    chainlink_close=chainlink_close,
                    pm_up_price_close=pm_up_price_close,
                ),
                price_to_beat=window['price_to_beat'],
                outcome_override=None,
                is_incomplete=True,
                notes='pending_outcome',
            )
        except Exception as exc:
            self._emit('close_window_error', window_id=market.window_id, error=repr(exc))
            return
        with self.pending_lock:
            self.pending_resolution[market.window_id] = {
                'slug': market.slug,
                'first_attempt_at': time.time(),
                'attempts': 0,
            }
        self._emit('window_closed_continuous', window_id=market.window_id, pending_resolution=True)

    def _resolver_loop(self) -> None:
        while not self.stop_event.is_set():
            with self.pending_lock:
                items = list(self.pending_resolution.items())
            for window_id, meta in items:
                if self.stop_event.is_set():
                    return
                try:
                    outcome, _ = resolve_outcome_with_retries(
                        self.client,
                        meta['slug'],
                        poll_intervals_seconds=(),
                        sleep_fn=lambda s: None,
                    )
                except Exception:
                    outcome = None
                if outcome is not None:
                    try:
                        update_outcome(self.db_path, window_id, outcome, is_incomplete=0, notes='')
                    except Exception as exc:
                        self._emit('update_outcome_error', window_id=window_id, error=repr(exc))
                        continue
                    with self.pending_lock:
                        self.pending_resolution.pop(window_id, None)
                    self._emit('gamma_resolved', window_id=window_id, outcome=outcome, attempts=meta.get('attempts', 0) + 1)
                else:
                    meta['attempts'] += 1
                    age = time.time() - meta['first_attempt_at']
                    if age > self.resolver_giveup_seconds:
                        try:
                            update_outcome(
                                self.db_path, window_id, None,
                                is_incomplete=1, notes='gamma_unresolved_after_30min',
                            )
                        except Exception:
                            pass
                        with self.pending_lock:
                            self.pending_resolution.pop(window_id, None)
                        self._emit('gamma_unresolved', window_id=window_id, attempts=meta['attempts'])
            if self.stop_event.wait(timeout=self.resolver_poll_seconds):
                return
