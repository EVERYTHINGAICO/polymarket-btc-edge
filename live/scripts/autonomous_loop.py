from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.executor import Executor, ExecutorConfig
from core.loop_policy import decide_from_phase_status, write_current_task

STATUS_PATH = ROOT / 'reports' / 'phases' / 'fase_5v_validation_status.json'
CURRENT_TASK_PATH = ROOT / 'tasks' / 'current_task.md'
REPORTS_DIR = ROOT / 'reports' / 'cycles'
CONFIG_PATH = ROOT / 'config.json'


def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding='utf-8')) if CONFIG_PATH.exists() else {}


def utc_now_stamp() -> str:
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')


def _display_task_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def load_executor_config(data: dict | None = None) -> ExecutorConfig:
    data = data or load_config()
    return ExecutorConfig(
        mode=data.get('executor_mode', 'none'),
        command=data.get('executor_command', ''),
        timeout_seconds=int(data.get('executor_timeout_seconds', 60)),
        test_command=data.get('test_command', ''),
        enabled=bool(data.get('executor_enabled', False)),
    )


def run_once() -> tuple[dict, int]:
    decision = decide_from_phase_status(STATUS_PATH)
    write_current_task(CURRENT_TASK_PATH, decision)
    result = {
        'status': decision.status,
        'next_goal': decision.next_goal,
        'phase_complete': decision.phase_complete,
        'current_task_path': _display_task_path(CURRENT_TASK_PATH),
    }
    if decision.status == 'PHASE_IN_PROGRESS':
        task_text = CURRENT_TASK_PATH.read_text(encoding='utf-8') if CURRENT_TASK_PATH.exists() else ''
        config_data = load_config()
        executor = Executor(ROOT, load_executor_config(config_data), config_data.get('forbidden_paths'))
        exec_result = executor.run(task_text)
        result['executor'] = exec_result.to_dict()
        if exec_result.status == 'PASS':
            test_result = executor.run_tests()
            result['test_result'] = test_result.to_dict() if test_result else None
            if test_result and test_result.status != 'PASS':
                result['runner_action'] = 'EXECUTOR_TESTS_FAILED'
                result['message'] = 'Executor succeeded but configured tests failed.'
                return result, 1
            result['runner_action'] = 'EXECUTOR_PASS'
            result['message'] = 'Executor and configured tests completed successfully.'
            return result, 0
        if exec_result.status == 'TASK_READY_NO_EXECUTOR':
            result['runner_action'] = 'TASK_READY_NO_EXECUTOR'
            result['message'] = 'Next goal prepared in tasks/current_task.md; no task executor configured in this runner.'
            return result, 0
        result['runner_action'] = exec_result.status
        result['message'] = 'Executor failed or is blocked.'
        return result, 1
    elif decision.status == 'PHASE_BLOCKED_DEFERRED_T4':
        result['runner_action'] = 'HUMAN_GATE_STOP'
        result['message'] = 'Loop stopped cleanly at deferred human gate.'
        return result, 0
    elif decision.status == 'PHASE_READY_FOR_HUMAN_APPROVAL':
        result['runner_action'] = 'HUMAN_APPROVAL_STOP'
        result['message'] = 'Phase ready for human approval.'
        return result, 0
    elif decision.status == 'PHASE_READY_WITH_ACCEPTED_RISK':
        result['runner_action'] = 'HUMAN_APPROVAL_WITH_ACCEPTED_RISK_STOP'
        result['message'] = 'Fase lista para aprobación humana con riesgo T4 aceptado.'
        return result, 0
    else:
        result['runner_action'] = 'NO_SAFE_ACTION'
        result['message'] = 'No safe automated action available.'
        return result, 0


def write_cycle_report(result: dict) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / f'{utc_now_stamp()}_autonomous_loop_once.json'
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--max-cycles', type=int, default=1)
    args = parser.parse_args()

    cycles = 1 if args.once else max(1, args.max_cycles)
    final_result: dict | None = None
    exit_code = 0
    for index in range(cycles):
        result, exit_code = run_once()
        result['cycle_index'] = index + 1
        report_path = write_cycle_report(result)
        result['cycle_report'] = str(report_path.relative_to(ROOT))
        final_result = result
        if result['status'] in {'PHASE_BLOCKED_DEFERRED_T4', 'PHASE_READY_FOR_HUMAN_APPROVAL', 'PHASE_READY_WITH_ACCEPTED_RISK'}:
            break
        if result['runner_action'] not in {'TASK_READY_NO_EXECUTOR', 'EXECUTOR_PASS'}:
            break
        break

    assert final_result is not None
    print(json.dumps(final_result, indent=2, ensure_ascii=False))
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
