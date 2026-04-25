from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.auto_migrate import (
    build_full_migrate_command,
    existing_app_guard_reason,
    infer_slug_from_source,
    next_stage_after_functional_check,
)


class AutoMigrateTest(unittest.TestCase):
    def test_build_full_migrate_command_uses_reinstall_mode(self) -> None:
        command = build_full_migrate_command("owner/repo", build_mode="reinstall")

        self.assertEqual(
            command,
            ["python3", "scripts/full_migrate.py", "owner/repo", "--build-mode", "reinstall", "--no-commit"],
        )

    def test_build_full_migrate_command_supports_resume(self) -> None:
        command = build_full_migrate_command("owner/repo", build_mode="reinstall", resume=True)

        self.assertEqual(command[-1], "--resume")

    def test_build_full_migrate_command_can_enable_scaffold_commit(self) -> None:
        command = build_full_migrate_command("owner/repo", build_mode="reinstall", commit_scaffold=True)

        self.assertNotIn("--no-commit", command)

    def test_next_stage_requires_browser_pass(self) -> None:
        self.assertEqual(next_stage_after_functional_check("browser_pending"), "functional_pending")
        self.assertEqual(next_stage_after_functional_check("browser_failed"), "functional_failed")
        self.assertEqual(next_stage_after_functional_check("browser_pass"), "functional_passed")

    def test_infer_slug_from_github_source(self) -> None:
        self.assertEqual(infer_slug_from_source("https://github.com/microsoft/markitdown.git"), "markitdown")
        self.assertEqual(infer_slug_from_source("owner/demo-app"), "demo-app")

    def test_existing_app_guard_blocks_without_resume_or_allow(self) -> None:
        reason = existing_app_guard_reason(Path("/repo"), "owner/demo", app_exists=True)

        self.assertIn("already exists", reason)

    def test_existing_app_guard_allows_resume(self) -> None:
        reason = existing_app_guard_reason(Path("/repo"), "owner/demo", app_exists=True, resume=True)

        self.assertEqual(reason, "")


if __name__ == "__main__":
    unittest.main()
