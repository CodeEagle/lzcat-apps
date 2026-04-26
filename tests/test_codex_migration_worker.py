from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.codex_migration_worker import (
    CodexWorkerConfig,
    build_codex_command,
    build_codex_prompt,
    safe_task_name,
    write_notification,
    write_task_bundle,
)


class CodexMigrationWorkerTest(unittest.TestCase):
    def make_repo_root(self) -> Path:
        return Path(tempfile.mkdtemp(prefix="codex-worker-test-"))

    def test_safe_task_name_keeps_identifier_readable(self) -> None:
        self.assertEqual(safe_task_name("github:owner/demo"), "github-owner-demo")

    def test_build_codex_prompt_includes_failure_and_guardrails(self) -> None:
        repo_root = self.make_repo_root()
        item = {
            "id": "github:owner/demo",
            "source": "owner/demo",
            "slug": "demo",
            "state": "build_failed",
            "last_error": "compose parser failed",
        }

        prompt = build_codex_prompt(
            repo_root,
            item,
            box_domain="box.example.test",
            recent_logs="RuntimeError: compose parser failed",
        )

        self.assertIn("owner/demo", prompt)
        self.assertIn("compose parser failed", prompt)
        self.assertIn("box.example.test", prompt)
        self.assertIn("Do not submit", prompt)
        self.assertIn("scripts/full_migrate.py", prompt)

    def test_build_codex_command_uses_noninteractive_exec(self) -> None:
        repo_root = self.make_repo_root()
        config = CodexWorkerConfig(repo_root=repo_root, task_dir=repo_root / "tasks" / "demo")

        command = build_codex_command(config)

        self.assertEqual(command[:4], ["codex", "exec", "-C", str(repo_root)])
        self.assertIn("--sandbox", command)
        self.assertIn("danger-full-access", command)
        self.assertIn("--ask-for-approval", command)
        self.assertIn("never", command)
        self.assertEqual(command[-1], "-")

    def test_write_task_bundle_writes_prompt_and_metadata(self) -> None:
        repo_root = self.make_repo_root()
        item = {"id": "github:owner/demo", "source": "owner/demo", "slug": "demo", "state": "build_failed"}
        config = CodexWorkerConfig(repo_root=repo_root, task_dir=repo_root / "tasks" / "demo")

        bundle = write_task_bundle(config, item, prompt="Fix this", command=["codex", "exec"], now="2026-04-26T00:00:00Z")

        self.assertEqual((config.task_dir / "prompt.md").read_text(encoding="utf-8"), "Fix this")
        metadata = json.loads((config.task_dir / "task.json").read_text(encoding="utf-8"))
        self.assertEqual(metadata["item"]["id"], "github:owner/demo")
        self.assertEqual(bundle["prompt_path"], str(config.task_dir / "prompt.md"))

    def test_write_notification_creates_outbox_markdown(self) -> None:
        repo_root = self.make_repo_root()
        outbox = repo_root / "outbox"
        item = {"id": "github:owner/demo", "source": "owner/demo", "slug": "demo", "state": "build_failed"}

        path = write_notification(
            outbox,
            item,
            status="completed",
            task_dir=repo_root / "tasks" / "demo",
            now="2026-04-26T00:00:00Z",
        )

        content = path.read_text(encoding="utf-8")
        self.assertIn("owner/demo", content)
        self.assertIn("completed", content)
        self.assertIn("tasks/demo", content)


if __name__ == "__main__":
    unittest.main()
