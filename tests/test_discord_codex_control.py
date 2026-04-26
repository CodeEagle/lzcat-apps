from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.discord_codex_control import (
    CodexControlConfig,
    CodexControlRunResult,
    CodexControlTask,
    mark_existing_messages_seen,
    parse_control_message,
    parse_control_command,
    process_codex_control_commands,
)
from scripts.discord_migration_notifier import DiscordClient


class DiscordCodexControlTest(unittest.TestCase):
    def make_repo_root(self) -> Path:
        return Path(tempfile.mkdtemp(prefix="discord-codex-control-test-"))

    def write_queue(self, repo_root: Path, *, workspace_path: Path | None = None) -> Path:
        queue_path = repo_root / "registry" / "auto-migration" / "queue.json"
        queue_path.parent.mkdir(parents=True)
        item: dict[str, object] = {
            "id": "github:rcarmo/piclaw",
            "source": "rcarmo/piclaw",
            "slug": "piclaw",
            "state": "browser_failed",
            "candidate": {"description": "Photo rights helper"},
        }
        if workspace_path:
            item["workspace_path"] = str(workspace_path)
        queue_path.write_text(json.dumps({"schema_version": 1, "items": [item]}) + "\n", encoding="utf-8")
        return queue_path

    def make_config(self, repo_root: Path, *, workspace_root: Path | None = None) -> CodexControlConfig:
        return CodexControlConfig(
            repo_root=repo_root,
            queue_path=repo_root / "registry" / "auto-migration" / "queue.json",
            state_path=repo_root / "registry" / "auto-migration" / "discord-codex-control.json",
            task_root=repo_root / "registry" / "auto-migration" / "codex-control-tasks",
            workspace_root=workspace_root or repo_root / "migration-workspaces",
            guild_id="guild-1",
            category_id="category-1",
            channel_prefix="migration",
            control_channel="migration-control",
            mention_role_ids=("role-1",),
            model="gpt-5.5",
        )

    def test_parse_direct_and_mention_commands(self) -> None:
        self.assertEqual(parse_control_command("!status").kind, "status")
        self.assertEqual(parse_control_command("!codex 修一下截图").instruction, "修一下截图")
        self.assertEqual(parse_control_command("!fix").kind, "codex")
        self.assertEqual(parse_control_command("<@123> status", bot_user_id="123").kind, "status")
        self.assertEqual(parse_control_command("<@123> 继续处理", bot_user_id="123").instruction, "继续处理")
        self.assertIsNone(parse_control_command("<@123> 继续处理"))
        self.assertIsNone(parse_control_command("<@999> 继续处理", bot_user_id="123"))
        self.assertIsNone(parse_control_command("随便聊一句"))

    def test_parse_empty_role_mention_as_content_unavailable(self) -> None:
        repo_root = self.make_repo_root()
        config = self.make_config(repo_root)
        message = {"content": "", "mention_roles": ["role-1"], "author": {"id": "u1"}}

        parsed = parse_control_message(message, config)

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.kind, "content_unavailable")

    def test_process_migration_channel_runs_codex_with_worktree_context(self) -> None:
        repo_root = self.make_repo_root()
        workspace_path = repo_root / "migration-workspaces" / "migration-piclaw"
        workspace_path.mkdir(parents=True)
        self.write_queue(repo_root, workspace_path=workspace_path)
        config = self.make_config(repo_root)
        events: list[tuple[str, str, dict[str, object] | None]] = []
        tasks: list[CodexControlTask] = []

        def transport(method: str, route: str, payload: dict[str, object] | None = None) -> object:
            events.append((method, route, payload))
            if method == "GET" and route == "/guilds/guild-1/channels":
                return [
                    {"id": "control-1", "name": "migration-control", "type": 0, "parent_id": "category-1"},
                    {"id": "piclaw-1", "name": "migration-piclaw", "type": 0, "parent_id": "category-1"},
                ]
            if method == "GET" and route == "/channels/control-1/messages?limit=20":
                return []
            if method == "GET" and route == "/channels/piclaw-1/messages?limit=20":
                return [{"id": "100", "content": "!fix 修复网页截图流程", "author": {"id": "u1"}}]
            if method == "PUT" and route == "/channels/piclaw-1/messages/100/reactions/%F0%9F%91%80/@me":
                return {}
            if method == "PUT" and route == "/channels/piclaw-1/messages/100/reactions/%F0%9F%94%A7/@me":
                return {}
            if method == "POST" and route == "/channels/piclaw-1/messages":
                return {"id": f"reply-{len(events)}"}
            raise AssertionError(f"unexpected Discord call {method} {route}")

        def runner(task: CodexControlTask) -> CodexControlRunResult:
            events.append(("RUNNER", "codex", None))
            tasks.append(task)
            return CodexControlRunResult("completed", 0, "已修复并验证。", task.task_dir)

        results = process_codex_control_commands(
            config,
            DiscordClient("token", transport=transport),
            runner=runner,
            now="2026-04-26T10:00:00Z",
        )

        self.assertEqual(results, [{"channel_id": "piclaw-1", "message_id": "100", "status": "completed"}])
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].context.slug, "piclaw")
        self.assertEqual(tasks[0].context.workdir, workspace_path)
        self.assertIn("修复网页截图流程", tasks[0].prompt)
        self.assertIn("rcarmo/piclaw", tasks[0].prompt)
        self.assertIn(str(workspace_path), tasks[0].command)
        self.assertLess(
            events.index(("PUT", "/channels/piclaw-1/messages/100/reactions/%F0%9F%91%80/@me", None)),
            next(index for index, event in enumerate(events) if event[0:2] == ("POST", "/channels/piclaw-1/messages")),
        )
        self.assertLess(
            events.index(("PUT", "/channels/piclaw-1/messages/100/reactions/%F0%9F%94%A7/@me", None)),
            events.index(("RUNNER", "codex", None)),
        )
        self.assertEqual(sum(1 for event in events if event[0:2] == ("POST", "/channels/piclaw-1/messages")), 2)
        state = json.loads(config.state_path.read_text(encoding="utf-8"))
        self.assertEqual(state["channels"]["piclaw-1"]["last_message_id"], "100")

    def test_status_command_does_not_run_codex(self) -> None:
        repo_root = self.make_repo_root()
        workspace_path = repo_root / "migration-workspaces" / "migration-piclaw"
        workspace_path.mkdir(parents=True)
        self.write_queue(repo_root, workspace_path=workspace_path)
        config = self.make_config(repo_root)
        replies: list[str] = []

        def transport(method: str, route: str, payload: dict[str, object] | None = None) -> object:
            if method == "GET" and route == "/guilds/guild-1/channels":
                return [
                    {"id": "control-1", "name": "migration-control", "type": 0, "parent_id": "category-1"},
                    {"id": "piclaw-1", "name": "migration-piclaw", "type": 0, "parent_id": "category-1"},
                ]
            if method == "GET" and route == "/channels/control-1/messages?limit=20":
                return []
            if method == "GET" and route == "/channels/piclaw-1/messages?limit=20":
                return [{"id": "101", "content": "!status", "author": {"id": "u1"}}]
            if method == "PUT" and route == "/channels/piclaw-1/messages/101/reactions/%F0%9F%91%80/@me":
                return {}
            if method == "POST" and route == "/channels/piclaw-1/messages":
                assert payload is not None
                replies.append(str(payload.get("content", "")))
                return {"id": "reply-1"}
            raise AssertionError(f"unexpected Discord call {method} {route}")

        def runner(_: CodexControlTask) -> CodexControlRunResult:
            raise AssertionError("status must not invoke Codex")

        results = process_codex_control_commands(
            config,
            DiscordClient("token", transport=transport),
            runner=runner,
            now="2026-04-26T10:00:00Z",
        )

        self.assertEqual(results, [{"channel_id": "piclaw-1", "message_id": "101", "status": "status"}])
        self.assertEqual(len(replies), 1)
        self.assertIn("Codex 频道状态：piclaw", replies[0])
        self.assertIn("worktree 存在：yes", replies[0])

    def test_missing_queue_item_is_reported_without_runner(self) -> None:
        repo_root = self.make_repo_root()
        self.write_queue(repo_root)
        config = self.make_config(repo_root)
        replies: list[str] = []

        def transport(method: str, route: str, payload: dict[str, object] | None = None) -> object:
            if method == "GET" and route == "/guilds/guild-1/channels":
                return [
                    {"id": "control-1", "name": "migration-control", "type": 0, "parent_id": "category-1"},
                    {"id": "demo-1", "name": "migration-demo", "type": 0, "parent_id": "category-1"},
                ]
            if method == "GET" and route == "/channels/control-1/messages?limit=20":
                return []
            if method == "GET" and route == "/channels/demo-1/messages?limit=20":
                return [{"id": "102", "content": "!fix 继续", "author": {"id": "u1"}}]
            if method == "PUT" and route == "/channels/demo-1/messages/102/reactions/%F0%9F%91%80/@me":
                return {}
            if method == "POST" and route == "/channels/demo-1/messages":
                assert payload is not None
                replies.append(str(payload.get("content", "")))
                return {"id": "reply-1"}
            raise AssertionError(f"unexpected Discord call {method} {route}")

        def runner(_: CodexControlTask) -> CodexControlRunResult:
            raise AssertionError("missing queue item must not invoke Codex")

        results = process_codex_control_commands(
            config,
            DiscordClient("token", transport=transport),
            runner=runner,
            now="2026-04-26T10:00:00Z",
        )

        self.assertEqual(results, [{"channel_id": "demo-1", "message_id": "102", "status": "missing_queue_item"}])
        self.assertEqual(len(replies), 1)
        self.assertIn("queue.json 里没有对应项目", replies[0])

    def test_mark_seen_initializes_channel_state_without_running_commands(self) -> None:
        repo_root = self.make_repo_root()
        workspace_path = repo_root / "migration-workspaces" / "migration-piclaw"
        workspace_path.mkdir(parents=True)
        self.write_queue(repo_root, workspace_path=workspace_path)
        config = self.make_config(repo_root)

        def transport(method: str, route: str, payload: dict[str, object] | None = None) -> object:
            if method == "GET" and route == "/guilds/guild-1/channels":
                return [
                    {"id": "control-1", "name": "migration-control", "type": 0, "parent_id": "category-1"},
                    {"id": "piclaw-1", "name": "migration-piclaw", "type": 0, "parent_id": "category-1"},
                ]
            if method == "GET" and route == "/channels/control-1/messages?limit=1":
                return [{"id": "200", "content": "!status", "author": {"id": "u1"}}]
            if method == "GET" and route == "/channels/piclaw-1/messages?limit=1":
                return [{"id": "201", "content": "!fix old", "author": {"id": "u1"}}]
            raise AssertionError(f"unexpected Discord call {method} {route}")

        results = mark_existing_messages_seen(
            config,
            DiscordClient("token", transport=transport),
            now="2026-04-26T10:00:00Z",
        )

        self.assertEqual(
            results,
            [
                {"channel_id": "control-1", "message_id": "200", "status": "marked_seen"},
                {"channel_id": "piclaw-1", "message_id": "201", "status": "marked_seen"},
            ],
        )
        state = json.loads(config.state_path.read_text(encoding="utf-8"))
        self.assertEqual(state["channels"]["control-1"]["last_message_id"], "200")
        self.assertEqual(state["channels"]["piclaw-1"]["last_message_id"], "201")

    def test_unreadable_channel_does_not_block_other_channels(self) -> None:
        repo_root = self.make_repo_root()
        workspace_path = repo_root / "migration-workspaces" / "migration-piclaw"
        workspace_path.mkdir(parents=True)
        self.write_queue(repo_root, workspace_path=workspace_path)
        config = self.make_config(repo_root)
        replies: list[str] = []

        def transport(method: str, route: str, payload: dict[str, object] | None = None) -> object:
            if method == "GET" and route == "/guilds/guild-1/channels":
                return [
                    {"id": "control-1", "name": "migration-control", "type": 0, "parent_id": "category-1"},
                    {"id": "blocked-1", "name": "migration-blocked", "type": 0, "parent_id": "category-1"},
                    {"id": "piclaw-1", "name": "migration-piclaw", "type": 0, "parent_id": "category-1"},
                ]
            if method == "GET" and route == "/channels/control-1/messages?limit=20":
                return []
            if method == "GET" and route == "/channels/blocked-1/messages?limit=20":
                raise RuntimeError("HTTP 403")
            if method == "GET" and route == "/channels/piclaw-1/messages?limit=20":
                return [{"id": "301", "content": "!status", "author": {"id": "u1"}}]
            if method == "PUT" and route == "/channels/piclaw-1/messages/301/reactions/%F0%9F%91%80/@me":
                return {}
            if method == "POST" and route == "/channels/piclaw-1/messages":
                assert payload is not None
                replies.append(str(payload.get("content", "")))
                return {"id": "reply-1"}
            raise AssertionError(f"unexpected Discord call {method} {route}")

        results = process_codex_control_commands(
            config,
            DiscordClient("token", transport=transport),
            now="2026-04-26T10:00:00Z",
        )

        self.assertEqual(results[-1], {"channel_id": "piclaw-1", "message_id": "301", "status": "status"})
        self.assertEqual(len(replies), 1)
        state = json.loads(config.state_path.read_text(encoding="utf-8"))
        self.assertEqual(state["channels"]["blocked-1"]["last_error"], "HTTP 403")

    def test_guild_channel_failure_is_recorded_without_crashing(self) -> None:
        repo_root = self.make_repo_root()
        config = self.make_config(repo_root)

        def transport(method: str, route: str, payload: dict[str, object] | None = None) -> object:
            if method == "GET" and route == "/guilds/guild-1/channels":
                raise RuntimeError("HTTP 522")
            raise AssertionError(f"unexpected Discord call {method} {route}")

        results = process_codex_control_commands(
            config,
            DiscordClient("token", transport=transport),
            now="2026-04-26T10:00:00Z",
        )

        self.assertEqual(results, [{"channel_id": "", "message_id": "", "status": "guild_read_failed"}])
        state = json.loads(config.state_path.read_text(encoding="utf-8"))
        self.assertEqual(state["last_error"], "HTTP 522")

    def test_reply_failure_is_recorded_without_replaying_command(self) -> None:
        repo_root = self.make_repo_root()
        workspace_path = repo_root / "migration-workspaces" / "migration-piclaw"
        workspace_path.mkdir(parents=True)
        self.write_queue(repo_root, workspace_path=workspace_path)
        config = self.make_config(repo_root)

        def transport(method: str, route: str, payload: dict[str, object] | None = None) -> object:
            if method == "GET" and route == "/guilds/guild-1/channels":
                return [
                    {"id": "control-1", "name": "migration-control", "type": 0, "parent_id": "category-1"},
                    {"id": "piclaw-1", "name": "migration-piclaw", "type": 0, "parent_id": "category-1"},
                ]
            if method == "GET" and route == "/channels/control-1/messages?limit=20":
                return []
            if method == "GET" and route == "/channels/piclaw-1/messages?limit=20":
                return [{"id": "401", "content": "!status", "author": {"id": "u1"}}]
            if method == "PUT" and route == "/channels/piclaw-1/messages/401/reactions/%F0%9F%91%80/@me":
                return {}
            if method == "POST" and route == "/channels/piclaw-1/messages":
                raise RuntimeError("send failed")
            raise AssertionError(f"unexpected Discord call {method} {route}")

        results = process_codex_control_commands(
            config,
            DiscordClient("token", transport=transport),
            now="2026-04-26T10:00:00Z",
        )

        self.assertEqual(results[-1]["status"], "status_reply_failed")
        state = json.loads(config.state_path.read_text(encoding="utf-8"))
        self.assertEqual(state["channels"]["piclaw-1"]["last_message_id"], "401")
        self.assertEqual(state["channels"]["piclaw-1"]["last_error"], "send failed")


if __name__ == "__main__":
    unittest.main()
