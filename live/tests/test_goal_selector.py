from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from core.goal_selector import load_validation_status, select_phase_5v_goal
from core.loop_policy import decide_from_phase_status, write_current_task


class GoalSelectorTests(unittest.TestCase):
    def write_status(self, payload: dict) -> Path:
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        path = Path(tmpdir.name) / 'status.json'
        path.write_text(json.dumps(payload), encoding='utf-8')
        return path

    def test_current_state_produces_blocked_deferred_t4(self) -> None:
        path = self.write_status({
            'T1': {'status': 'PASS'},
            'T2': {'status': 'PASS'},
            'T3': {'status': 'PASS'},
            'T4': {'status': 'DEFERRED_MANUAL_NETWORK_CUT'},
            'T5': {'status': 'PASS'},
        })
        decision = decide_from_phase_status(path)
        self.assertEqual('PHASE_BLOCKED_DEFERRED_T4', decision.status)
        self.assertEqual('manual T4 network cut', decision.next_goal)
        self.assertFalse(decision.phase_complete)

    def test_deferred_t4_and_t5_not_started_selects_t5(self) -> None:
        path = self.write_status({
            'T1': {'status': 'PASS'},
            'T2': {'status': 'PASS'},
            'T3': {'status': 'PASS'},
            'T4': {'status': 'DEFERRED_MANUAL_NETWORK_CUT'},
            'T5': {'status': 'NOT_STARTED'},
        })
        decision = decide_from_phase_status(path)
        self.assertEqual('PHASE_IN_PROGRESS', decision.status)
        self.assertEqual('T5', decision.next_goal)
        self.assertFalse(decision.phase_complete)

    def test_all_pass_yields_ready_for_human_approval(self) -> None:
        path = self.write_status({
            'T1': {'status': 'PASS'},
            'T2': {'status': 'PASS'},
            'T3': {'status': 'PASS'},
            'T4': {'status': 'PASS'},
            'T5': {'status': 'PASS'},
        })
        decision = decide_from_phase_status(path)
        self.assertEqual('PHASE_READY_FOR_HUMAN_APPROVAL', decision.status)
        self.assertEqual('human approval', decision.next_goal)
        self.assertTrue(decision.phase_complete)

    def test_waived_t4_yields_ready_with_accepted_risk(self) -> None:
        path = self.write_status({
            'T1': {'status': 'PASS'},
            'T2': {'status': 'PASS'},
            'T3': {'status': 'PASS'},
            'T4': {'status': 'WAIVED_BY_HUMAN'},
            'T5': {'status': 'PASS'},
        })
        decision = decide_from_phase_status(path)
        self.assertEqual('PHASE_READY_WITH_ACCEPTED_RISK', decision.status)
        self.assertEqual('human approval with accepted T4 risk', decision.next_goal)
        self.assertTrue(decision.phase_complete)

    def test_normalizes_defered_typo(self) -> None:
        path = self.write_status({
            'T1': {'status': 'PASS'},
            'T2': {'status': 'PASS'},
            'T3': {'status': 'PASS'},
            'T4': {'status': 'DEFERED_MANUAL_NETWORK_CUT'},
            'T5': {'status': 'PASS'},
        })
        data = load_validation_status(path)
        self.assertEqual('DEFERRED_MANUAL_NETWORK_CUT', data['T4']['status'])

    def test_normalizes_accepted_risk_deferred_to_waived_by_human(self) -> None:
        path = self.write_status({
            'T1': {'status': 'PASS'},
            'T2': {'status': 'PASS'},
            'T3': {'status': 'PASS'},
            'T4': {'status': 'ACCEPTED_RISK_DEFERRED'},
            'T5': {'status': 'PASS'},
        })
        data = load_validation_status(path)
        self.assertEqual('WAIVED_BY_HUMAN', data['T4']['status'])

    def test_write_current_task_updates_task_file(self) -> None:
        path = self.write_status({
            'T1': {'status': 'PASS'},
            'T2': {'status': 'PASS'},
            'T3': {'status': 'PASS'},
            'T4': {'status': 'DEFERRED_MANUAL_NETWORK_CUT'},
            'T5': {'status': 'NOT_STARTED'},
        })
        decision = decide_from_phase_status(path)
        with tempfile.TemporaryDirectory() as tmp:
            task_path = Path(tmp) / 'current_task.md'
            write_current_task(task_path, decision)
            self.assertIn('T5', task_path.read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
