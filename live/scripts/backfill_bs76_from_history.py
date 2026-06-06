"""Backfill retroactivo de columnas *_bs76 sobre las ventanas ya capturadas.

Para cada ventana en observations.db que NO tenga bs76 calculado:
1. Lee ts_open de la fila.
2. Baja trades de history.deribit.com para [ts_open-15min, ts_open).
3. Computa D/V/n_trades_bs76 con src/signal_bs76 (Black-76).
4. UPDATE de la fila con las columnas _bs76 + bs76_source='backfill_history'.

Importante:
- READ-ONLY sobre history.deribit.com (endpoint publico).
- NO modifica columnas existentes (D_*, V_*, n_trades_*, outcome, etc.).
- Resumable: si se interrumpe, las filas ya procesadas (bs76_computed_at_utc not null) se saltan.
- Persiste cada trade crudo en deribit_trades_raw para reutilizar si re-procesamos.

Reglas duras (PROJECT_DESIGN seccion 0):
- READ-ONLY sobre Deribit (API publica /public/get_last_trades_by_currency_and_time).
- No trading, no signing, no wallets.

Uso:
    py scripts/backfill_bs76_from_history.py --db data/observations.db
    py scripts/backfill_bs76_from_history.py --db data/observations.db --limit 10  # test corto
    py scripts/backfill_bs76_from_history.py --db data/observations.db --window-id btc-updown-15m-1779860700
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.signal_bs76 import RawTrade, compute_all_windows_bs76  # noqa: E402

HISTORY_API_URL = (
    'https://history.deribit.com/api/v2/public/get_last_trades_by_currency_and_time'
)
USER_AGENT = 'Mozilla/5.0 (PROJECT_DESIGN backfill)'
REQUEST_TIMEOUT = 30.0
PAGE_SIZE = 1000  # maximo por request en Deribit
POLITE_SLEEP_SECONDS = 0.05  # ~20 req/s, muy debajo del limit publico

INSERT_TRADE_SQL = """
INSERT OR IGNORE INTO deribit_trades_raw
    (trade_id, timestamp_ms, instrument_name, direction, iv, index_price, amount, price, captured_at_ms)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

UPDATE_BS76_SQL_TEMPLATE = """
UPDATE observations SET
    D_5m_otm_dotm_bs76 = :D_5m_otm_dotm_bs76,
    D_10m_otm_dotm_bs76 = :D_10m_otm_dotm_bs76,
    D_15m_otm_dotm_bs76 = :D_15m_otm_dotm_bs76,
    D_5m_atm_bs76 = :D_5m_atm_bs76,
    D_10m_atm_bs76 = :D_10m_atm_bs76,
    D_15m_atm_bs76 = :D_15m_atm_bs76,
    V_5m_otm_dotm_bs76 = :V_5m_otm_dotm_bs76,
    V_10m_otm_dotm_bs76 = :V_10m_otm_dotm_bs76,
    V_15m_otm_dotm_bs76 = :V_15m_otm_dotm_bs76,
    n_trades_5m_bs76 = :n_trades_5m_bs76,
    n_trades_10m_bs76 = :n_trades_10m_bs76,
    n_trades_15m_bs76 = :n_trades_15m_bs76,
    bs76_computed_at_utc = :bs76_computed_at_utc,
    bs76_source = :bs76_source
WHERE window_id = :window_id
"""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def parse_ts_open_to_ms(ts_open_str: str) -> int:
    """ '2026-05-27T05:45:00Z' -> ms epoch."""
    dt = datetime.fromisoformat(ts_open_str.replace('Z', '+00:00'))
    return int(dt.timestamp() * 1000)


