from __future__ import annotations

import importlib
import unittest
from pathlib import Path


class ScaffoldTests(unittest.TestCase):
    def test_phase0_scaffold_files_exist(self) -> None:
        required = [
            Path("README.md"),
            Path("requirements.txt"),
            Path(".env.example"),
            Path("config.py"),
            Path("src/__init__.py"),
            Path("src/db.py"),
            Path("tests/test_db.py"),
        ]
        missing = [str(path) for path in required if not path.exists()]
        self.assertEqual([], missing)

    def test_project_modules_import_cleanly(self) -> None:
        for module_name in [
            "config",
            "src",
            "src.deribit_feed",
            "src.signal",
            "src.polymarket_feed",
            "src.logger",
            "src.db",
        ]:
            module = importlib.import_module(module_name)
            self.assertIsNotNone(module)


if __name__ == "__main__":
    unittest.main()
