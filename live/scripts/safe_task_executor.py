from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PHASES_DIR = ROOT / 'reports' / 'phases'
CYCLES_DIR = ROOT / 'reports' / 'cycles'


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def readiness_report() -> dict:
    report_path = PHASES_DIR / 'fase_6_readiness_report.md'
    content = """# Fase 6 Readiness Report\n\nPASS_WITH_HUMAN_START_GATE\n\n## objetivo\nPreparar la recolección oficial read-only sin lanzar aún una corrida prolongada.\n\n## comando reproducible propuesto\n```bash\npython3 -m src.logger --db data/observations.db --log-path reports/live/logger_runtime.log\n```\n\n## observabilidad mínima\n- logs UTC en `reports/live/logger_runtime.log`\n- base SQLite en `data/observations.db`\n- reportes de ciclo en `reports/cycles/`\n\n## criterios de ventana confiable\n- apertura/cierre UTC alineados\n- sin inventar completitud\n- `is_incomplete=0` y `insufficient_flow=0` para ventanas confiables\n- sin duplicados ni corrupción tras stop/resume\n\n## stop/resume\n- detener proceso manualmente con supervisión humana\n- reiniciar sobre la misma DB\n- validar que no aparezcan duplicados\n\n## límites\n- no iniciar aún recolección prolongada desde este paso\n- requiere gate humano antes del arranque supervisado\n"""
    write_text(report_path, content)
    return {'task': 'F6_READINESS_REPORT', 'report_path': str(report_path.relative_to(ROOT))}


def collection_command_check() -> dict:
    phase_path = PHASES_DIR / 'fase_6_collection_command_check.md'
    proc = subprocess.run(
        'python3 scripts/run_collection_once.py',
        shell=True,
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=30,
    )
    content = (
        '# Fase 6 Collection Command Check\n\n'
        f'Exit code: {proc.returncode}\n\n'
        '## stdout\n```\n' + proc.stdout + '\n```\n\n'
        '## stderr\n```\n' + proc.stderr + '\n```\n'
    )
    write_text(phase_path, content)
    return {
        'task': 'F6_COLLECTION_COMMAND_CHECK',
        'report_path': str(phase_path.relative_to(ROOT)),
        'exit_code': proc.returncode,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--task-file', default='tasks/current_task.md')
    args = parser.parse_args()

    task_text = (ROOT / args.task_file).read_text(encoding='utf-8')
    if 'F6_READINESS_REPORT' in task_text:
        result = readiness_report()
    elif 'F6_COLLECTION_COMMAND_CHECK' in task_text:
        result = collection_command_check()
    else:
        result = {'task': 'NOOP', 'reason': 'No supported safe task found in current task file.'}
    CYCLES_DIR.mkdir(parents=True, exist_ok=True)
    artifact = CYCLES_DIR / f'{utc_now()}_safe_task_executor.json'
    artifact.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get('task') != 'NOOP' else 2


if __name__ == '__main__':
    raise SystemExit(main())
