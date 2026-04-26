from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.discord_codex_control import (
    ChannelContext,
    CodexControlConfig,
    CodexControlRunResult,
    CodexControlTask,
    ParsedCommand,
    build_gateway_identify_payload,
    codex_command_catalog,
    ensure_context_workdir,
    format_codex_result_reply,
    format_codex_progress_message,
    gateway_intents,
    handle_command,
    handle_gateway_interaction_create,
    handle_gateway_message_create,
    mark_existing_messages_seen,
    parse_interaction_command,
    parse_control_message,
    parse_channel_message,
    parse_control_command,
    process_codex_control_commands,
    register_guild_slash_commands,
)
from scripts.discord_migration_notifier import DiscordClient


class DiscordCodexControlTest(unittest.TestCase):
    def make_repo_root(self) -> Path:
        return Path(tempfile.mkdtemp(prefix="discord-codex-control-test-"))

    def init_git_repo(self, repo_root: Path) -> None:
        subprocess.run(["git", "init", "-b", "template", str(repo_root)], check=True, capture_output=True, text=True)
        subprocess.run(["git", "-C", str(repo_root), "config", "user.name", "Test User"], check=True, capture_output=True, text=True)
        subprocess.run(["git", "-C", str(repo_root), "config", "user.email", "test@example.com"], check=True, capture_output=True, text=True)
        (repo_root / "README.md").write_text("test\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo_root), "add", "README.md"], check=True, capture_output=True, text=True)
        subprocess.run(["git", "-C", str(repo_root), "commit", "-m", "init"], check=True, capture_output=True, text=True)

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
        self.assertEqual(parse_control_command("!filter-close").kind, "filter_cleanup")
        self.assertEqual(parse_control_command("<@123> status", bot_user_id="123").kind, "status")
        self.assertEqual(parse_control_command("<@123> 继续处理", bot_user_id="123").instruction, "继续处理")
        self.assertIsNone(parse_control_command("<@123> 继续处理"))
        self.assertIsNone(parse_control_command("<@999> 继续处理", bot_user_id="123"))
        self.assertIsNone(parse_control_command("随便聊一句"))

    def test_parse_slash_interaction_commands(self) -> None:
        self.assertEqual(
            parse_interaction_command({"type": 2, "data": {"name": "status"}}),
            parse_control_command("!status"),
        )
        self.assertEqual(
            parse_interaction_command({"type": 2, "data": {"name": "codex", "options": [{"name": "task", "value": "继续处理"}]}}),
            parse_control_command("!codex 继续处理"),
        )
        self.assertEqual(
            parse_interaction_command({"type": 2, "data": {"name": "filter-close"}}).kind,
            "filter_cleanup",
        )
        self.assertIsNone(parse_interaction_command({"type": 3, "data": {"name": "status"}}))

    def test_register_guild_slash_commands_uses_catalog(self) -> None:
        repo_root = self.make_repo_root()
        config = self.make_config(repo_root)
        events: list[tuple[str, str, object | None]] = []

        def transport(method: str, route: str, payload: dict[str, object] | None = None) -> object:
            events.append((method, route, payload))
            if method == "PUT" and route == "/applications/app-1/guilds/guild-1/commands":
                assert payload == codex_command_catalog()
                return [{"id": "cmd-1", "name": "status"}]
            raise AssertionError(f"unexpected Discord call {method} {route}")

        result = register_guild_slash_commands(config, DiscordClient("token", transport=transport), application_id="app-1")

        self.assertEqual(result, [{"id": "cmd-1", "name": "status"}])
        self.assertEqual(events, [("PUT", "/applications/app-1/guilds/guild-1/commands", codex_command_catalog())])

    def test_parse_empty_role_mention_as_content_unavailable(self) -> None:
        repo_root = self.make_repo_root()
        config = self.make_config(repo_root)
        message = {"content": "", "mention_roles": ["role-1"], "author": {"id": "u1"}}

        parsed = parse_control_message(message, config)

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.kind, "content_unavailable")

    def test_dashboard_channel_treats_plain_text_as_codex_instruction(self) -> None:
        repo_root = self.make_repo_root()
        config = self.make_config(repo_root)
        context = ChannelContext(
            channel_id="dashboard-1",
            channel_name="dashboard",
            scope="dashboard",
            slug="dashboard",
            workdir=repo_root,
            implicit_codex=True,
        )

        parsed = parse_channel_message({"content": "继续处理等待人工决策的项目", "author": {"id": "u1"}}, config, context)

        self.assertEqual(parsed, ParsedCommand("codex", "继续处理等待人工决策的项目"))

    def test_migration_channel_treats_plain_text_as_codex_instruction(self) -> None:
        repo_root = self.make_repo_root()
        config = self.make_config(repo_root)
        context = ChannelContext(
            channel_id="piclaw-1",
            channel_name="migration-piclaw",
            scope="migration",
            slug="piclaw",
            workdir=repo_root,
            implicit_codex=True,
        )

        parsed = parse_channel_message({"content": "选择官方作者信息，继续上架", "author": {"id": "u1"}}, config, context)

        self.assertEqual(parsed, ParsedCommand("codex", "选择官方作者信息，继续上架"))

    def test_gateway_identify_payload_requests_message_events_and_content(self) -> None:
        payload = build_gateway_identify_payload("token-1")

        self.assertEqual(payload["op"], 2)
        self.assertEqual(payload["d"]["token"], "token-1")
        self.assertTrue(gateway_intents() & (1 << 0))  # GUILDS
        self.assertTrue(gateway_intents() & (1 << 9))  # GUILD_MESSAGES
        self.assertTrue(gateway_intents() & (1 << 15))  # MESSAGE_CONTENT

    def test_gateway_message_create_dispatches_command_without_message_polling(self) -> None:
        repo_root = self.make_repo_root()
        self.write_queue(repo_root)
        config = self.make_config(repo_root)
        context = ChannelContext(
            channel_id="dashboard-1",
            channel_name="dashboard",
            scope="dashboard",
            slug="dashboard",
            workdir=repo_root,
            implicit_codex=True,
        )
        events: list[tuple[str, str, dict[str, object] | None]] = []
        replies: list[str] = []

        def transport(method: str, route: str, payload: dict[str, object] | None = None) -> object:
            events.append((method, route, payload))
            if method == "PUT" and route == "/channels/dashboard-1/messages/900/reactions/%E2%9C%85/@me":
                return {}
            if method == "POST" and route == "/channels/dashboard-1/messages":
                assert payload is not None
                replies.append(str(payload.get("content", "")))
                return {"id": "reply-1"}
            raise AssertionError(f"unexpected Discord call {method} {route}")

        def runner(_: CodexControlTask) -> CodexControlRunResult:
            raise AssertionError("status must not invoke Codex")

        result = handle_gateway_message_create(
            config,
            DiscordClient("token", transport=transport),
            {"dashboard-1": context},
            {"id": "900", "channel_id": "dashboard-1", "content": "!status", "author": {"id": "u1"}},
            runner=runner,
            now="2026-04-26T10:00:00Z",
        )

        self.assertEqual(result, {"channel_id": "dashboard-1", "message_id": "900", "status": "status"})
        self.assertEqual(len(replies), 1)
        self.assertIn("Codex Dashboard 状态", replies[0])
        self.assertFalse(any("/messages?limit" in event[1] for event in events))

    def test_gateway_message_create_runs_plain_text_from_dashboard_channel(self) -> None:
        repo_root = self.make_repo_root()
        config = self.make_config(repo_root)
        context = ChannelContext(
            channel_id="dashboard-1",
            channel_name="dashboard",
            scope="dashboard",
            slug="dashboard",
            workdir=repo_root,
            implicit_codex=True,
        )
        tasks: list[CodexControlTask] = []
        replies: list[str] = []

        def transport(method: str, route: str, payload: dict[str, object] | None = None) -> object:
            if method == "PUT" and route == "/channels/dashboard-1/messages/902/reactions/%E2%9C%85/@me":
                return {}
            if method == "PUT" and route == "/channels/dashboard-1/messages/902/reactions/%F0%9F%9A%80/@me":
                return {}
            if method == "POST" and route == "/channels/dashboard-1/messages":
                assert payload is not None
                replies.append(str(payload.get("content", "")))
                return {"id": "reply-1"}
            raise AssertionError(f"unexpected Discord call {method} {route}")

        def runner(task: CodexControlTask) -> CodexControlRunResult:
            tasks.append(task)
            return CodexControlRunResult("completed", 0, "已处理。", task.task_dir)

        result = handle_gateway_message_create(
            config,
            DiscordClient("token", transport=transport),
            {"dashboard-1": context},
            {"id": "902", "channel_id": "dashboard-1", "content": "继续处理等待人工决策的项目", "author": {"id": "u1"}},
            runner=runner,
            now="2026-04-26T10:00:00Z",
        )

        self.assertEqual(result, {"channel_id": "dashboard-1", "message_id": "902", "status": "completed"})
        self.assertEqual(len(tasks), 1)
        self.assertIn("继续处理等待人工决策的项目", tasks[0].prompt)
        self.assertEqual(len(replies), 2)
        self.assertIn("Codex worker 已启动", replies[0])
        self.assertIn("Codex 任务完成", replies[-1])

    def test_gateway_message_create_runs_codex_command_from_migration_channel(self) -> None:
        repo_root = self.make_repo_root()
        workspace_path = repo_root.parent / f"{repo_root.name}-migration-workspaces" / "migration-piclaw"
        workspace_path.mkdir(parents=True)
        self.write_queue(repo_root, workspace_path=workspace_path)
        config = self.make_config(repo_root)
        item = json.loads((repo_root / "registry" / "auto-migration" / "queue.json").read_text())["items"][0]
        context = ChannelContext(
            channel_id="piclaw-1",
            channel_name="migration-piclaw",
            scope="migration",
            slug="piclaw",
            item=item,
            workdir=workspace_path,
        )
        tasks: list[CodexControlTask] = []
        replies: list[str] = []

        def transport(method: str, route: str, payload: dict[str, object] | None = None) -> object:
            if method == "PUT" and route == "/channels/piclaw-1/messages/901/reactions/%E2%9C%85/@me":
                return {}
            if method == "PUT" and route == "/channels/piclaw-1/messages/901/reactions/%F0%9F%9A%80/@me":
                return {}
            if method == "POST" and route == "/channels/piclaw-1/messages":
                assert payload is not None
                replies.append(str(payload.get("content", "")))
                return {"id": "reply-1"}
            raise AssertionError(f"unexpected Discord call {method} {route}")

        def runner(task: CodexControlTask) -> CodexControlRunResult:
            tasks.append(task)
            time.sleep(0.03)
            return CodexControlRunResult("completed", 0, "已处理。", task.task_dir)

        result = handle_gateway_message_create(
            config,
            DiscordClient("token", transport=transport),
            {"piclaw-1": context},
            {"id": "901", "channel_id": "piclaw-1", "content": "!fix 继续修复", "author": {"id": "u1"}},
            runner=runner,
            now="2026-04-26T10:00:00Z",
            progress_interval_seconds=0.01,
        )

        self.assertEqual(result, {"channel_id": "piclaw-1", "message_id": "901", "status": "completed"})
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].context.workdir, workspace_path)
        self.assertIn("继续修复", tasks[0].prompt)
        self.assertEqual(len(replies), 2)
        self.assertIn("Codex worker 已启动", replies[0])
        self.assertIn("Codex 任务完成", replies[-1])
        self.assertFalse(any("收到" in reply for reply in replies))

    def test_gateway_message_create_runs_plain_text_from_migration_channel(self) -> None:
        repo_root = self.make_repo_root()
        workspace_path = repo_root.parent / f"{repo_root.name}-migration-workspaces" / "migration-piclaw"
        workspace_path.mkdir(parents=True)
        self.write_queue(repo_root, workspace_path=workspace_path)
        config = self.make_config(repo_root)
        item = json.loads((repo_root / "registry" / "auto-migration" / "queue.json").read_text())["items"][0]
        context = ChannelContext(
            channel_id="piclaw-1",
            channel_name="migration-piclaw",
            scope="migration",
            slug="piclaw",
            item=item,
            workdir=workspace_path,
            implicit_codex=True,
        )
        tasks: list[CodexControlTask] = []
        replies: list[str] = []

        def transport(method: str, route: str, payload: dict[str, object] | None = None) -> object:
            if method == "PUT" and route == "/channels/piclaw-1/messages/903/reactions/%E2%9C%85/@me":
                return {}
            if method == "PUT" and route == "/channels/piclaw-1/messages/903/reactions/%F0%9F%9A%80/@me":
                return {}
            if method == "POST" and route == "/channels/piclaw-1/messages":
                assert payload is not None
                replies.append(str(payload.get("content", "")))
                return {"id": "reply-1"}
            raise AssertionError(f"unexpected Discord call {method} {route}")

        def runner(task: CodexControlTask) -> CodexControlRunResult:
            tasks.append(task)
            return CodexControlRunResult("completed", 0, "已处理。", task.task_dir)

        result = handle_gateway_message_create(
            config,
            DiscordClient("token", transport=transport),
            {"piclaw-1": context},
            {"id": "903", "channel_id": "piclaw-1", "content": "继续修复截图流程", "author": {"id": "u1"}},
            runner=runner,
            now="2026-04-26T10:00:00Z",
        )

        self.assertEqual(result, {"channel_id": "piclaw-1", "message_id": "903", "status": "completed"})
        self.assertEqual(len(tasks), 1)
        self.assertIn("继续修复截图流程", tasks[0].prompt)
        self.assertEqual(len(replies), 2)
        self.assertIn("Codex worker 已启动", replies[0])
        self.assertIn("Codex 任务完成", replies[-1])

    def test_migration_operator_decision_records_human_response_without_runner(self) -> None:
        repo_root = self.make_repo_root()
        queue_path = repo_root / "registry" / "auto-migration" / "queue.json"
        queue_path.parent.mkdir(parents=True, exist_ok=True)
        queue_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "items": [
                        {
                            "id": "item-1",
                            "slug": "piclaw",
                            "state": "waiting_for_human",
                            "human_request": {"options": ["choose_official_author"]},
                        }
                    ],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        config = self.make_config(repo_root)
        context = ChannelContext(
            channel_id="piclaw-1",
            channel_name="migration-piclaw",
            scope="migration",
            slug="piclaw",
            item=json.loads(queue_path.read_text(encoding="utf-8"))["items"][0],
            workdir=repo_root,
            implicit_codex=True,
        )

        result = handle_command(
            ParsedCommand("codex", "choose_official_author"),
            context,
            config,
            now="2026-04-26T16:30:00Z",
        )

        self.assertEqual(result.status, "human_decision_recorded")
        item = json.loads(queue_path.read_text(encoding="utf-8"))["items"][0]
        self.assertEqual(item["human_response"]["content"], "choose_official_author")
        self.assertEqual(item["human_response"]["source"], "migration_operator")
        self.assertEqual(item["human_response"]["channel_id"], "piclaw-1")

    def test_running_progress_message_only_reports_summary_delta(self) -> None:
        repo_root = self.make_repo_root()
        task = CodexControlTask(
            instruction="继续处理 piclaw 的迁移失败并验证",
            context=ChannelContext(
                channel_id="piclaw-1",
                channel_name="migration-piclaw",
                scope="migration",
                slug="piclaw",
                workdir=repo_root,
            ),
            config=self.make_config(repo_root),
            task_dir=repo_root / "registry" / "auto-migration" / "codex-control-tasks" / "demo",
            prompt="",
            command=[],
            now="2026-04-26T10:00:00Z",
        )

        started = format_codex_progress_message(task, "started", 0.0, "读取失败日志并定位截图流程")
        running = format_codex_progress_message(task, "running", 65.0, "已定位到截图脚本参数不兼容，正在改修复")

        self.assertIn("频道：#migration-piclaw", started)
        self.assertIn("任务目录", started)
        self.assertIn("当前工作：读取失败日志并定位截图流程", started)
        self.assertIn("Codex worker 进展 1m05s", running)
        self.assertIn("当前工作：已定位到截图脚本参数不兼容，正在改修复", running)
        self.assertNotIn("频道：#migration-piclaw", running)
        self.assertNotIn("任务目录", running)

    def test_result_reply_includes_current_branch_and_commit(self) -> None:
        repo_root = self.make_repo_root()
        self.init_git_repo(repo_root)
        subprocess.run(
            ["git", "-C", str(repo_root), "checkout", "-b", "migration/piclaw"],
            check=True,
            capture_output=True,
            text=True,
        )
        head = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--short", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        context = ChannelContext(
            channel_id="piclaw-1",
            channel_name="migration-piclaw",
            scope="migration",
            slug="piclaw",
            workdir=repo_root,
        )

        reply = format_codex_result_reply(CodexControlRunResult("completed", 0, "已处理。", repo_root / "task"), context)

        self.assertIn("- 分支：migration/piclaw", reply)
        self.assertIn(head, reply)

    def test_gateway_interaction_create_runs_codex_command_from_migration_channel(self) -> None:
        repo_root = self.make_repo_root()
        workspace_path = repo_root.parent / f"{repo_root.name}-migration-workspaces" / "migration-piclaw"
        workspace_path.mkdir(parents=True)
        self.write_queue(repo_root, workspace_path=workspace_path)
        config = self.make_config(repo_root)
        item = json.loads((repo_root / "registry" / "auto-migration" / "queue.json").read_text())["items"][0]
        context = ChannelContext(
            channel_id="piclaw-1",
            channel_name="migration-piclaw",
            scope="migration",
            slug="piclaw",
            item=item,
            workdir=workspace_path,
        )
        tasks: list[CodexControlTask] = []
        events: list[tuple[str, str, dict[str, object] | None]] = []

        def transport(method: str, route: str, payload: dict[str, object] | None = None) -> object:
            events.append((method, route, payload))
            if method == "POST" and route == "/interactions/901/token-901/callback":
                return {}
            if method == "POST" and route == "/webhooks/app-1/token-901":
                return {"id": "followup-1"}
            raise AssertionError(f"unexpected Discord call {method} {route}")

        def runner(task: CodexControlTask) -> CodexControlRunResult:
            tasks.append(task)
            return CodexControlRunResult("completed", 0, "已处理。", task.task_dir)

        result = handle_gateway_interaction_create(
            config,
            DiscordClient("token", transport=transport),
            {"piclaw-1": context},
            {
                "id": "901",
                "application_id": "app-1",
                "channel_id": "piclaw-1",
                "token": "token-901",
                "type": 2,
                "data": {"name": "fix", "options": [{"name": "issue", "value": "继续修复"}]},
            },
            runner=runner,
            now="2026-04-26T10:00:00Z",
        )

        self.assertEqual(result, {"channel_id": "piclaw-1", "message_id": "901", "status": "completed"})
        self.assertEqual(len(tasks), 1)
        self.assertIn("继续修复", tasks[0].prompt)
        self.assertEqual(
            events[0],
            (
                "POST",
                "/interactions/901/token-901/callback",
                {"type": 5},
            ),
        )
        self.assertEqual(events[1][0:2], ("POST", "/webhooks/app-1/token-901"))

    def test_gateway_interaction_create_replies_immediately_for_status(self) -> None:
        repo_root = self.make_repo_root()
        self.write_queue(repo_root)
        context = ChannelContext(
            channel_id="dashboard-1",
            channel_name="dashboard",
            scope="dashboard",
            slug="dashboard",
            workdir=repo_root,
        )
        replies: list[str] = []

        def transport(method: str, route: str, payload: dict[str, object] | None = None) -> object:
            if method == "POST" and route == "/interactions/900/token-900/callback":
                assert payload is not None
                replies.append(str((payload.get("data") or {}).get("content", "")))
                return {}
            raise AssertionError(f"unexpected Discord call {method} {route}")

        def runner(_: CodexControlTask) -> CodexControlRunResult:
            raise AssertionError("status must not invoke Codex")

        result = handle_gateway_interaction_create(
            self.make_config(repo_root),
            DiscordClient("token", transport=transport),
            {"dashboard-1": context},
            {
                "id": "900",
                "application_id": "app-1",
                "channel_id": "dashboard-1",
                "token": "token-900",
                "type": 2,
                "data": {"name": "status"},
            },
            runner=runner,
            now="2026-04-26T10:00:00Z",
        )

        self.assertEqual(result, {"channel_id": "dashboard-1", "message_id": "900", "status": "status"})
        self.assertEqual(len(replies), 1)
        self.assertIn("Codex Dashboard 状态", replies[0])

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
            if method == "PUT" and route == "/channels/piclaw-1/messages/100/reactions/%E2%9C%85/@me":
                return {}
            if method == "PUT" and route == "/channels/piclaw-1/messages/100/reactions/%F0%9F%9A%80/@me":
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
            events.index(("PUT", "/channels/piclaw-1/messages/100/reactions/%E2%9C%85/@me", None)),
            next(index for index, event in enumerate(events) if event[0:2] == ("POST", "/channels/piclaw-1/messages")),
        )
        self.assertLess(
            events.index(("PUT", "/channels/piclaw-1/messages/100/reactions/%F0%9F%9A%80/@me", None)),
            events.index(("RUNNER", "codex", None)),
        )
        progress_posts = [
            event
            for event in events
            if event[0:2] == ("POST", "/channels/piclaw-1/messages") and event[2] and "Codex worker 已启动" in str(event[2].get("content", ""))
        ]
        self.assertEqual(len(progress_posts), 1)
        self.assertEqual(sum(1 for event in events if event[0:2] == ("POST", "/channels/piclaw-1/messages")), 2)
        state = json.loads(config.state_path.read_text(encoding="utf-8"))
        self.assertEqual(state["channels"]["piclaw-1"]["last_message_id"], "100")

    def test_process_migration_channel_falls_back_when_workspace_path_is_stale(self) -> None:
        repo_root = self.make_repo_root()
        self.init_git_repo(repo_root)
        stale_workspace_path = repo_root / "migration-workspaces" / "migration-piclaw"
        self.write_queue(repo_root, workspace_path=stale_workspace_path)
        config = self.make_config(repo_root)
        tasks: list[CodexControlTask] = []

        def transport(method: str, route: str, payload: dict[str, object] | None = None) -> object:
            if method == "GET" and route == "/guilds/guild-1/channels":
                return [
                    {"id": "control-1", "name": "migration-control", "type": 0, "parent_id": "category-1"},
                    {"id": "piclaw-1", "name": "migration-piclaw", "type": 0, "parent_id": "category-1"},
                ]
            if method == "GET" and route == "/channels/control-1/messages?limit=20":
                return []
            if method == "GET" and route == "/channels/piclaw-1/messages?limit=20":
                return [{"id": "100", "content": "!fix 继续处理", "author": {"id": "u1"}}]
            if method == "PUT" and route == "/channels/piclaw-1/messages/100/reactions/%E2%9C%85/@me":
                return {}
            if method == "PUT" and route == "/channels/piclaw-1/messages/100/reactions/%F0%9F%9A%80/@me":
                return {}
            if method == "POST" and route == "/channels/piclaw-1/messages":
                return {"id": "reply-1"}
            raise AssertionError(f"unexpected Discord call {method} {route}")

        def runner(task: CodexControlTask) -> CodexControlRunResult:
            tasks.append(task)
            return CodexControlRunResult("completed", 0, "已处理。", task.task_dir)

        results = process_codex_control_commands(
            config,
            DiscordClient("token", transport=transport),
            runner=runner,
            now="2026-04-26T10:00:00Z",
        )

        self.assertEqual(results, [{"channel_id": "piclaw-1", "message_id": "100", "status": "completed"}])
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].context.workdir, stale_workspace_path)
        self.assertTrue(stale_workspace_path.exists())
        self.assertIn(str(stale_workspace_path), tasks[0].command)
        self.assertNotIn(str(repo_root), tasks[0].command)
        branch = subprocess.run(
            ["git", "-C", str(repo_root), "branch", "--list", "migration/piclaw"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        self.assertIn("migration/piclaw", branch)

    def test_ensure_context_workdir_reuses_existing_branch_when_workspace_is_missing(self) -> None:
        repo_root = self.make_repo_root()
        self.init_git_repo(repo_root)
        subprocess.run(
            ["git", "-C", str(repo_root), "checkout", "-b", "migration/piclaw"],
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["git", "-C", str(repo_root), "checkout", "template"],
            check=True,
            capture_output=True,
            text=True,
        )
        workspace_path = repo_root / "migration-workspaces" / "migration-piclaw"
        queue_path = self.write_queue(repo_root, workspace_path=workspace_path)
        payload = json.loads(queue_path.read_text(encoding="utf-8"))
        payload["items"][0]["branch"] = "migration/piclaw"
        queue_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
        item = payload["items"][0]
        config = self.make_config(repo_root)
        context = ChannelContext(
            channel_id="piclaw-1",
            channel_name="migration-piclaw",
            scope="migration",
            slug="piclaw",
            item=item,
            workdir=repo_root,
        )

        ensured = ensure_context_workdir(context, config)

        self.assertEqual(ensured.workdir, workspace_path)
        self.assertTrue(workspace_path.exists())
        self.assertEqual(
            subprocess.run(
                ["git", "-C", str(workspace_path), "branch", "--show-current"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip(),
            "migration/piclaw",
        )

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
            if method == "PUT" and route == "/channels/piclaw-1/messages/101/reactions/%E2%9C%85/@me":
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

    def test_dashboard_channel_accepts_status_command(self) -> None:
        repo_root = self.make_repo_root()
        self.write_queue(repo_root)
        dashboard_root = repo_root / "registry" / "dashboard"
        dashboard_root.mkdir(parents=True)
        (dashboard_root / "latest.json").write_text(
            json.dumps(
                {
                    "generated_at": "2026-04-26T10:00:00Z",
                    "queue": {"total": 3, "state_counts": {"ready": 2, "waiting_for_human": 1}},
                    "local_agent": {"total": 7, "status_counts": {"portable": 4}},
                    "publication": {"total": 2, "status_counts": {"published": 2}},
                    "waiting_for_human": [{"slug": "piclaw"}],
                    "failed_items": [],
                    "top_candidates": [{"full_name": "owner/app"}],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        config = self.make_config(repo_root)
        replies: list[str] = []

        def transport(method: str, route: str, payload: dict[str, object] | None = None) -> object:
            if method == "GET" and route == "/guilds/guild-1/channels":
                return [
                    {"id": "control-1", "name": "migration-control", "type": 0, "parent_id": "category-1"},
                    {"id": "dashboard-1", "name": "dashboard", "type": 0, "parent_id": "category-1"},
                ]
            if method == "GET" and route == "/channels/control-1/messages?limit=20":
                return []
            if method == "GET" and route == "/channels/dashboard-1/messages?limit=20":
                return [{"id": "150", "content": "!status", "author": {"id": "u1"}}]
            if method == "PUT" and route == "/channels/dashboard-1/messages/150/reactions/%E2%9C%85/@me":
                return {}
            if method == "POST" and route == "/channels/dashboard-1/messages":
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

        self.assertEqual(results, [{"channel_id": "dashboard-1", "message_id": "150", "status": "status"}])
        self.assertEqual(len(replies), 1)
        self.assertIn("Codex Dashboard 状态", replies[0])
        self.assertIn("等待回复：1", replies[0])
        self.assertIn("今日优先候选：1", replies[0])

    def test_dashboard_channel_runs_codex_with_dashboard_context(self) -> None:
        repo_root = self.make_repo_root()
        self.write_queue(repo_root)
        dashboard_root = repo_root / "registry" / "dashboard"
        dashboard_root.mkdir(parents=True)
        (dashboard_root / "latest.md").write_text("# LazyCat 自动移植日报\n\n## 失败待处理\n- piclaw\n", encoding="utf-8")
        config = self.make_config(repo_root)
        tasks: list[CodexControlTask] = []

        def transport(method: str, route: str, payload: dict[str, object] | None = None) -> object:
            if method == "GET" and route == "/guilds/guild-1/channels":
                return [
                    {"id": "control-1", "name": "migration-control", "type": 0, "parent_id": "category-1"},
                    {"id": "dashboard-1", "name": "dashboard", "type": 0, "parent_id": "category-1"},
                ]
            if method == "GET" and route == "/channels/control-1/messages?limit=20":
                return []
            if method == "GET" and route == "/channels/dashboard-1/messages?limit=20":
                return [{"id": "151", "content": "!codex 总结今天失败原因", "author": {"id": "u1"}}]
            if method == "PUT" and route == "/channels/dashboard-1/messages/151/reactions/%E2%9C%85/@me":
                return {}
            if method == "PUT" and route == "/channels/dashboard-1/messages/151/reactions/%F0%9F%9A%80/@me":
                return {}
            if method == "POST" and route == "/channels/dashboard-1/messages":
                return {"id": "reply-1"}
            raise AssertionError(f"unexpected Discord call {method} {route}")

        def runner(task: CodexControlTask) -> CodexControlRunResult:
            tasks.append(task)
            return CodexControlRunResult("completed", 0, "已总结。", task.task_dir)

        results = process_codex_control_commands(
            config,
            DiscordClient("token", transport=transport),
            runner=runner,
            now="2026-04-26T10:00:00Z",
        )

        self.assertEqual(results, [{"channel_id": "dashboard-1", "message_id": "151", "status": "completed"}])
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].context.scope, "dashboard")
        self.assertEqual(tasks[0].context.workdir, repo_root)
        self.assertIn("Latest dashboard summary", tasks[0].prompt)
        self.assertIn("piclaw", tasks[0].prompt)

    def test_dashboard_channel_reuses_persistent_codex_session(self) -> None:
        repo_root = self.make_repo_root()
        self.write_queue(repo_root)
        dashboard_root = repo_root / "registry" / "dashboard"
        dashboard_root.mkdir(parents=True)
        config = self.make_config(repo_root)
        config.state_path.parent.mkdir(parents=True, exist_ok=True)
        config.state_path.write_text(
            json.dumps(
                {
                    "channels": {
                        "dashboard-1": {
                            "channel_name": "dashboard",
                            "slug": "dashboard",
                            "codex": {
                                "session_id": "11111111-2222-3333-4444-555555555555",
                                "updated_at": "2026-04-26T09:00:00Z",
                                "mode": "persistent_dashboard",
                            },
                        }
                    }
                }
            )
            + "\n",
            encoding="utf-8",
        )
        tasks: list[CodexControlTask] = []

        def transport(method: str, route: str, payload: dict[str, object] | None = None) -> object:
            if method == "GET" and route == "/guilds/guild-1/channels":
                return [
                    {"id": "control-1", "name": "migration-control", "type": 0, "parent_id": "category-1"},
                    {"id": "dashboard-1", "name": "dashboard", "type": 0, "parent_id": "category-1"},
                ]
            if method == "GET" and route == "/channels/control-1/messages?limit=20":
                return []
            if method == "GET" and route == "/channels/dashboard-1/messages?limit=20":
                return [{"id": "152", "content": "!codex 继续", "author": {"id": "u1"}}]
            if method == "PUT" and route == "/channels/dashboard-1/messages/152/reactions/%E2%9C%85/@me":
                return {}
            if method == "PUT" and route == "/channels/dashboard-1/messages/152/reactions/%F0%9F%9A%80/@me":
                return {}
            if method == "POST" and route == "/channels/dashboard-1/messages":
                return {"id": "reply-1"}
            raise AssertionError(f"unexpected Discord call {method} {route}")

        def runner(task: CodexControlTask) -> CodexControlRunResult:
            tasks.append(task)
            return CodexControlRunResult(
                "completed",
                0,
                "继续完成。",
                task.task_dir,
                session_id="66666666-7777-8888-9999-aaaaaaaaaaaa",
            )

        results = process_codex_control_commands(
            config,
            DiscordClient("token", transport=transport),
            runner=runner,
            now="2026-04-26T10:00:00Z",
        )

        self.assertEqual(results, [{"channel_id": "dashboard-1", "message_id": "152", "status": "completed"}])
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].session_id, "11111111-2222-3333-4444-555555555555")
        self.assertIn("resume", tasks[0].command)
        state = json.loads(config.state_path.read_text(encoding="utf-8"))
        self.assertEqual(
            state["channels"]["dashboard-1"]["codex"]["session_id"],
            "66666666-7777-8888-9999-aaaaaaaaaaaa",
        )

    def test_migration_channel_does_not_reuse_dashboard_style_session(self) -> None:
        repo_root = self.make_repo_root()
        workspace_path = repo_root / "migration-workspaces" / "migration-piclaw"
        workspace_path.mkdir(parents=True)
        self.write_queue(repo_root, workspace_path=workspace_path)
        config = self.make_config(repo_root)
        config.state_path.parent.mkdir(parents=True, exist_ok=True)
        config.state_path.write_text(
            json.dumps(
                {
                    "channels": {
                        "piclaw-1": {
                            "channel_name": "migration-piclaw",
                            "slug": "piclaw",
                            "codex": {"session_id": "11111111-2222-3333-4444-555555555555"},
                        }
                    }
                }
            )
            + "\n",
            encoding="utf-8",
        )
        tasks: list[CodexControlTask] = []

        def transport(method: str, route: str, payload: dict[str, object] | None = None) -> object:
            if method == "GET" and route == "/guilds/guild-1/channels":
                return [
                    {"id": "control-1", "name": "migration-control", "type": 0, "parent_id": "category-1"},
                    {"id": "piclaw-1", "name": "migration-piclaw", "type": 0, "parent_id": "category-1"},
                ]
            if method == "GET" and route == "/channels/control-1/messages?limit=20":
                return []
            if method == "GET" and route == "/channels/piclaw-1/messages?limit=20":
                return [{"id": "153", "content": "!codex 继续修复", "author": {"id": "u1"}}]
            if method == "PUT" and route == "/channels/piclaw-1/messages/153/reactions/%E2%9C%85/@me":
                return {}
            if method == "PUT" and route == "/channels/piclaw-1/messages/153/reactions/%F0%9F%9A%80/@me":
                return {}
            if method == "POST" and route == "/channels/piclaw-1/messages":
                return {"id": "reply-1"}
            raise AssertionError(f"unexpected Discord call {method} {route}")

        def runner(task: CodexControlTask) -> CodexControlRunResult:
            tasks.append(task)
            return CodexControlRunResult("completed", 0, "修复完成。", task.task_dir)

        results = process_codex_control_commands(
            config,
            DiscordClient("token", transport=transport),
            runner=runner,
            now="2026-04-26T10:00:00Z",
        )

        self.assertEqual(results, [{"channel_id": "piclaw-1", "message_id": "153", "status": "completed"}])
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].session_id, "")
        self.assertNotIn("resume", tasks[0].command)
        state = json.loads(config.state_path.read_text(encoding="utf-8"))
        self.assertEqual(state["channels"]["piclaw-1"]["last_message_id"], "153")
        self.assertEqual(state["channels"]["piclaw-1"]["codex"]["session_id"], "11111111-2222-3333-4444-555555555555")

    def test_dashboard_operator_decision_records_human_response_without_runner(self) -> None:
        repo_root = self.make_repo_root()
        queue_path = repo_root / "registry" / "auto-migration" / "queue.json"
        queue_path.parent.mkdir(parents=True)
        queue_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "items": [
                        {
                            "id": "github:glomatico/gamdl",
                            "source": "glomatico/gamdl",
                            "slug": "gamdl",
                            "state": "waiting_for_human",
                            "human_request": {
                                "kind": "migration_decision",
                                "question": "skip or wrap?",
                                "options": ["skip_candidate", "build_custom_wrapper"],
                                "created_at": "2026-04-26T16:25:00Z",
                            },
                        }
                    ],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        config = self.make_config(repo_root)
        context = ChannelContext(
            channel_id="dashboard-1",
            channel_name="dashboard",
            scope="dashboard",
            slug="dashboard",
            workdir=repo_root,
        )

        def runner(_: CodexControlTask) -> CodexControlRunResult:
            raise AssertionError("dashboard decision should not invoke Codex")

        result = handle_command(
            ParsedCommand("codex", "build_custom_wrapper"),
            context,
            config,
            runner=runner,
            now="2026-04-26T16:30:00Z",
        )

        self.assertEqual(result.status, "human_decision_recorded")
        payload = json.loads(queue_path.read_text(encoding="utf-8"))
        item = payload["items"][0]
        self.assertEqual(item["human_response"]["content"], "build_custom_wrapper")
        self.assertEqual(item["human_response"]["source"], "dashboard_operator")
        self.assertEqual(item["human_response"]["channel_id"], "dashboard-1")

    def test_dashboard_operator_decision_reports_ambiguity(self) -> None:
        repo_root = self.make_repo_root()
        queue_path = repo_root / "registry" / "auto-migration" / "queue.json"
        queue_path.parent.mkdir(parents=True)
        queue_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "items": [
                        {
                            "id": "github:owner/one",
                            "source": "owner/one",
                            "slug": "one",
                            "state": "waiting_for_human",
                            "human_request": {"options": ["build_custom_wrapper"]},
                        },
                        {
                            "id": "github:owner/two",
                            "source": "owner/two",
                            "slug": "two",
                            "state": "waiting_for_human",
                            "human_request": {"options": ["build_custom_wrapper"]},
                        },
                    ],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        config = self.make_config(repo_root)
        context = ChannelContext(
            channel_id="dashboard-1",
            channel_name="dashboard",
            scope="dashboard",
            slug="dashboard",
            workdir=repo_root,
        )

        result = handle_command(
            ParsedCommand("codex", "build_custom_wrapper"),
            context,
            config,
            now="2026-04-26T16:30:00Z",
        )

        self.assertEqual(result.status, "human_decision_ambiguous")
        self.assertIn("one", result.reply)
        self.assertIn("two", result.reply)

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
            if method == "PUT" and route == "/channels/demo-1/messages/102/reactions/%E2%9C%85/@me":
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
            if method == "PUT" and route == "/channels/piclaw-1/messages/301/reactions/%E2%9C%85/@me":
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
            if method == "PUT" and route == "/channels/piclaw-1/messages/401/reactions/%E2%9C%85/@me":
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

    def test_filter_close_cleans_queue_state_and_deletes_channel(self) -> None:
        repo_root = self.make_repo_root()
        self.init_git_repo(repo_root)
        workspace_path = repo_root / "migration-workspaces" / "migration-piclaw"
        workspace_path.parent.mkdir(parents=True, exist_ok=True)
        self.write_queue(repo_root, workspace_path=workspace_path)
        subprocess.run(
            ["git", "-C", str(repo_root), "worktree", "add", "-b", "migration/piclaw", str(workspace_path), "template"],
            check=True,
            capture_output=True,
            text=True,
        )
        notifications_dir = repo_root / "registry" / "auto-migration" / "notifications"
        notifications_dir.mkdir(parents=True, exist_ok=True)
        (notifications_dir / "20260426T000000Z-github-owner-piclaw.md").write_text("note\n", encoding="utf-8")
        config = self.make_config(repo_root, workspace_root=workspace_path.parent)
        state_path = config.state_path
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(
            json.dumps({"channels": {"piclaw-1": {"last_message_id": "old", "slug": "piclaw"}}}) + "\n",
            encoding="utf-8",
        )
        replies: list[str] = []
        deleted_channels: list[str] = []

        def transport(method: str, route: str, payload: dict[str, object] | None = None) -> object:
            if method == "GET" and route == "/guilds/guild-1/channels":
                return [
                    {"id": "control-1", "name": "migration-control", "type": 0, "parent_id": "category-1"},
                    {"id": "piclaw-1", "name": "migration-piclaw", "type": 0, "parent_id": "category-1"},
                ]
            if method == "GET" and route == "/channels/control-1/messages?limit=20":
                return []
            if method == "GET" and route in {"/channels/piclaw-1/messages?limit=20", "/channels/piclaw-1/messages?after=old&limit=20", "/channels/piclaw-1/messages?limit=20&after=old"}:
                return [{"id": "501", "content": "!filter-close", "author": {"id": "u1"}}]
            if method == "PUT" and route == "/channels/piclaw-1/messages/501/reactions/%E2%9C%85/@me":
                return {}
            if method == "PUT" and route == "/channels/piclaw-1/messages/501/reactions/%F0%9F%9A%80/@me":
                return {}
            if method == "POST" and route == "/channels/piclaw-1/messages":
                assert payload is not None
                replies.append(str(payload.get("content", "")))
                return {"id": "reply-1"}
            if method == "DELETE" and route == "/channels/piclaw-1":
                deleted_channels.append("piclaw-1")
                return {"id": "piclaw-1"}
            raise AssertionError(f"unexpected Discord call {method} {route}")

        results = process_codex_control_commands(
            config,
            DiscordClient("token", transport=transport),
            now="2026-04-26T10:00:00Z",
        )

        self.assertEqual(results, [{"channel_id": "piclaw-1", "message_id": "501", "status": "filtered_cleaned"}])
        self.assertEqual(deleted_channels, ["piclaw-1"])
        self.assertEqual(len(replies), 1)
        self.assertIn("频道会被关闭", replies[0])
        queue = json.loads(config.queue_path.read_text(encoding="utf-8"))
        item = queue["items"][0]
        self.assertEqual(item["state"], "filtered_out")
        self.assertEqual(item["filtered_reason"], "manual_filter_cleanup")
        self.assertNotIn("discord", item)
        exclusions = json.loads((repo_root / "registry" / "auto-migration" / "manual-exclusions.json").read_text(encoding="utf-8"))
        self.assertEqual(exclusions["repos"][0]["full_name"], "rcarmo/piclaw")
        self.assertFalse(workspace_path.exists())
        branches = subprocess.run(
            ["git", "-C", str(repo_root), "branch", "--list", "migration/piclaw"],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(branches.stdout.strip(), "")
        state = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(state["channels"], {})
        self.assertFalse((notifications_dir / "20260426T000000Z-github-owner-piclaw.md").exists())


if __name__ == "__main__":
    unittest.main()
