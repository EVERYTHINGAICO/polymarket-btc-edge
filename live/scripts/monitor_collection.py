"""Monitor read-only del progreso de recoleccion + FLIP counter.

Lee SQLite y log JSON sin modificar nada. Pensado para correr periodicamente
via /loop o cron.

Uso:
    py scripts/monitor_collection.py
    py scripts/monitor_collection.py --json  # output JSON estructurado
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / 'data' / 'observations.db'
LOG_PATH = ROOT / 'reports' / 'live' / 'continuous_logger.log'
STDOUT_PATH = ROOT / 'reports' / 'live' / 'continuous_stdout.log'

TARGET_WINDOWS = 1000
HEALTH_STALE_SECONDS = 5 * 60
HEALTH_DEAD_SECONDS = 15 * 60


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def fetch_db_stats(db_path: Path) -> dict:
    if not db_path.exists():
        return {'error': f'DB no encontrada: {db_path}'}
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        n_complete = con.execute(
            "SELECT COUNT(*) FROM observations WHERE outcome IN ('Up','Down') AND is_incomplete=0 AND window_id != 'demo-window'"
        ).fetchone()[0]
        n_pending = con.execute(
            "SELECT COUNT(*) FROM observations WHERE outcome IS NULL AND ts_close IS NOT NULL AND window_id != 'demo-window'"
        ).fetchone()[0]
        n_open = con.execute(
            "SELECT COUNT(*) FROM observations WHERE ts_close IS NULL AND window_id != 'demo-window'"
        ).fetchone()[0]
        n_incomplete = con.execute(
            "SELECT COUNT(*) FROM observations WHERE is_incomplete=1 AND window_id != 'demo-window'"
        ).fetchone()[0]
        ups = con.execute(
            "SELECT COUNT(*) FROM observations WHERE outcome='Up' AND is_incomplete=0"
        ).fetchone()[0]
        downs = con.execute(
            "SELECT COUNT(*) FROM observations WHERE outcome='Down' AND is_incomplete=0"
        ).fetchone()[0]

        # Throughput last 1h y last 24h
        now_iso = datetime.now(timezone.utc)
        one_h_ago = (now_iso - timedelta(hours=1)).isoformat().replace('+00:00', 'Z')
        one_day_ago = (now_iso - timedelta(hours=24)).isoformat().replace('+00:00', 'Z')
        n_last_1h = con.execute(
            "SELECT COUNT(*) FROM observations WHERE ts_close > ? AND outcome IN ('Up','Down') AND is_incomplete=0",
            (one_h_ago,),
        ).fetchone()[0]
        n_last_24h = con.execute(
            "SELECT COUNT(*) FROM observations WHERE ts_close > ? AND outcome IN ('Up','Down') AND is_incomplete=0",
            (one_day_ago,),
        ).fetchone()[0]

        # Ultima ventana
        last_row = con.execute(
            "SELECT window_id, ts_open, ts_close FROM observations WHERE window_id != 'demo-window' ORDER BY ts_open DESC LIMIT 1"
        ).fetchone()
        last_window = dict(last_row) if last_row else None

        # FLIP analysis (Chainlink dir vs Polymarket outcome)
        flip_rows = con.execute(
            """
            SELECT window_id, outcome, deribit_index_open, deribit_index_close,
                   price_to_beat, chainlink_close
              FROM observations
             WHERE outcome IN ('Up','Down') AND is_incomplete=0
               AND deribit_index_open IS NOT NULL AND deribit_index_close IS NOT NULL
               AND price_to_beat IS NOT NULL AND chainlink_close IS NOT NULL
               AND window_id != 'demo-window'
            """
        ).fetchall()
    finally:
        con.close()

    return {
        'n_complete': n_complete,
        'n_pending': n_pending,
        'n_open': n_open,
        'n_incomplete': n_incomplete,
        'ups': ups,
        'downs': downs,
        'n_last_1h': n_last_1h,
        'n_last_24h': n_last_24h,
        'last_window': last_window,
        '_flip_rows': flip_rows,
    }


def analyze_flips(rows) -> dict:
    """Cuenta FLIPs Chainlink-on-chain vs Polymarket outcome."""
    flips_chainlink_vs_poly = 0
    flips_deribit_vs_poly = 0
    flips_deribit_vs_chainlink = 0
    chainlink_move_magnitudes_stable: list[float] = []
    chainlink_move_magnitudes_flip: list[float] = []
    flippy_windows = []

    for r in rows:
        deribit_dir = 'Up' if r['deribit_index_close'] >= r['deribit_index_open'] else 'Down'
        chainlink_dir = 'Up' if r['chainlink_close'] >= r['price_to_beat'] else 'Down'
        chainlink_move = abs(r['chainlink_close'] - r['price_to_beat'])
        if chainlink_dir != r['outcome']:
            flips_chainlink_vs_poly += 1
            chainlink_move_magnitudes_flip.append(chainlink_move)
            flippy_windows.append({
                'window_id': r['window_id'],
                'outcome': r['outcome'],
                'deribit_change': round(r['deribit_index_close'] - r['deribit_index_open'], 2),
                'chainlink_change': round(r['chainlink_close'] - r['price_to_beat'], 2),
            })
        else:
            chainlink_move_magnitudes_stable.append(chainlink_move)
        if deribit_dir != r['outcome']:
            flips_deribit_vs_poly += 1
        if deribit_dir != chainlink_dir:
            flips_deribit_vs_chainlink += 1

    n = len(rows)

    def _median(xs):
        if not xs:
            return None
        s = sorted(xs)
        m = len(s) // 2
        return round(s[m] if len(s) % 2 else (s[m - 1] + s[m]) / 2, 2)

    return {
        'n_evaluated': n,
        'flips_chainlink_vs_polymarket': flips_chainlink_vs_poly,
        'flips_chainlink_rate': round(flips_chainlink_vs_poly / n * 100, 2) if n else 0,
        'flips_deribit_vs_polymarket': flips_deribit_vs_poly,
        'flips_deribit_rate': round(flips_deribit_vs_poly / n * 100, 2) if n else 0,
        'flips_deribit_vs_chainlink': flips_deribit_vs_chainlink,
        'median_chainlink_move_stable': _median(chainlink_move_magnitudes_stable),
        'median_chainlink_move_flippy': _median(chainlink_move_magnitudes_flip),
        'flippy_windows_recent': flippy_windows[-5:] if flippy_windows else [],
    }


def parse_last_log_event(log_path: Path) -> dict:
    if not log_path.exists():
        return {'error': 'log no encontrado'}
    try:
        with log_path.open('r', encoding='utf-8') as fh:
            lines = fh.readlines()
        if not lines:
            return {'error': 'log vacio'}
        last = json.loads(lines[-1].strip())
        last_ts_utc = last.get('ts_utc')
        if last_ts_utc:
            last_dt = datetime.fromisoformat(last_ts_utc.replace('Z', '+00:00'))
            age_seconds = (datetime.now(timezone.utc) - last_dt).total_seconds()
        else:
            age_seconds = None
        return {
            'last_event': last.get('event'),
            'last_ts_utc': last_ts_utc,
            'age_seconds': age_seconds,
        }
    except Exception as exc:
        return {'error': repr(exc)}


def compute_health(last_event_age: float | None) -> str:
    if last_event_age is None:
        return 'UNKNOWN'
    if last_event_age < HEALTH_STALE_SECONDS:
        return 'HEALTHY'
    if last_event_age < HEALTH_DEAD_SECONDS:
        return 'STALE'
    return 'DEAD'


def compute_eta(n_complete: int, n_last_24h: int) -> dict:
    remaining = TARGET_WINDOWS - n_complete
    if n_last_24h <= 0:
        return {'remaining': remaining, 'eta_unknown': True}
    rate_per_h = n_last_24h / 24
    hours_remaining = remaining / rate_per_h if rate_per_h > 0 else None
    eta_at = (datetime.now(timezone.utc) + timedelta(hours=hours_remaining)).isoformat().replace('+00:00', 'Z') if hours_remaining else None
    return {
        'remaining': remaining,
        'rate_per_h': round(rate_per_h, 2),
        'hours_remaining': round(hours_remaining, 1) if hours_remaining else None,
        'days_remaining': round(hours_remaining / 24, 1) if hours_remaining else None,
        'eta_at_utc': eta_at,
    }


def next_boundary_utc() -> str:
    now = time.time()
    next_b = (int(now) // 900 + 1) * 900
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(next_b))


def render_text_report(stats: dict, flips: dict, log: dict, health: str, eta: dict) -> str:
    lines = []
    lines.append('=' * 60)
    lines.append(f'  COLLECTION MONITOR — {utc_now_iso()}')
    lines.append('=' * 60)
    lines.append('')
    lines.append('  PROGRESO')
    lines.append(f'    Completas:        {stats["n_complete"]} / {TARGET_WINDOWS}  ({stats["n_complete"]/TARGET_WINDOWS*100:.1f}%)')
    lines.append(f'    Pendientes:       {stats["n_pending"]}')
    lines.append(f'    En curso/abiertas: {stats["n_open"]}')
    lines.append(f'    Marcadas incompletas: {stats["n_incomplete"]}')
    lines.append('')
    lines.append('  THROUGHPUT')
    lines.append(f'    Last 1h:          {stats["n_last_1h"]} ventanas')
    lines.append(f'    Last 24h:         {stats["n_last_24h"]} ventanas')
    if not eta.get('eta_unknown'):
        lines.append(f'    Rate:             {eta["rate_per_h"]} ventanas/h')
        lines.append(f'    ETA a {TARGET_WINDOWS}:      ~{eta["hours_remaining"]}h = {eta["days_remaining"]} días ({eta["eta_at_utc"]})')
    lines.append('')
    lines.append('  CALIDAD DATOS')
    total = stats['ups'] + stats['downs']
    lines.append(f'    Up/Down split:    {stats["ups"]} / {stats["downs"]}  ({stats["ups"]/total*100:.1f}% Up)' if total else f'    Up/Down split:    sin datos')
    lines.append('')
    lines.append(f'  FLIPS (Chainlink-on-chain vs Polymarket Data Streams)')
    lines.append(f'    N evaluadas:      {flips["n_evaluated"]}')
    lines.append(f'    FLIPs Chainlink:  {flips["flips_chainlink_vs_polymarket"]}  ({flips["flips_chainlink_rate"]}%)')
    lines.append(f'    FLIPs Deribit:    {flips["flips_deribit_vs_polymarket"]}  ({flips["flips_deribit_rate"]}%)')
    lines.append(f'    Mediana movimiento chainlink:')
    lines.append(f'      Estables: ${flips["median_chainlink_move_stable"]}')
    lines.append(f'      Flippy:   ${flips["median_chainlink_move_flippy"]}')
    if flips['flippy_windows_recent']:
        lines.append(f'    FLIPs recientes (últimos 5):')
        for f in flips['flippy_windows_recent']:
            lines.append(f"      {f['window_id'][-15:]} outcome={f['outcome']} deribit={f['deribit_change']:+.2f} chainlink={f['chainlink_change']:+.2f}")
    lines.append('')
    lines.append('  SALUD DEL PROCESO')
    if 'error' in log:
        lines.append(f'    Estado: ERROR leyendo log ({log["error"]})')
    else:
        age = log.get('age_seconds')
        if age is not None:
            lines.append(f'    Última actividad: hace {int(age)}s  ({log.get("last_event")})')
        lines.append(f'    Próximo boundary: {next_boundary_utc()}')
        status_icon = '[OK]' if health == 'HEALTHY' else ('[STALE]' if health == 'STALE' else '[DEAD]')
        lines.append(f'    Status:           {status_icon} {health}')
    lines.append('')
    if stats.get('last_window'):
        lw = stats['last_window']
        lines.append('  ÚLTIMA VENTANA')
        lines.append(f"    window_id: {lw['window_id']}")
        lines.append(f"    ts_open:   {lw['ts_open']}")
        lines.append(f"    ts_close:  {lw['ts_close']}")
        lines.append('')
    lines.append('=' * 60)
    return '\n'.join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description='Monitor read-only de la recoleccion.')
    parser.add_argument('--json', action='store_true', help='Output JSON estructurado en lugar de texto.')
    parser.add_argument('--db', default=str(DB_PATH))
    parser.add_argument('--log', default=str(LOG_PATH))
    args = parser.parse_args()

    db_path = Path(args.db)
    log_path = Path(args.log)

    stats = fetch_db_stats(db_path)
    if 'error' in stats:
        print(f'ERROR: {stats["error"]}', file=sys.stderr)
        return 2
    flip_rows = stats.pop('_flip_rows')
    flips = analyze_flips(flip_rows)
    log = parse_last_log_event(log_path)
    health = compute_health(log.get('age_seconds'))
    eta = compute_eta(stats['n_complete'], stats['n_last_24h'])

    if args.json:
        payload = {
            'generated_at_utc': utc_now_iso(),
            'progress': stats,
            'flips': flips,
            'log': log,
            'health': health,
            'eta': eta,
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
    else:
        print(render_text_report(stats, flips, log, health, eta))

    return 0 if health == 'HEALTHY' else 1


if __name__ == '__main__':
    raise SystemExit(main())
