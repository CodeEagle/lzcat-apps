from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.auto_migrate import (
    build_full_migrate_command,
    candidate_source,
    existing_app_guard_reason,
    infer_slug_from_source,
    load_candidate_snapshot,
    next_stage_after_functional_check,
    resolve_migration_source,
    select_next_candidate,
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

    def test_select_next_candidate_picks_first_portable_candidate(self) -> None:
        payload = {
            "candidates": [
                {"full_name": "owner/done", "status": "already_migrated"},
                {"full_name": "owner/in-flight", "status": "in_progress"},
                {"full_name": "owner/demo", "status": "portable"},
            ]
        }

        candidate = select_next_candidate(payload)

        self.assertEqual(candidate["full_name"], "owner/demo")

    def test_select_next_candidate_allows_explicit_statuses(self) -> None:
        payload = {
            "candidates": [
                {"full_name": "owner/review", "status": "needs_review"},
                {"full_name": "owner/demo", "status": "portable"},
            ]
        }

        candidate = select_next_candidate(payload, allowed_statuses=("needs_review",))

        self.assertEqual(candidate["full_name"], "owner/review")

    def test_candidate_source_prefers_full_name(self) -> None:
        self.assertEqual(
            candidate_source({"full_name": "owner/demo", "repo_url": "https://github.com/owner/demo"}),
            "owner/demo",
        )

    def test_load_candidate_snapshot_reads_json(self) -> None:
        repo_root = Path(tempfile.mkdtemp(prefix="auto-migrate-candidates-"))
        snapshot_path = repo_root / "registry" / "candidates" / "latest.json"
        snapshot_path.parent.mkdir(parents=True)
        snapshot_path.write_text(
            json.dumps({"candidates": [{"full_name": "owner/demo", "status": "portable"}]}) + "\n",
            encoding="utf-8",
        )

        payload = load_candidate_snapshot(repo_root, "registry/candidates/latest.json")

        self.assertEqual(payload["candidates"][0]["full_name"], "owner/demo")

    def test_resolve_migration_source_from_candidates(self) -> None:
        repo_root = Path(tempfile.mkdtemp(prefix="auto-migrate-candidates-"))
        snapshot_path = repo_root / "registry" / "candidates" / "latest.json"
        snapshot_path.parent.mkdir(parents=True)
        snapshot_path.write_text(
            json.dumps({"candidates": [{"full_name": "owner/demo", "status": "portable"}]}) + "\n",
            encoding="utf-8",
        )

        source = resolve_migration_source(repo_root, None, candidates_path="registry/candidates/latest.json")

        self.assertEqual(source, "owner/demo")

    def test_resolve_migration_source_rejects_explicit_source_with_candidates(self) -> None:
        repo_root = Path(tempfile.mkdtemp(prefix="auto-migrate-candidates-"))

        with self.assertRaises(ValueError):
            resolve_migration_source(repo_root, "owner/demo", candidates_path="registry/candidates/latest.json")


if __name__ == "__main__":
    unittest.main()
