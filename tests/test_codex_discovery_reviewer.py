from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.codex_discovery_reviewer import (
    DiscoveryReviewerConfig,
    build_codex_command,
    build_codex_prompt,
    run_codex,
    safe_task_name,
    write_task_bundle,
)


class CodexDiscoveryReviewerTest(unittest.TestCase):
    def make_repo_root(self) -> Path:
        return Path(tempfile.mkdtemp(prefix="codex-discovery-reviewer-test-"))

    def test_build_codex_prompt_contains_decision_contract(self) -> None:
        repo_root = self.make_repo_root()
        queue_path = repo_root / "registry" / "auto-migration" / "queue.json"
        item = {
            "id": "github:owner/demo",
            "source": "owner/demo",
            "slug": "demo",
            "state": "discovery_review",
            "candidate": {"status": "needs_review", "status_reason": "Name matches existing app weakly"},
        }

        prompt = build_codex_prompt(repo_root, queue_path, item, developer_url="https://lazycat.cloud/appstore/more/developers/178")

        self.assertIn("owner/demo", prompt)
        self.assertIn("migrate", prompt)
        self.assertIn("skip", prompt)
        self.assertIn("needs_human", prompt)
        self.assertIn("waiting_for_human", prompt)
        self.assertIn("discovery_review", prompt)
        self.assertIn("developer", prompt)

    def test_build_codex_prompt_includes_store_search_hit_contract(self) -> None:
        repo_root = self.make_repo_root()
        queue_path = repo_root / "registry" / "auto-migration" / "queue.json"
        item = {
            "id": "local-agent:paperclipai/paperclip",
            "source": "paperclipai/paperclip",
            "slug": "paperclip",
            "state": "discovery_review",
            "candidate": {
                "status": "needs_review",
                "lazycat_hits": [
                    {
                        "raw_label": "Paperclip AI",
                        "detail_url": "https://lazycat.cloud/appstore/paperclip",
                        "reason": "name match",
                    }
                ],
                "ai_store_review": {"status": "pending", "source": "lazycat_store_search"},
            },
        }

        prompt = build_codex_prompt(repo_root, queue_path, item)

        self.assertIn("LazyCat app-store search hits", prompt)
        self.assertIn("Paperclip AI", prompt)
        self.assertIn("https://lazycat.cloud/appstore/paperclip", prompt)
        self.assertIn("choose `needs_human`; do not guess", prompt)
        self.assertIn("choose `skip` and cite the hit", prompt)

    def test_build_codex_command_uses_noninteractive_exec(self) -> None:
        repo_root = self.make_repo_root()
        config = DiscoveryReviewerConfig(
            repo_root=repo_root,
            queue_path=repo_root / "queue.json",
            task_dir=repo_root / "tasks" / "demo",
        )

        command = build_codex_command(config)

        self.assertEqual(command[:4], ["codex", "--ask-for-approval", "never", "exec"])
        self.assertIn("--sandbox", command)
        self.assertIn("danger-full-access", command)
        self.assertIn("--model", command)
        self.assertIn("gpt-5.5", command)
        self.assertEqual(command[-1], "-")

    def test_write_task_bundle_writes_prompt_and_metadata(self) -> None:
        repo_root = self.make_repo_root()
        item = {"id": "github:owner/demo", "source": "owner/demo", "slug": "demo", "state": "discovery_review"}
        config = DiscoveryReviewerConfig(
            repo_root=repo_root,
            queue_path=repo_root / "queue.json",
            task_dir=repo_root / "tasks" / "demo",
        )

        bundle = write_task_bundle(config, item, prompt="Review this", command=["codex", "exec"], now="2026-04-26T00:00:00Z")

        self.assertEqual((config.task_dir / "prompt.md").read_text(encoding="utf-8"), "Review this")
        metadata = json.loads((config.task_dir / "task.json").read_text(encoding="utf-8"))
        self.assertEqual(metadata["queue_path"], str(config.queue_path))
        self.assertEqual(metadata["item"]["id"], "github:owner/demo")
        self.assertEqual(bundle["prompt_path"], str(config.task_dir / "prompt.md"))

    def test_safe_task_name_keeps_identifier_readable(self) -> None:
        self.assertEqual(safe_task_name("github:owner/demo"), "github-owner-demo")

    def test_run_codex_falls_back_when_cli_rejects_default_model(self) -> None:
        repo_root = self.make_repo_root()
        config = DiscoveryReviewerConfig(
            repo_root=repo_root,
            queue_path=repo_root / "queue.json",
            task_dir=repo_root / "tasks" / "demo",
            model="gpt-5.5",
        )
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
            if len(calls) == 1:
                return Result(1, stderr="The 'gpt-5.5' model requires a newer version of Codex.")
            return Result(0, stdout="fallback ok")

        with patch("scripts.codex_discovery_reviewer.subprocess.run", side_effect=fake_run):
            returncode = run_codex(config, "prompt", command)

        self.assertEqual(returncode, 0)
        self.assertEqual(calls[0][calls[0].index("--model") + 1], "gpt-5.5")
        self.assertEqual(calls[1][calls[1].index("--model") + 1], "gpt-5.4")
        self.assertIn("fallback ok", (config.task_dir / "codex.stdout.log").read_text(encoding="utf-8"))
        self.assertTrue((config.task_dir / "model-fallback.json").exists())


if __name__ == "__main__":
    unittest.main()
