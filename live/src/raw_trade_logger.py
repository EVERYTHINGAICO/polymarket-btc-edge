"""Logger PARALELO de trades crudos de Deribit (con iv + index_price).

Proceso independiente del continuous_logger principal. Abre su propia
conexion WS a Deribit, captura cada trade clasificado de opciones BTC con
TODOS los campos necesarios para recomputar delta Black-76 a posteriori.

Persiste a tabla deribit_trades_raw (creada por scripts/migrate_add_bs76_columns.py).

Por que un proceso aparte:
- El continuous_logger ya esta corriendo y no queremos modificarlo (riesgo de romper
  la captura de las 506 ventanas en curso).
- Tener dos WS al mismo endpoint publico es permitido por Deribit (sin auth).
- Aislamiento de fallos: si este logger crashea, el principal sigue.

Reglas duras (PROJECT_DESIGN seccion 0):
- READ-ONLY sobre Deribit. Solo subscribe a trades.option.BTC.100ms.
- No firma, no opera, no usa wallets ni keys.

Uso:
    py -m src.raw_trade_logger --db data/observations.db
    py -m src.raw_trade_logger --db data/observations.db --log-path reports/live/raw_trades.log

Para detener: Ctrl+C (shutdown limpio).
"""

from __future__ import annotations

import argparse
import json
import socket
import sqlite3
import sys
import threading
import time
from pathlib import Path

from src.deribit_feed import (
    BTC_OPTIONS_TRADES_CHANNEL,
    DERIBIT_PUBLIC_WS_URL,
    MinimalWebSocketClient,
    build_heartbeat_request,
    build_subscribe_request,
    extract_trades_from_message,
    handle_non_trade_message,
    is_btc_option_trade,
)

