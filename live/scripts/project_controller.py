from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.auditor import audit_cycle
from core.executor import Executor
from core.project_planner import create_plan
from core.project_state import load_project_state
from core.task_synthesizer import synthesize_task, write_task

CONFIG_PATH = ROOT / 'config.json'
AUTHORITY_PATH = ROOT / 'PROJECT_DESIGN.md'
VALIDATION_PATH = ROOT / 'reports' / 'phases' / 'fase_5v_validation_status.json'
TASK_PATH = ROOT / 'tasks' / 'current_task.md'
REPORTS_DIR = ROOT / 'reports' / 'cycles'
APPROVALS_DIR = ROOT / 'reports' / 'approvals'


def utc_now_stamp() -> str:
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')


def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding='utf-8')) if CONFIG_PATH.exists() else {}


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def run_cycle() -> tuple[dict, int]:
    config = load_config()
    state = load_project_state(AUTHORITY_PATH, VALIDATION_PATH, APPROVALS_DIR)
    plan = create_plan(state)
    synthesis = synthesize_task(state, plan)
    write_task(TASK_PATH, synthesis)

    result = {
        'phase': state.phase_label,
        'status': state.status,
        'next_goal': state.next_goal,
        'phase_complete': state.phase_complete,
        'current_task_path': _display_path(TASK_PATH),
        'planner': plan.to_dict(),
        'task_synthesis': synthesis.to_dict(),
        'project_state': {
            'approval_active': state.approval_active,
            'readiness_report_exists': state.readiness_report_exists,
            'command_check_exists': state.command_check_exists,
        },
    }

    forbidden_paths = config.get('forbidden_paths', ['.env', 'data', 'PROJECT_DESIGN.md'])
    if plan.requires_human_gate:
        audit = audit_cycle(root=ROOT, forbidden_paths=forbidden_paths)
        result['audit'] = audit.to_dict()
        if state.status == 'PHASE_READY_WITH_ACCEPTED_RISK':
            result['runner_action'] = 'HUMAN_APPROVAL_WITH_ACCEPTED_RISK_STOP'
            result['message'] = 'Fase lista para aprobación humana con riesgo T4 aceptado.'
            return result, 0
        if state.status == 'PHASE_READY_FOR_HUMAN_APPROVAL':
            result['runner_action'] = 'HUMAN_APPROVAL_STOP'
            result['message'] = 'Phase ready for human approval.' if state.phase_label != 'Fase 6' else 'Fase 6 preparada; gate humano requerido antes de recolección prolongada.'
            return result, 0
        if state.status == 'PHASE_UNKNOWN_STATE':
            result['runner_action'] = 'NO_SAFE_ACTION'
            result['message'] = 'Unknown project state; human review required.'
            return result, 0
        result['runner_action'] = 'HUMAN_GATE_STOP'
        result['message'] = plan.gate_reason
        return result, 0

    executor = Executor(ROOT, ExecutorConfigShim.from_config(config), forbidden_paths)
    exec_result = executor.run(synthesis.text)
    result['executor'] = exec_result.to_dict()
    audit = audit_cycle(root=ROOT, forbidden_paths=forbidden_paths, execution=exec_result)
    result['audit'] = audit.to_dict()
    if not audit.ok:
        result['runner_action'] = 'AUDIT_BLOCKED'
        result['message'] = audit.reason
        return result, 1
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
        result['message'] = 'Atomic task synthesized; executor is disabled or not configured.'
        return result, 0
    result['runner_action'] = exec_result.status
    result['message'] = 'Executor failed or is blocked.'
    return result, 1


class ExecutorConfigShim:
    def __init__(self, *, mode: str, command: str, timeout_seconds: int, test_command: str, enabled: bool) -> None:
        self.mode = mode
        self.command = command
        self.timeout_seconds = timeout_seconds
        self.test_command = test_command
        self.enabled = enabled

    @classmethod
    def from_config(cls, data: dict) -> 'ExecutorConfigShim':
        return cls(
            mode=data.get('executor_mode', 'none'),
            command=data.get('executor_command', ''),
            timeout_seconds=int(data.get('executor_timeout_seconds', 60)),
            test_command=data.get('test_command', ''),
            enabled=bool(data.get('executor_enabled', False)),
        )


def write_cycle_report(result: dict) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / f'{utc_now_stamp()}_project_controller_cycle.json'
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--max-cycles', type=int, default=1)
    args = parser.parse_args()

    max_cycles = max(1, args.max_cycles)
    exit_code = 0
    final_result: dict | None = None
    for index in range(max_cycles):
        result, exit_code = run_cycle()
        result['cycle_index'] = index + 1
        report_path = write_cycle_report(result)
        result['cycle_report'] = _display_path(report_path)
        final_result = result
        if result['runner_action'] in {
            'HUMAN_APPROVAL_WITH_ACCEPTED_RISK_STOP',
            'HUMAN_APPROVAL_STOP',
            'HUMAN_GATE_STOP',
            'NO_SAFE_ACTION',
            'AUDIT_BLOCKED',
        }:
            break
        if result['runner_action'] not in {'TASK_READY_NO_EXECUTOR', 'EXECUTOR_PASS'}:
            break
    assert final_result is not None
    print(json.dumps(final_result, indent=2, ensure_ascii=False))
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
