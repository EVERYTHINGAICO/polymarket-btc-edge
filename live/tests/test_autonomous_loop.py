from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scripts.autonomous_loop as autonomous_loop
from core.executor import ExecutionResult
from core.goal_selector import GoalDecision


class AutonomousLoopTests(unittest.TestCase):
    def test_blocked_deferred_t4_stops_cleanly(self) -> None:
        with patch.object(autonomous_loop, 'decide_from_phase_status', return_value=GoalDecision('PHASE_BLOCKED_DEFERRED_T4', 'manual T4 network cut', False, 'blocked\n')):
            with tempfile.TemporaryDirectory() as tmp:
                task_path = Path(tmp) / 'current_task.md'
                with patch.object(autonomous_loop, 'CURRENT_TASK_PATH', task_path):
                    result, code = autonomous_loop.run_once()
        self.assertEqual(0, code)
        self.assertEqual('HUMAN_GATE_STOP', result['runner_action'])
        self.assertEqual('PHASE_BLOCKED_DEFERRED_T4', result['status'])

    def test_deferred_t4_and_t5_not_started_prepares_t5(self) -> None:
        fake_exec = ExecutionResult('TASK_READY_NO_EXECUTOR', 'none', '', None, '', '', False, False, [], 0.0)
        with patch.object(autonomous_loop, 'decide_from_phase_status', return_value=GoalDecision('PHASE_IN_PROGRESS', 'T5', False, 'Next goal: T5\n')):
            with patch.object(autonomous_loop.Executor, 'run', return_value=fake_exec):
                with tempfile.TemporaryDirectory() as tmp:
                    task_path = Path(tmp) / 'current_task.md'
                    with patch.object(autonomous_loop, 'CURRENT_TASK_PATH', task_path):
                        result, code = autonomous_loop.run_once()
                        written = task_path.read_text(encoding='utf-8')
        self.assertEqual(0, code)
        self.assertEqual('TASK_READY_NO_EXECUTOR', result['runner_action'])
        self.assertEqual('T5', result['next_goal'])
        self.assertIn('T5', written)

    def test_all_pass_stops_for_human_approval(self) -> None:
        with patch.object(autonomous_loop, 'decide_from_phase_status', return_value=GoalDecision('PHASE_READY_FOR_HUMAN_APPROVAL', 'human approval', True, 'ready\n')):
            with tempfile.TemporaryDirectory() as tmp:
                task_path = Path(tmp) / 'current_task.md'
                with patch.object(autonomous_loop, 'CURRENT_TASK_PATH', task_path):
                    result, code = autonomous_loop.run_once()
        self.assertEqual(0, code)
        self.assertEqual('HUMAN_APPROVAL_STOP', result['runner_action'])
        self.assertTrue(result['phase_complete'])

    def test_ready_with_accepted_risk_stops_for_human_approval(self) -> None:
        with patch.object(autonomous_loop, 'decide_from_phase_status', return_value=GoalDecision('PHASE_READY_WITH_ACCEPTED_RISK', 'human approval with accepted T4 risk', True, 'accepted risk\n')):
            with patch.object(autonomous_loop.Executor, 'run') as run_mock:
                with tempfile.TemporaryDirectory() as tmp:
                    task_path = Path(tmp) / 'current_task.md'
                    with patch.object(autonomous_loop, 'CURRENT_TASK_PATH', task_path):
                        result, code = autonomous_loop.run_once()
        self.assertEqual(0, code)
        self.assertEqual('HUMAN_APPROVAL_WITH_ACCEPTED_RISK_STOP', result['runner_action'])
        self.assertEqual('Fase lista para aprobación humana con riesgo T4 aceptado.', result['message'])
        self.assertEqual('PHASE_READY_WITH_ACCEPTED_RISK', result['status'])
        self.assertTrue(result['phase_complete'])
        run_mock.assert_not_called()

    def test_no_safe_action_exits_cleanly(self) -> None:
        with patch.object(autonomous_loop, 'decide_from_phase_status', return_value=GoalDecision('PHASE_UNKNOWN_STATE', 'human review', False, 'review\n')):
            with tempfile.TemporaryDirectory() as tmp:
                task_path = Path(tmp) / 'current_task.md'
                with patch.object(autonomous_loop, 'CURRENT_TASK_PATH', task_path):
                    result, code = autonomous_loop.run_once()
        self.assertEqual(0, code)
        self.assertEqual('NO_SAFE_ACTION', result['runner_action'])

    def test_phase_in_progress_calls_executor_once(self) -> None:
        fake_exec = ExecutionResult('TASK_READY_NO_EXECUTOR', 'none', '', None, '', '', False, False, [], 0.0)
        with patch.object(autonomous_loop, 'decide_from_phase_status', return_value=GoalDecision('PHASE_IN_PROGRESS', 'T5', False, 'Next goal: T5\n')):
            with patch.object(autonomous_loop.Executor, 'run', return_value=fake_exec) as run_mock:
                with tempfile.TemporaryDirectory() as tmp:
                    task_path = Path(tmp) / 'current_task.md'
                    with patch.object(autonomous_loop, 'CURRENT_TASK_PATH', task_path):
                        result, code = autonomous_loop.run_once()
        self.assertEqual(0, code)
        self.assertEqual(1, run_mock.call_count)
        self.assertEqual('TASK_READY_NO_EXECUTOR', result['runner_action'])

    def test_shell_executor_pass_path(self) -> None:
        fake_exec = ExecutionResult('PASS', 'shell', 'echo ok', 0, 'ok', '', False, False, [], 0.01)
        fake_test = ExecutionResult('PASS', 'shell', 'pytest', 0, 'ok', '', False, False, [], 0.01)
        with patch.object(autonomous_loop, 'decide_from_phase_status', return_value=GoalDecision('PHASE_IN_PROGRESS', 'T5', False, 'Next goal: T5\n')):
            with patch.object(autonomous_loop.Executor, 'run', return_value=fake_exec):
                with patch.object(autonomous_loop.Executor, 'run_tests', return_value=fake_test):
                    with tempfile.TemporaryDirectory() as tmp:
                        task_path = Path(tmp) / 'current_task.md'
                        with patch.object(autonomous_loop, 'CURRENT_TASK_PATH', task_path):
                            result, code = autonomous_loop.run_once()
        self.assertEqual(0, code)
        self.assertEqual('EXECUTOR_PASS', result['runner_action'])

    def test_shell_executor_fail_path(self) -> None:
        fake_exec = ExecutionResult('FAIL', 'shell', 'bad', 1, '', 'err', False, False, [], 0.01)
        with patch.object(autonomous_loop, 'decide_from_phase_status', return_value=GoalDecision('PHASE_IN_PROGRESS', 'T5', False, 'Next goal: T5\n')):
            with patch.object(autonomous_loop.Executor, 'run', return_value=fake_exec):
                with tempfile.TemporaryDirectory() as tmp:
                    task_path = Path(tmp) / 'current_task.md'
                    with patch.object(autonomous_loop, 'CURRENT_TASK_PATH', task_path):
                        result, code = autonomous_loop.run_once()
        self.assertEqual(1, code)
        self.assertEqual('FAIL', result['runner_action'])