INSERT_TRADE_SQL = """
INSERT OR IGNORE INTO deribit_trades_raw
    (trade_id, timestamp_ms, instrument_name, direction, iv, index_price, amount, price, captured_at_ms)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


class RawTradeLogger:
    def __init__(self, db_path: str | Path, log_path: str | Path | None = None,
                 url: str = DERIBIT_PUBLIC_WS_URL,
                 reconnect_backoff_seconds: float = 5.0,
                 per_read_timeout_seconds: float = 10.0,
                 flush_every_n: int = 50,
                 flush_every_seconds: float = 5.0,
                 run_seconds: float | None = None) -> None:
        self.db_path = Path(db_path)
        self.log_path = Path(log_path) if log_path else None
        self.url = url
        self.reconnect_backoff_seconds = reconnect_backoff_seconds
        self.per_read_timeout_seconds = per_read_timeout_seconds
        self.flush_every_n = flush_every_n
        self.flush_every_seconds = flush_every_seconds
        self.run_seconds = run_seconds
        self.started_at = time.time()
        self.stop_event = threading.Event()
        self.counts = {
            'raw_trades': 0,
            'persisted': 0,
            'skipped_non_btc_option': 0,
            'skipped_missing_fields': 0,
            'reconnects': 0,
            'errors': 0,
            'timeouts': 0,
        }
        self._pending: list[tuple] = []
        self._last_flush = time.time()

    def _emit(self, event: str, **payload) -> None:
        ts = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        extras = ' '.join(f'{k}={v}' for k, v in payload.items())
        line = f'[{ts}] {event} {extras}'
        try:
            print(line, flush=True)
        except Exception:
            pass
        if self.log_path is not None:
            try:
                self.log_path.parent.mkdir(parents=True, exist_ok=True)
                with self.log_path.open('a', encoding='utf-8') as f:
                    f.write(json.dumps({'ts': ts, 'event': event, **payload}) + '\n')
            except Exception:
                pass

    def _extract_raw(self, trade_payload: dict) -> tuple | None:
        """Devuelve tupla lista para INSERT o None si invalido."""
        if not is_btc_option_trade(trade_payload):
            self.counts['skipped_non_btc_option'] += 1
            return None
        try:
            trade_id = str(trade_payload['trade_id'])
            timestamp_ms = int(trade_payload['timestamp'])
            instrument_name = str(trade_payload['instrument_name'])
            direction = str(trade_payload['direction']).strip().lower()
            iv = trade_payload.get('iv')
            index_price = trade_payload.get('index_price')
            amount = float(trade_payload.get('amount', trade_payload.get('contracts', 0.0)))
            price = float(trade_payload.get('price', 0.0))
        except (KeyError, ValueError, TypeError):
            self.counts['skipped_missing_fields'] += 1
            return None
        if iv is None or index_price is None:
            self.counts['skipped_missing_fields'] += 1
            return None
        try:
            iv_f = float(iv)
            index_price_f = float(index_price)
        except (TypeError, ValueError):
            self.counts['skipped_missing_fields'] += 1
            return None
        captured_at_ms = int(time.time() * 1000)
        return (trade_id, timestamp_ms, instrument_name, direction,
                iv_f, index_price_f, amount, price, captured_at_ms)

    def _flush_pending(self, force: bool = False) -> None:
        if not self._pending:
            self._last_flush = time.time()
            return
        if not force and len(self._pending) < self.flush_every_n and (time.time() - self._last_flush) < self.flush_every_seconds:
            return
        rows = self._pending
        self._pending = []
        self._last_flush = time.time()
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        try:
            conn.execute('PRAGMA journal_mode=WAL')
            cur = conn.executemany(INSERT_TRADE_SQL, rows)
            conn.commit()
            inserted = cur.rowcount if cur.rowcount is not None else 0
            self.counts['persisted'] += max(0, inserted)
        finally:
            conn.close()

    def start(self) -> None:
        self._emit('raw_trade_logger_started',
                   db=str(self.db_path),
                   url=self.url)
        try:
            self._stream_loop()
        finally:
            try:
                self._flush_pending(force=True)
            except Exception:
                pass
            self._emit('raw_trade_logger_stopped', counts=json.dumps(self.counts))

    def stop(self) -> None:
        self.stop_event.set()

    def _stream_loop(self) -> None:
        while not self.stop_event.is_set() and not self._deadline_reached():
            try:
                client = MinimalWebSocketClient(self.url, timeout=self.per_read_timeout_seconds)
                client.connect()
                client.send_text(json.dumps(build_heartbeat_request()))
                client.send_text(json.dumps(build_subscribe_request([BTC_OPTIONS_TRADES_CHANNEL])))
                self._emit('raw_trade_logger_connected')
                self._stream_messages(client)
                try:
                    client.close()
                except Exception:
                    pass
            except Exception as exc:
                self.counts['errors'] += 1
                self._emit('raw_trade_logger_error', error=repr(exc))
                if self.stop_event.is_set():
                    break
                self.counts['reconnects'] += 1
                self.stop_event.wait(timeout=self.reconnect_backoff_seconds)

    def _stream_messages(self, client: MinimalWebSocketClient) -> None:
        from collections import Counter
        non_trade_counts: Counter = Counter()
        while not self.stop_event.is_set() and not self._deadline_reached():
            try:
                raw_message = client.recv_text()
            except socket.timeout:
                self.counts['timeouts'] += 1
                self._flush_pending()
                continue
            try:
                message = json.loads(raw_message)
            except Exception:
                continue
            if handle_non_trade_message(message, non_trade_counts, client.send_text):
                continue
            trade_payloads = extract_trades_from_message(message)
            if not trade_payloads:
                continue
            for tp in trade_payloads:
                self.counts['raw_trades'] += 1
                row = self._extract_raw(tp)
                if row is not None:
                    self._pending.append(row)
            self._flush_pending()

    def _deadline_reached(self) -> bool:
        return self.run_seconds is not None and (time.time() - self.started_at) >= self.run_seconds


def main() -> int:
    parser = argparse.ArgumentParser(description='Logger PARALELO de trades crudos Deribit (no toca el continuous_logger).')
    parser.add_argument('--db', required=True, help='Path a observations.db (tabla deribit_trades_raw debe existir).')
    parser.add_argument('--log-path', default=None, help='Path opcional a archivo de log JSONL.')
    parser.add_argument('--url', default=DERIBIT_PUBLIC_WS_URL)
    parser.add_argument('--run-seconds', type=float, default=None, help='Optional bounded run for smoke/testing.')
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f'ERROR: DB no existe: {db_path}', file=sys.stderr)
        return 1
    # Verificar que la tabla deribit_trades_raw exista
    conn = sqlite3.connect(db_path)
    try:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    finally:
        conn.close()
    if 'deribit_trades_raw' not in tables:
        print('ERROR: tabla deribit_trades_raw no existe. Correr scripts/migrate_add_bs76_columns.py primero.', file=sys.stderr)
        return 2

    logger = RawTradeLogger(db_path=db_path, log_path=args.log_path, url=args.url, run_seconds=args.run_seconds)
    try:
        logger.start()
    except KeyboardInterrupt:
        print('Ctrl+C recibido. Cerrando...', flush=True)
        logger.stop()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