def fetch_trades_history(start_ms: int, end_ms: int) -> list[dict]:
    """Pagina trades BTC options de history.deribit.com en [start_ms, end_ms).

    Devuelve lista de payloads raw (filtrados a BTC options) con: timestamp, iv,
    index_price, direction, amount, instrument_name, trade_id.
    """
    all_trades: list[dict] = []
    cursor_ms = start_ms
    safety_iter = 0
    while cursor_ms < end_ms and safety_iter < 50:  # safety: ~50k trades max por ventana
        safety_iter += 1
        params = {
            'currency': 'BTC',
            'kind': 'option',
            'start_timestamp': cursor_ms,
            'end_timestamp': end_ms,
            'count': PAGE_SIZE,
            'include_old': 'true',
            'sorting': 'asc',
        }
        url = f'{HISTORY_API_URL}?{urlencode(params)}'
        req = Request(url, headers={'User-Agent': USER_AGENT, 'Accept': 'application/json'})
        try:
            with urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                payload = json.loads(resp.read().decode('utf-8'))
        except Exception as exc:
            raise RuntimeError(f'history.deribit.com fetch failed: {exc}') from exc
        result = payload.get('result', {})
        trades = result.get('trades', []) or []
        if not trades:
            break
        # Filtrar BTC options solo y ya tener todos los campos
        kept = [t for t in trades if str(t.get('instrument_name', '')).startswith('BTC-')
                and str(t.get('instrument_name', '')).endswith(('-C', '-P'))]
        all_trades.extend(kept)
        # avanzar cursor al ultimo timestamp + 1ms
        last_ts = trades[-1].get('timestamp')
        if last_ts is None or len(trades) < PAGE_SIZE:
            break
        new_cursor = int(last_ts) + 1
        if new_cursor <= cursor_ms:  # no avanzo => safeguard
            break
        cursor_ms = new_cursor
        time.sleep(POLITE_SLEEP_SECONDS)
    return all_trades


def to_raw_trades(payloads: list[dict]) -> list[RawTrade]:
    out: list[RawTrade] = []
    for p in payloads:
        try:
            trade_id = str(p['trade_id'])
            ts_ms = int(p['timestamp'])
            instr = str(p['instrument_name'])
            direction = str(p['direction']).strip().lower()
            iv = p.get('iv')
            ip = p.get('index_price')
            if iv is None or ip is None:
                continue
            out.append(RawTrade(
                trade_id=trade_id,
                timestamp_ms=ts_ms,
                instrument_name=instr,
                direction=direction,
                iv=float(iv),
                index_price=float(ip),
                amount=float(p.get('amount', p.get('contracts', 0.0))),
            ))
        except (KeyError, ValueError, TypeError):
            continue
    return out


def persist_raw_trades(conn: sqlite3.Connection, payloads: list[dict]) -> int:
    """Persiste payloads a deribit_trades_raw. Devuelve filas insertadas (no duplicadas)."""
    rows = []
    captured_at_ms = int(time.time() * 1000)
    for p in payloads:
        try:
            rows.append((
                str(p['trade_id']),
                int(p['timestamp']),
                str(p['instrument_name']),
                str(p['direction']).strip().lower(),
                float(p['iv']) if p.get('iv') is not None else None,
                float(p['index_price']) if p.get('index_price') is not None else None,
                float(p.get('amount', p.get('contracts', 0.0))),
                float(p.get('price', 0.0)),
                captured_at_ms,
            ))
        except (KeyError, ValueError, TypeError):
            continue
    if not rows:
        return 0
    cur = conn.executemany(INSERT_TRADE_SQL, rows)
    inserted = cur.rowcount if cur.rowcount is not None else 0
    return max(0, inserted)


def pending_windows(conn: sqlite3.Connection, limit: int | None, window_id: str | None) -> list[tuple[str, str]]:
    """Devuelve [(window_id, ts_open)] de filas sin bs76_computed_at_utc."""
    if window_id is not None:
        rows = conn.execute(
            "SELECT window_id, ts_open FROM observations WHERE window_id = ?",
            (window_id,)
        ).fetchall()
        return [(r[0], r[1]) for r in rows]
    q = ("SELECT window_id, ts_open FROM observations "
         "WHERE bs76_computed_at_utc IS NULL "
         "AND ts_open IS NOT NULL "
         "AND window_id != 'demo-window' "
         "ORDER BY ts_open ASC")
    if limit is not None and limit > 0:
        q += f' LIMIT {int(limit)}'
    rows = conn.execute(q).fetchall()
    return [(r[0], r[1]) for r in rows]


