from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.auto_migrate import build_full_migrate_command, next_stage_after_functional_check


class AutoMigrateTest(unittest.TestCase):
    def test_build_full_migrate_command_uses_reinstall_mode(self) -> None:
        command = build_full_migrate_command("owner/repo", build_mode="reinstall")

        self.assertEqual(
            command,
            ["python3", "scripts/full_migrate.py", "owner/repo", "--build-mode", "reinstall"],
        )

    def test_build_full_migrate_command_supports_resume(self) -> None:
        command = build_full_migrate_command("owner/repo", build_mode="reinstall", resume=True)

        self.assertEqual(command[-1], "--resume")

    def test_next_stage_requires_browser_pass(self) -> None:
        self.assertEqual(next_stage_after_functional_check("browser_pending"), "functional_pending")
        self.assertEqual(next_stage_after_functional_check("browser_failed"), "functional_failed")
        self.assertEqual(next_stage_after_functional_check("browser_pass"), "functional_passed")


if __name__ == "__main__":
    unittest.main()
