from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.codex_migration_worker import (
    CodexWorkerConfig,
    build_codex_command,
    build_codex_prompt,
    extract_session_id_from_jsonl,
    run_codex,
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

    def test_build_codex_prompt_includes_human_help_contract(self) -> None:
        repo_root = self.make_repo_root()
        item = {"id": "github:owner/demo", "source": "owner/demo", "slug": "demo", "state": "browser_failed"}

        prompt = build_codex_prompt(repo_root, item, box_domain="box.example.test")

        self.assertIn("waiting_for_human", prompt)
        self.assertIn("human_request", prompt)
        self.assertIn("Discord", prompt)
        self.assertIn("credentials", prompt)

    def test_build_codex_command_invokes_claude_cli_unattended(self) -> None:
        repo_root = self.make_repo_root()
        config = CodexWorkerConfig(repo_root=repo_root, task_dir=repo_root / "tasks" / "demo")

        command = build_codex_command(config)

        self.assertEqual(command[0], "claude")
        self.assertIn("--print", command)
        self.assertIn("--dangerously-skip-permissions", command)
        self.assertIn("--add-dir", command)
        self.assertIn(str(repo_root), command)
        self.assertIn("--model", command)
        self.assertIn("claude-sonnet-4-6", command)
        # stream-json + verbose so we can extract session_id from the event log.
        self.assertIn("--output-format", command)
        self.assertIn("stream-json", command)
        self.assertNotIn("--ask-for-approval", command)
        self.assertNotIn("--sandbox", command)

    def test_build_codex_command_resumes_existing_session(self) -> None:
        repo_root = self.make_repo_root()
        session_id = "11111111-2222-3333-4444-555555555555"
        config = CodexWorkerConfig(repo_root=repo_root, task_dir=repo_root / "tasks" / "demo", session_id=session_id)

        command = build_codex_command(config)

        self.assertIn("--resume", command)
        self.assertEqual(command[command.index("--resume") + 1], session_id)

    def test_extract_session_id_from_jsonl_reads_nested_codex_event(self) -> None:
        output = "\n".join(
            [
                json.dumps({"type": "task.started", "payload": {"session_id": "11111111-2222-3333-4444-555555555555"}}),
                json.dumps({"type": "message", "id": "not-a-session-id"}),
            ]
        )

        self.assertEqual(extract_session_id_from_jsonl(output), "11111111-2222-3333-4444-555555555555")

    def test_write_task_bundle_writes_prompt_and_metadata(self) -> None:
        repo_root = self.make_repo_root()
        item = {
            "id": "github:owner/demo",
            "source": "owner/demo",
            "slug": "demo",
            "state": "build_failed",
            "codex": {"session_id": "11111111-2222-3333-4444-555555555555"},
        }
        config = CodexWorkerConfig(
            repo_root=repo_root,
            task_dir=repo_root / "tasks" / "demo",
            session_id="11111111-2222-3333-4444-555555555555",
        )

        bundle = write_task_bundle(config, item, prompt="Fix this", command=["codex", "exec"], now="2026-04-26T00:00:00Z")

        self.assertEqual((config.task_dir / "prompt.md").read_text(encoding="utf-8"), "Fix this")
        metadata = json.loads((config.task_dir / "task.json").read_text(encoding="utf-8"))
        self.assertEqual(metadata["item"]["id"], "github:owner/demo")
        self.assertEqual(metadata["session_id"], "11111111-2222-3333-4444-555555555555")
        self.assertTrue(metadata["resumed"])
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

    def test_run_codex_writes_stdout_and_stderr_logs(self) -> None:
        repo_root = self.make_repo_root()
        config = CodexWorkerConfig(repo_root=repo_root, task_dir=repo_root / "tasks" / "demo", model="claude-sonnet-4-6")
        config.task_dir.mkdir(parents=True)
        command = build_codex_command(config)

        class Result:
            def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
                self.returncode = returncode
                self.stdout = stdout
                self.stderr = stderr

        calls: list[list[str]] = []

        def fake_run(command_arg: list[str], **kwargs: object) -> Result:
            calls.append(command_arg)
            return Result(0, stdout="repair ok", stderr="warn")

        with patch("scripts.codex_migration_worker.subprocess.run", side_effect=fake_run):
            result = run_codex(config, "prompt", command)

        self.assertEqual(result.returncode, 0)
        self.assertEqual(len(calls), 1)   # No fallback path on claude.
        self.assertEqual(calls[0][calls[0].index("--model") + 1], "claude-sonnet-4-6")
        self.assertIn("repair ok", (config.task_dir / "claude.stdout.log").read_text(encoding="utf-8"))
        self.assertIn("warn", (config.task_dir / "claude.stderr.log").read_text(encoding="utf-8"))
        self.assertFalse((config.task_dir / "model-fallback.json").exists())

    def test_run_codex_returns_session_id_from_stream_json(self) -> None:
        repo_root = self.make_repo_root()
        config = CodexWorkerConfig(repo_root=repo_root, task_dir=repo_root / "tasks" / "demo")
        config.task_dir.mkdir(parents=True)
        command = build_codex_command(config)

        class Result:
            returncode = 0
            stdout = json.dumps({"type": "system", "session_id": "11111111-2222-3333-4444-555555555555"})
            stderr = ""

        with patch("scripts.codex_migration_worker.subprocess.run", return_value=Result()):
            result = run_codex(config, "prompt", command)

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.session_id, "11111111-2222-3333-4444-555555555555")


if __name__ == "__main__":
    unittest.main()
