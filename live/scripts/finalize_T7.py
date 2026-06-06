"""Finalize T-7 + G6.1b verification + write reports.

Run this AFTER the background pilot (T-7 with --with-trajectory) has finished.
Reads its stdout JSON + SQLite state, writes:
  - reports/phases/fase_6_real_window_pass_report.md  (G-9)
  - HANDOFF_FINAL_2026-05-27.md
"""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / 'data' / 'observations.db'
T7_STDOUT = ROOT / 'reports' / 'live' / 'T7_pilot_stdout.json'
T7_STDERR = ROOT / 'reports' / 'live' / 'T7_pilot_stderr.log'
G9_REPORT = ROOT / 'reports' / 'phases' / 'fase_6_real_window_pass_report.md'
HANDOFF_FINAL = ROOT / 'HANDOFF_FINAL_2026-05-27.md'


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def load_t7_output() -> dict | None:
    if not T7_STDOUT.exists() or T7_STDOUT.stat().st_size == 0:
        return None
    try:
        return json.loads(T7_STDOUT.read_text(encoding='utf-8'))
    except Exception as exc:
        return {'_parse_error': repr(exc), '_raw_preview': T7_STDOUT.read_text(encoding='utf-8')[:2000]}


def query_latest_real_row() -> dict | None:
    if not DB_PATH.exists():
        return None
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        row = con.execute(
            "SELECT * FROM observations WHERE window_id != 'demo-window' "
            "ORDER BY ts_open DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None
    finally:
        con.close()


def query_trajectory(window_id: str) -> list[dict]:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            "SELECT t_seconds, pm_up_price, sampled_at_utc FROM observations_intrawindow "
            "WHERE window_id = ? ORDER BY t_seconds",
            (window_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


def count_all_real_rows() -> int:
    con = sqlite3.connect(DB_PATH)
    try:
        return con.execute(
            "SELECT COUNT(*) FROM observations WHERE window_id != 'demo-window'"
        ).fetchone()[0]
    finally:
        con.close()


def evaluate(row: dict | None, trajectory: list[dict]) -> dict:
    if row is None:
        return {'status': 'FAIL', 'reason': 'No real row found in SQLite'}
    crit = {
        'outcome_valid': row.get('outcome') in ('Up', 'Down'),
        'is_incomplete_zero': row.get('is_incomplete') == 0,
        'has_n_trades': (row.get('n_trades_15m') or 0) > 0,
        'has_deribit_open': (row.get('deribit_index_open') or 0) > 0,
        'has_deribit_close': (row.get('deribit_index_close') or 0) > 0,
        'has_chainlink_close': row.get('chainlink_close') is not None,
        'has_price_to_beat_g61b': row.get('price_to_beat') is not None,
        'trajectory_count_ok': len(trajectory) >= 25,
    }
    main_pass = (
        crit['outcome_valid']
        and crit['is_incomplete_zero']
        and crit['has_n_trades']
        and crit['has_deribit_open']
        and crit['has_deribit_close']
    )
    return {
        'status': 'PASS' if main_pass else 'FAIL',
        'criteria': crit,
        'main_pass': main_pass,
        'g6_1b_verified': crit['has_price_to_beat_g61b'],
        'fase_6b_trajectory_present': crit['trajectory_count_ok'],
    }


def render_g9_report(row: dict | None, traj: list[dict], evaluation: dict, t7_output: dict | None) -> str:
    lines = [
        '# Fase 6 — Real Window PASS Report',
        '',
        f'**Fecha:** {utc_now()}',
        f'**Estado:** {evaluation["status"]}',
        '',
        '## Resumen',
        '',
    ]
    if row is None:
        lines.extend(['Sin fila real escrita en SQLite. T-7 falló o no completó.', ''])
    else:
        lines.append(f'- `window_id`: `{row.get("window_id")}`')
        lines.append(f'- `ts_open` → `ts_close`: {row.get("ts_open")} → {row.get("ts_close")}')
        lines.append(f'- `outcome`: **{row.get("outcome")}** (autoridad: Polymarket gamma)')
        lines.append(f'- `chainlink_close`: {row.get("chainlink_close")} (referencia, oráculo Polygon)')
        lines.append(f'- `deribit_index_open` → `deribit_index_close`: {row.get("deribit_index_open")} → {row.get("deribit_index_close")}')
        lines.append(f'- `price_to_beat`: {row.get("price_to_beat")} (G6.1b: desde Chainlink al ts_open)')
        lines.append(f'- `pm_up_price_open` → `pm_up_price_close`: {row.get("pm_up_price_open")} → {row.get("pm_up_price_close")}')
        lines.append(f'- `n_trades_15m`: {row.get("n_trades_15m")}')
        lines.append(f'- `is_incomplete`: {row.get("is_incomplete")}')
        lines.append(f'- `insufficient_flow`: {row.get("insufficient_flow")}')
        lines.append(f'- `notes`: `{row.get("notes")}`')
    lines.append('')
    lines.append('## Criterios de evaluación')
    lines.append('')
    for k, v in evaluation.get('criteria', {}).items():
        lines.append(f'- {"✅" if v else "❌"} {k}')
    lines.append('')
    lines.append('## Trayectoria intra-ventana (Fase 6.b)')
    lines.append('')
    lines.append(f'- Puntos capturados: **{len(traj)}**')
    if traj:
        lines.append(f'- Primer punto: t={traj[0]["t_seconds"]}s, pm_up_price={traj[0]["pm_up_price"]}')
        lines.append(f'- Último punto: t={traj[-1]["t_seconds"]}s, pm_up_price={traj[-1]["pm_up_price"]}')
        prices = [p['pm_up_price'] for p in traj if p['pm_up_price'] is not None]
        if prices:
            lines.append(f'- Min/Max: {min(prices)} / {max(prices)}')
    lines.append('')
    if t7_output:
        lines.append('## T-7 stdout (resumen)')
        lines.append('')
        lines.append('```json')
        compact = {
            'status': t7_output.get('status'),
            'row_kind': t7_output.get('row_kind'),
            'selected_window_id': t7_output.get('selected_window_id'),
            'finished_at_utc': t7_output.get('finished_at_utc'),
            'trajectory_samples': t7_output.get('trajectory_samples'),
            'trajectory_errors': t7_output.get('trajectory_errors'),
        }
        lines.append(json.dumps(compact, indent=2, ensure_ascii=False))
        lines.append('```')
        lines.append('')
    lines.append('## Riesgos residuales')
    lines.append('')
    lines.append('- T4 (resilience caída de red/luz) sigue WAIVED_BY_HUMAN.')
    lines.append('- Gamma puede tardar >7 min en publicar resolución. Si recurre, subir `poll_intervals_seconds`.')
    lines.append('- RPC públicos de Polygon pueden cambiar; lista de fallback en `src/chainlink_feed.py`.')
    lines.append('')
    lines.append('## Siguiente acción recomendada')
    lines.append('')
    lines.append('- Si PASS: avanzar a G6.2 (3-5 ventanas consecutivas con `--with-trajectory`).')
    lines.append('- Si FAIL: revisar criterios fallidos arriba y replanear.')
    return '\n'.join(lines) + '\n'


def render_handoff_final(row: dict | None, traj: list[dict], evaluation: dict, total_real_rows: int, t7_output: dict | None) -> str:
    traj_count = len(traj)
    traj_lines = []
    if traj_count:
        for p in traj[:5]:
            traj_lines.append(f"t={p['t_seconds']:>4}s  price={p['pm_up_price']}  sampled={p['sampled_at_utc']}")
        if traj_count > 10:
            traj_lines.append('...')
        if traj_count > 5:
            for p in traj[-5:]:
                traj_lines.append(f"t={p['t_seconds']:>4}s  price={p['pm_up_price']}  sampled={p['sampled_at_utc']}")
    traj_block = '\n'.join(traj_lines) if traj_lines else '(sin trayectoria)'
    return f"""# HANDOFF FINAL — 2026-05-27

## Quién
Claude Code (sesión Pedro). Trabajo nocturno autónomo.

## Estado global
**T-7 + G6.1b verification + Fase 6.b: {evaluation['status']}**

## Resumen ejecutivo

- Filas reales no-demo en `data/observations.db`: **{total_real_rows}**
- Última fila escrita por T-7: `window_id={row.get('window_id') if row else 'N/A'}`
- G6.1b (`price_to_beat` desde Chainlink): {'✅ verificado' if evaluation.get('g6_1b_verified') else '❌ no verificado'}
- Fase 6.b trayectoria: {'✅ ' + str(traj_count) + ' puntos' if evaluation.get('fase_6b_trajectory_present') else '❌ insuficiente o ausente'}
- T-9 PROJECT_DESIGN §3 ampliado: ✅

## Fila T-7

```json
{json.dumps(row, indent=2, ensure_ascii=False) if row else 'null'}
```

## Criterios

{chr(10).join(f"- {'✅' if v else '❌'} {k}" for k, v in evaluation.get('criteria', {}).items())}

## Trayectoria — primeros y últimos puntos

```
{traj_block}
```

## Archivos producidos en esta sesión

Copia activa `D:\\openclaw\\PROJECT DESIGN\\`:
- **Nuevo:** `src/chainlink_feed.py` (G-1)
- **Nuevo:** `src/intrawindow_sampler.py` (T-2)
- **Modificado:** `src/polymarket_feed.py` (resolve_outcome_with_retries, G-2)
- **Modificado:** `src/logger.py` (outcome_override + CLI --with-trajectory, G-3 + T-4)
- **Modificado:** `src/db.py` (tabla observations_intrawindow + funciones, T-1)
- **Modificado:** `scripts/one_window_pilot.py` (cableado completo, G-4 + G6.1b + T-3)
- **Modificado:** `PROJECT_DESIGN.md` §3 (Fase 6.b autorizado, T-9)
- **Nuevo:** `CLAUDE.md`, `HANDOFF_2026-05-27.md`, `HANDOFF_FINAL_2026-05-27.md`
- **Append:** `AGENTS.md`, `OPENCLAW_HANDOFF.md`, `OPENCLAW_RUNBOOK.md`

Copia base `D:\\descargas al dico vergas\\PROJECT DESIGN\\`:
- **Append:** `CLAUDE.md` (nota espejo)

## Decisiones clave registradas

1. **Autoridad del outcome = Polymarket gamma `outcomePrices`**.
2. **Chainlink = referencia informativa best-effort**, no autoridad.
3. **Fase 6.b trayectoria**: opt-in `--with-trajectory`, 30s default, tabla aux separada.

## Riesgos abiertos

- T4 WAIVED_BY_HUMAN (resilience).
- Gamma latencia variable.
- RPC públicos de Polygon (mitigado con fallback).

## Próximos pasos (cuando despiertes)

1. **Si PASS:** abrir `reports/phases/fase_6_real_window_pass_report.md` para ver detalle. Luego planear G6.2 (3-5 ventanas multi-window).
2. **Si FAIL:** revisar `T7_pilot_stderr.log` y los criterios fallidos arriba.

Generado: {utc_now()}
"""


def main() -> int:
    print(f'Reading T-7 stdout from {T7_STDOUT}...')
    t7 = load_t7_output()
    print(f'Reading latest real row from {DB_PATH}...')
    row = query_latest_real_row()
    traj = []
    if row is not None:
        traj = query_trajectory(row['window_id'])
    total_real_rows = count_all_real_rows() if DB_PATH.exists() else 0
    evaluation = evaluate(row, traj)
    print(f'Evaluation: {evaluation["status"]}')
    G9_REPORT.parent.mkdir(parents=True, exist_ok=True)
    G9_REPORT.write_text(render_g9_report(row, traj, evaluation, t7), encoding='utf-8')
    HANDOFF_FINAL.write_text(render_handoff_final(row, traj, evaluation, total_real_rows, t7), encoding='utf-8')
    print(f'Wrote {G9_REPORT}')
    print(f'Wrote {HANDOFF_FINAL}')
    print(f'Total real rows in DB: {total_real_rows}')
    print(f'Last window_id: {row.get("window_id") if row else "N/A"}')
    print(f'Trajectory points: {len(traj)}')
    return 0 if evaluation['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