def process_window(conn: sqlite3.Connection, window_id: str, ts_open_str: str, verbose: bool) -> dict:
    """Procesa una ventana: fetch trades, compute bs76, UPDATE row."""
    ts_open_ms = parse_ts_open_to_ms(ts_open_str)
    start_ms = ts_open_ms - 15 * 60 * 1000  # 15 min antes
    end_ms = ts_open_ms
    payloads = fetch_trades_history(start_ms, end_ms)
    n_inserted = persist_raw_trades(conn, payloads)
    trades = to_raw_trades(payloads)
    metrics = compute_all_windows_bs76(trades, window_end_ms=end_ms)
    metrics['window_id'] = window_id
    metrics['bs76_computed_at_utc'] = utc_now_iso()
    metrics['bs76_source'] = 'backfill_history'
    conn.execute(UPDATE_BS76_SQL_TEMPLATE, metrics)
    conn.commit()
    summary = {
        'window_id': window_id,
        'n_payloads': len(payloads),
        'n_valid_raw_trades': len(trades),
        'n_trades_raw_inserted': n_inserted,
        'n_trades_15m_bs76': metrics['n_trades_15m_bs76'],
        'D_15m_otm_dotm_bs76': metrics['D_15m_otm_dotm_bs76'],
    }
    if verbose:
        print(json.dumps(summary), flush=True)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description='Backfill columnas *_bs76 desde history.deribit.com.')
    parser.add_argument('--db', required=True)
    parser.add_argument('--limit', type=int, default=None, help='Procesar solo N ventanas (test).')
    parser.add_argument('--window-id', default=None, help='Procesar SOLO esta ventana (override).')
    parser.add_argument('--quiet', action='store_true', help='Solo imprime totales.')
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f'ERROR: DB no existe: {db_path}', file=sys.stderr)
        return 1

    conn = sqlite3.connect(db_path, timeout=30.0)
    try:
        conn.execute('PRAGMA journal_mode=WAL')
        # verificar columnas bs76 existen
        cols = {r[1] for r in conn.execute("PRAGMA table_info(observations)").fetchall()}
        if 'bs76_computed_at_utc' not in cols:
            print('ERROR: columnas _bs76 no existen. Correr scripts/migrate_add_bs76_columns.py primero.', file=sys.stderr)
            return 2
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        if 'deribit_trades_raw' not in tables:
            print('ERROR: tabla deribit_trades_raw no existe. Correr migrate primero.', file=sys.stderr)
            return 2

        pending = pending_windows(conn, args.limit, args.window_id)
        print(f'[backfill] {len(pending)} ventanas pendientes')
        if not pending:
            return 0

        processed = 0
        errors = 0
        started_at = time.time()
        for wid, tso in pending:
            try:
                process_window(conn, wid, tso, verbose=not args.quiet)
                processed += 1
            except Exception as exc:
                errors += 1
                print(f'ERROR on {wid}: {exc}', file=sys.stderr)
                # no abortamos; el script es resumable
            if processed % 10 == 0:
                elapsed = time.time() - started_at
                rate = processed / elapsed if elapsed > 0 else 0
                eta = (len(pending) - processed) / rate if rate > 0 else float('inf')
                print(f'[progress] {processed}/{len(pending)} '
                      f'rate={rate:.2f}/s eta={eta:.0f}s errors={errors}', flush=True)
        elapsed = time.time() - started_at
        print(f'[done] processed={processed} errors={errors} elapsed={elapsed:.1f}s')
    finally:
        conn.close()

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
