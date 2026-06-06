from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scripts.project_controller as project_controller


class ProjectControllerTests(unittest.TestCase):
    def write_status(self, root: Path, payload: dict) -> Path:
        path = root / 'reports' / 'phases' / 'fase_5v_validation_status.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding='utf-8')
        return path

    def write_authority(self, root: Path) -> Path:
        path = root / 'PROJECT_DESIGN.md'
        path.write_text('Este sistema REGISTRA, no OPERA.\nFase 5.V\nFase 6\n', encoding='utf-8')
        return path

    def write_config(self, root: Path, *, mode: str = 'none', enabled: bool = False, command: str = '', test_command: str = '') -> Path:
        path = root / 'config.json'
        path.write_text(json.dumps({
            'forbidden_paths': ['.env', 'data', 'PROJECT_DESIGN.md'],
            'executor_mode': mode,
            'executor_command': command,
            'executor_timeout_seconds': 5,
            'executor_enabled': enabled,
            'test_command': test_command,
        }), encoding='utf-8')
        return path

    def patch_paths(self, root: Path):
        return patch.multiple(
            project_controller,
            ROOT=root,
            CONFIG_PATH=root / 'config.json',
            AUTHORITY_PATH=root / 'PROJECT_DESIGN.md',
            VALIDATION_PATH=root / 'reports' / 'phases' / 'fase_5v_validation_status.json',
            TASK_PATH=root / 'tasks' / 'current_task.md',
            REPORTS_DIR=root / 'reports' / 'cycles',
            APPROVALS_DIR=root / 'reports' / 'approvals',
        )

    def test_current_state_waived_t4_stops_for_human_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_authority(root)
            self.write_config(root)
            self.write_status(root, {
                'T1': {'status': 'PASS'}, 'T2': {'status': 'PASS'}, 'T3': {'status': 'PASS'}, 'T4': {'status': 'WAIVED_BY_HUMAN'}, 'T5': {'status': 'PASS'}
            })
            with self.patch_paths(root):
                result, code = project_controller.run_cycle()
        self.assertEqual(0, code)
        self.assertEqual('PHASE_READY_WITH_ACCEPTED_RISK', result['status'])
        self.assertEqual('HUMAN_APPROVAL_WITH_ACCEPTED_RISK_STOP', result['runner_action'])
        self.assertNotIn('executor', result)

    def test_approved_waived_t4_advances_to_phase6_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_authority(root)
            self.write_config(root, mode='none', enabled=False)
            self.write_status(root, {
                'T1': {'status': 'PASS'}, 'T2': {'status': 'PASS'}, 'T3': {'status': 'PASS'}, 'T4': {'status': 'WAIVED_BY_HUMAN'}, 'T5': {'status': 'PASS'}
            })
            approval_path = root / 'reports' / 'approvals' / 'fase_5v_human_approval.json'
            approval_path.parent.mkdir(parents=True, exist_ok=True)
            approval_path.write_text(json.dumps({'allow_phase_6_preparation': True}), encoding='utf-8')
            with self.patch_paths(root):
                result, code = project_controller.run_cycle()
        self.assertEqual(0, code)
        self.assertEqual('Fase 6', result['phase'])
        self.assertEqual('PHASE_IN_PROGRESS', result['status'])
        self.assertEqual('F6_READINESS_REPORT', result['next_goal'])
        self.assertEqual('TASK_READY_NO_EXECUTOR', result['runner_action'])

    def test_all_pass_stops_for_human_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_authority(root)
            self.write_config(root)
            self.write_status(root, {
                'T1': {'status': 'PASS'}, 'T2': {'status': 'PASS'}, 'T3': {'status': 'PASS'}, 'T4': {'status': 'PASS'}, 'T5': {'status': 'PASS'}
            })
            with self.patch_paths(root):
                result, code = project_controller.run_cycle()
        self.assertEqual(0, code)
        self.assertEqual('PHASE_READY_FOR_HUMAN_APPROVAL', result['status'])
        self.assertEqual('HUMAN_APPROVAL_STOP', result['runner_action'])

    def test_pending_task_with_executor_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_authority(root)
            self.write_config(root)
            self.write_status(root, {
                'T1': {'status': 'PASS'}, 'T2': {'status': 'PASS'}, 'T3': {'status': 'PASS'}, 'T4': {'status': 'NOT_STARTED'}, 'T5': {'status': 'NOT_STARTED'}
            })
            with self.patch_paths(root):
                result, code = project_controller.run_cycle()
            self.assertEqual(0, code)
            self.assertEqual('PHASE_IN_PROGRESS', result['status'])
            self.assertEqual('TASK_READY_NO_EXECUTOR', result['runner_action'])
            self.assertIn('T5', (root / 'tasks' / 'current_task.md').read_text(encoding='utf-8'))

    def test_forbidden_path_detection_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_authority(root)
            self.write_config(root, mode='shell', enabled=True, command="python3 -c 'from pathlib import Path; Path(\"data/x\").parent.mkdir(parents=True, exist_ok=True); Path(\"data/x\").write_text(\"bad\")'")
            self.write_status(root, {
                'T1': {'status': 'PASS'}, 'T2': {'status': 'PASS'}, 'T3': {'status': 'PASS'}, 'T4': {'status': 'NOT_STARTED'}, 'T5': {'status': 'NOT_STARTED'}
            })
            with self.patch_paths(root):
                result, code = project_controller.run_cycle()
        self.assertEqual(1, code)
        self.assertEqual('AUDIT_BLOCKED', result['runner_action'])
        self.assertTrue(result['audit']['forbidden_touched'])

    def test_unknown_state_stops_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_authority(root)
            self.write_config(root)
            self.write_status(root, {
                'T1': {'status': 'PASS'}, 'T2': {'status': 'PASS'}, 'T3': {'status': 'PASS'}, 'T4': {'status': 'MAYBE'}, 'T5': {'status': 'PASS'}
            })
            with self.patch_paths(root):
                result, code = project_controller.run_cycle()
        self.assertEqual(0, code)
        self.assertEqual('PHASE_UNKNOWN_STATE', result['status'])
        self.assertEqual('NO_SAFE_ACTION', result['runner_action'])

    def test_max_cycles_cuts_correctly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_authority(root)
            self.write_config(root)
            self.write_status(root, {
                'T1': {'status': 'PASS'}, 'T2': {'status': 'PASS'}, 'T3': {'status': 'PASS'}, 'T4': {'status': 'NOT_STARTED'}, 'T5': {'status': 'NOT_STARTED'}
            })
            with self.patch_paths(root):
                with patch('sys.argv', ['project_controller.py', '--max-cycles', '3']):
                    code = project_controller.main()
            self.assertEqual(0, code)
            reports = list((root / 'reports' / 'cycles').glob('*_project_controller_cycle.json'))
            self.assertEqual(3, len(reports))


if __name__ == '__main__':
    unittest.main()
