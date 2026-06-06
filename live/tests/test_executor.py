from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.executor import Executor, ExecutorConfig


class ExecutorTests(unittest.TestCase):
    def test_mode_none_returns_task_ready_no_executor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = Executor(tmp, ExecutorConfig(mode='none', enabled=False)).run('task')
            self.assertEqual('TASK_READY_NO_EXECUTOR', result.status)

    def test_shell_success_returns_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = Executor(tmp, ExecutorConfig(mode='shell', command="python3 -c 'print(\"ok\")'", timeout_seconds=5, enabled=True)).run('task')
            self.assertEqual('PASS', result.status)
            self.assertIn('ok', result.stdout)

    def test_shell_failure_returns_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = Executor(tmp, ExecutorConfig(mode='shell', command="python3 -c 'import sys; sys.exit(2)'", timeout_seconds=5, enabled=True)).run('task')
            self.assertEqual('FAIL', result.status)
            self.assertEqual(2, result.exit_code)

    def test_timeout_returns_blocked_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = Executor(tmp, ExecutorConfig(mode='shell', command="python3 -c 'import time; time.sleep(2)'", timeout_seconds=1, enabled=True)).run('task')
            self.assertEqual('BLOCKED_EXECUTOR_TIMEOUT', result.status)
            self.assertTrue(result.timed_out)

    def test_forbidden_path_touched_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'data').mkdir()
            result = Executor(root, ExecutorConfig(mode='shell', command="python3 -c 'from pathlib import Path; Path(\"data/x\").write_text(\"bad\")'", timeout_seconds=5, enabled=True)).run('task')
            self.assertEqual('BLOCKED_FORBIDDEN_PATH', result.status)
            self.assertTrue(result.forbidden_touched)
            self.assertIn('data', result.forbidden_paths)

    def test_nested_forbidden_path_touched_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'data' / 'nested').mkdir(parents=True)
            result = Executor(root, ExecutorConfig(mode='shell', command="python3 -c 'from pathlib import Path; Path(\"data/nested/x\").write_text(\"bad\")'", timeout_seconds=5, enabled=True)).run('task')
            self.assertEqual('BLOCKED_FORBIDDEN_PATH', result.status)
            self.assertTrue(result.forbidden_touched)
            self.assertIn('data', result.forbidden_paths)

    def test_openclaw_agent_mode_blocks_when_not_configured(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = Executor(tmp, ExecutorConfig(mode='openclaw_agent', command='', enabled=True)).run('task')
            self.assertEqual('BLOCKED_EXECUTOR_NOT_CONFIGURED', result.status)
