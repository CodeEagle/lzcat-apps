from __future__ import annotations

import json
import os
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
    CommandResult,
    DashboardConversationResult,
    DashboardConversationTurn,
    DashboardConversationWorker,
    build_dashboard_conversation_command,
    ParsedCommand,
    build_gateway_identify_payload,
    build_task,
    channel_context,
    codex_command_catalog,
    cleanup_workspace_and_branch,
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
    run_codex_control_task,
    _resolve_cti_home,
)
from scripts.discord_migration_notifier import DiscordClient
from scripts.discord_local_agent_commands import decision_token_for_item_id


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

    def make_config(
        self,
        repo_root: Path,
        *,
        workspace_root: Path | None = None,
        cti_home: Path | None = None,
        secret_admin_channel_id: str = "",
        secret_admin_user_ids: tuple[str, ...] = (),
    ) -> CodexControlConfig:
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
            dashboard_model="gpt-5.5",
            dashboard_reasoning_effort="xhigh",
            cti_home=cti_home or Path(""),
            secret_admin_channel_id=secret_admin_channel_id,
            secret_admin_user_ids=secret_admin_user_ids,
        )

    def test_parse_direct_and_mention_commands(self) -> None:
        self.assertEqual(parse_control_command("!status").kind, "status")
        self.assertEqual(parse_control_command("!codex 修一下截图").instruction, "修一下截图")
        self.assertEqual(parse_control_command("!fix").kind, "codex")
        self.assertEqual(parse_control_command("!filter-close").kind, "filter_cleanup")
        self.assertEqual(parse_control_command("!la status"), ParsedCommand("local_agent", "!la status"))
        self.assertEqual(parse_control_command("<@123> status", bot_user_id="123").kind, "status")
        self.assertEqual(parse_control_command("<@123> 继续处理", bot_user_id="123").instruction, "继续处理")
        self.assertIsNone(parse_control_command("<@123> 继续处理"))
        self.assertIsNone(parse_control_command("<@999> 继续处理", bot_user_id="123"))
        self.assertIsNone(parse_control_command("随便聊一句"))

    def test_dashboard_channel_context_can_be_disabled_for_agenthub_takeover(self) -> None:
        repo_root = self.make_repo_root()
        config = self.make_config(repo_root)
        old_value = os.environ.get("LZCAT_CODEX_DISABLE_DASHBOARD")
        os.environ["LZCAT_CODEX_DISABLE_DASHBOARD"] = "1"
        try:
            context = channel_context(
                {"id": "dashboard-1", "name": "dashboard", "type": 0, "parent_id": "category-1"},
                config,
                [],
            )
        finally:
            if old_value is None:
                os.environ.pop("LZCAT_CODEX_DISABLE_DASHBOARD", None)
            else:
                os.environ["LZCAT_CODEX_DISABLE_DASHBOARD"] = old_value

        self.assertIsNone(context)

    def test_local_agent_channel_context_allows_only_local_agent_commands(self) -> None:
        repo_root = self.make_repo_root()
        config = self.make_config(repo_root)
        context = channel_context(
            {"id": "local-agent-1", "name": "migration-local-agent", "type": 0, "parent_id": "category-1"},
            config,
            [],
        )

        self.assertIsNotNone(context)
        assert context is not None
        self.assertEqual(context.scope, "local_agent")
        self.assertFalse(context.implicit_codex)
        self.assertIsNone(parse_channel_message({"id": "1", "content": "随便聊一句"}, config, context))
        self.assertIsNone(parse_channel_message({"id": "2", "content": "!codex 开始迁移"}, config, context))
        parsed = parse_channel_message({"id": "3", "content": "!la status"}, config, context)
        self.assertEqual(parsed, ParsedCommand("local_agent", "!la status"))

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
        self.assertEqual(
            parse_interaction_command(
                {"type": 2, "data": {"name": "local-agent", "options": [{"name": "command", "value": "status"}]}}
            ),
            ParsedCommand("local_agent", "!la status"),
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
        self.assertIn("bridge", [str(command.get("name", "")) for command in codex_command_catalog()])

    def test_cti_home_defaults_to_agenthub_home_and_ignores_lzcat_home_env(self) -> None:
        repo_root = self.make_repo_root()
        config = self.make_config(repo_root)
        old_home = os.environ.get("CTI_HOME")
        old_agenthub_home = os.environ.get("AGENTHUB_HOME")
        old_lzcat_home = os.environ.get("CTI_LZCAT_HOME")
        os.environ.pop("CTI_HOME", None)
        os.environ.pop("AGENTHUB_HOME", None)
        os.environ["CTI_LZCAT_HOME"] = "/tmp/legacy-lzcat-home"
        try:
            resolved = _resolve_cti_home(config)
        finally:
            if old_home is None:
                os.environ.pop("CTI_HOME", None)
            else:
                os.environ["CTI_HOME"] = old_home
            if old_agenthub_home is None:
                os.environ.pop("AGENTHUB_HOME", None)
            else:
                os.environ["AGENTHUB_HOME"] = old_agenthub_home
            if old_lzcat_home is None:
                os.environ.pop("CTI_LZCAT_HOME", None)
            else:
                os.environ["CTI_LZCAT_HOME"] = old_lzcat_home

        self.assertEqual(resolved, Path("/Users/lincoln/Develop/GitHub/AgentHub/.agenthub/codex-to-im").resolve())

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

    def test_gateway_message_create_fast_replies_dashboard_status_question(self) -> None:
        repo_root = self.make_repo_root()
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
        context = ChannelContext(
            channel_id="dashboard-1",
            channel_name="dashboard",
            scope="dashboard",
            slug="dashboard",
            workdir=repo_root,
            implicit_codex=True,
        )
        replies: list[str] = []

        def transport(method: str, route: str, payload: dict[str, object] | None = None) -> object:
            if method == "PUT" and route == "/channels/dashboard-1/messages/902/reactions/%E2%9C%85/@me":
                return {}
            if method == "POST" and route == "/channels/dashboard-1/messages":
                assert payload is not None
                replies.append(str(payload.get("content", "")))
                return {"id": "reply-1"}
            raise AssertionError(f"unexpected Discord call {method} {route}")

        def runner(_: CodexControlTask) -> CodexControlRunResult:
            raise AssertionError("dashboard chat must not invoke per-message Codex worker")

        def dashboard_conversation(_: DashboardConversationTurn) -> DashboardConversationResult:
            raise AssertionError("status-like dashboard messages should use the local fast path")

        result = handle_gateway_message_create(
            config,
            DiscordClient("token", transport=transport),
            {"dashboard-1": context},
            {"id": "902", "channel_id": "dashboard-1", "content": "现在队列怎么样", "author": {"id": "u1"}},
            runner=runner,
            dashboard_conversation=dashboard_conversation,
            now="2026-04-26T10:00:00Z",
        )

        self.assertEqual(result, {"channel_id": "dashboard-1", "message_id": "902", "status": "status"})
        self.assertEqual(len(replies), 1)
        self.assertIn("Codex Dashboard 状态", replies[0])
        self.assertIn("队列：3", replies[0])
        self.assertFalse(config.state_path.exists())

    def test_dashboard_action_request_stays_in_persistent_conversation(self) -> None:
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
        turns: list[DashboardConversationTurn] = []
        replies: list[str] = []

        def transport(method: str, route: str, payload: dict[str, object] | None = None) -> object:
            if method == "PUT" and route == "/channels/dashboard-1/messages/905/reactions/%E2%9C%85/@me":
                return {}
            if method == "POST" and route == "/channels/dashboard-1/messages":
                assert payload is not None
                replies.append(str(payload.get("content", "")))
                return {"id": "reply-1"}
            raise AssertionError(f"unexpected Discord call {method} {route}")

        def runner(_: CodexControlTask) -> CodexControlRunResult:
            raise AssertionError("dashboard action requests must never enter the worker prompt")

        def dashboard_conversation(turn: DashboardConversationTurn) -> DashboardConversationResult:
            turns.append(turn)
            return DashboardConversationResult("completed", "我会保持在 dashboard 对话里处理这个请求。", session_id="dashboard-session-2")

        result = handle_gateway_message_create(
            config,
            DiscordClient("token", transport=transport),
            {"dashboard-1": context},
            {"id": "905", "channel_id": "dashboard-1", "content": "把发现逻辑改一下", "author": {"id": "u1"}},
            runner=runner,
            dashboard_conversation=dashboard_conversation,
            now="2026-04-27T10:00:00Z",
            progress_interval_seconds=0.01,
        )

        self.assertEqual(result, {"channel_id": "dashboard-1", "message_id": "905", "status": "completed"})
        self.assertEqual(len(turns), 1)
        self.assertEqual(turns[0].instruction, "把发现逻辑改一下")
        self.assertEqual(replies, ["我会保持在 dashboard 对话里处理这个请求。"])
        state = json.loads(config.state_path.read_text(encoding="utf-8"))
        self.assertEqual(state["channels"]["dashboard-1"]["codex"]["session_id"], "dashboard-session-2")

    def test_gateway_message_create_reports_timing_breakdown(self) -> None:
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
        timings: list[dict[str, object]] = []

        def transport(method: str, route: str, payload: dict[str, object] | None = None) -> object:
            if method == "PUT" and route == "/channels/dashboard-1/messages/907/reactions/%E2%9C%85/@me":
                return {}
            if method == "POST" and route == "/channels/dashboard-1/messages":
                return {"id": "reply-1"}
            raise AssertionError(f"unexpected Discord call {method} {route}")

        def runner(_: CodexControlTask) -> CodexControlRunResult:
            raise AssertionError("dashboard chat must not invoke per-message Codex worker")

        def dashboard_conversation(_: DashboardConversationTurn) -> DashboardConversationResult:
            return DashboardConversationResult("completed", "直接回复。", session_id="dashboard-session-1")

        result = handle_gateway_message_create(
            config,
            DiscordClient("token", transport=transport),
            {"dashboard-1": context},
            {"id": "907", "channel_id": "dashboard-1", "content": "随便聊一句", "author": {"id": "u1"}},
            runner=runner,
            dashboard_conversation=dashboard_conversation,
            now="2026-04-27T10:00:00Z",
            timing_sink=timings.append,
        )

        self.assertEqual(result, {"channel_id": "dashboard-1", "message_id": "907", "status": "completed"})
        self.assertEqual(len(timings), 1)
        timing = timings[0]
        self.assertEqual(timing["channel_id"], "dashboard-1")
        self.assertEqual(timing["message_id"], "907")
        self.assertEqual(timing["status"], "completed")
        self.assertEqual(timing["kind"], "codex")
        for key in ("parse_ms", "ack_ms", "codex_ms", "send_ms", "total_ms"):
            self.assertIsInstance(timing[key], int)

    def test_gateway_message_create_recognizes_image_attachment_for_dashboard_instruction(self) -> None:
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
        turns: list[DashboardConversationTurn] = []
        replies: list[str] = []

        def transport(method: str, route: str, payload: dict[str, object] | None = None) -> object:
            if method == "PUT" and route == "/channels/dashboard-1/messages/904/reactions/%E2%9C%85/@me":
                return {}
            if method == "POST" and route == "/channels/dashboard-1/messages":
                assert payload is not None
                replies.append(str(payload.get("content", "")))
                return {"id": "reply-1"}
            raise AssertionError(f"unexpected Discord call {method} {route}")

        def runner(_: CodexControlTask) -> CodexControlRunResult:
            raise AssertionError("dashboard chat must not invoke per-message Codex worker")

        def dashboard_conversation(turn: DashboardConversationTurn) -> DashboardConversationResult:
            turns.append(turn)
            return DashboardConversationResult("completed", "收到图片。", session_id="dashboard-session-1")

        result = handle_gateway_message_create(
            config,
            DiscordClient("token", transport=transport),
            {"dashboard-1": context},
            {
                "id": "904",
                "channel_id": "dashboard-1",
                "content": "",
                "attachments": [{"filename": "shot.png", "content_type": "image/png", "url": "https://cdn.example/shot.png"}],
                "author": {"id": "u1"},
            },
            runner=runner,
            dashboard_conversation=dashboard_conversation,
            now="2026-04-27T10:00:00Z",
            attachment_recognizer=lambda attachment, kind: __import__(
                "scripts.discord_attachment_recognition", fromlist=["AttachmentRecognitionResult"]
            ).AttachmentRecognitionResult(
                kind=kind,
                filename=str(attachment["filename"]),
                url=str(attachment["url"]),
                status="recognized",
                text="图片里是 LazyCat 安装错误页。",
            ),
        )

        self.assertEqual(result, {"channel_id": "dashboard-1", "message_id": "904", "status": "completed"})
        self.assertEqual(len(turns), 1)
        self.assertIn("附件识别结果", turns[0].instruction)
        self.assertIn("LazyCat 安装错误页", turns[0].instruction)
        self.assertEqual(turns[0].image_paths, ())
        self.assertEqual(replies, ["收到图片。"])

    def test_build_task_passes_native_codex_image_attachments(self) -> None:
        repo_root = self.make_repo_root()
        image_path = repo_root / "shot.png"
        image_path.write_bytes(b"fake")
        config = self.make_config(repo_root)
        context = ChannelContext(
            channel_id="piclaw-1",
            channel_name="migration-piclaw",
            scope="migration",
            slug="piclaw",
            item={"id": "item-1", "slug": "piclaw", "source": "owner/piclaw"},
            workdir=repo_root,
        )

        task = build_task(
            "看图修复",
            context,
            config,
            now="2026-04-27T10:00:00Z",
            task_id="message-1",
            image_paths=(image_path,),
        )

        self.assertIn("--image", task.command)
        self.assertIn(str(image_path), task.command)

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

    def test_gateway_message_create_runs_filter_close_with_client(self) -> None:
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
        config = self.make_config(repo_root, workspace_root=workspace_path.parent)
        item = json.loads(config.queue_path.read_text(encoding="utf-8"))["items"][0]
        context = ChannelContext(
            channel_id="piclaw-1",
            channel_name="migration-piclaw",
            scope="migration",
            slug="piclaw",
            item=item,
            workdir=workspace_path,
        )
        replies: list[str] = []
        deleted_channels: list[str] = []

        def transport(method: str, route: str, payload: dict[str, object] | None = None) -> object:
            if method == "PUT" and route == "/channels/piclaw-1/messages/906/reactions/%E2%9C%85/@me":
                return {}
            if method == "PUT" and route == "/channels/piclaw-1/messages/906/reactions/%F0%9F%9A%80/@me":
                return {}
            if method == "POST" and route == "/channels/piclaw-1/messages":
                assert payload is not None
                replies.append(str(payload.get("content", "")))
                return {"id": "reply-1"}
            if method == "DELETE" and route == "/channels/piclaw-1":
                deleted_channels.append("piclaw-1")
                return {"id": "piclaw-1"}
            raise AssertionError(f"unexpected Discord call {method} {route}")

        def runner(_: CodexControlTask) -> CodexControlRunResult:
            raise AssertionError("filter cleanup must not spawn Codex")

        result = handle_gateway_message_create(
            config,
            DiscordClient("token", transport=transport),
            {"piclaw-1": context},
            {"id": "906", "channel_id": "piclaw-1", "content": "!filter-close", "author": {"id": "u1"}},
            runner=runner,
            now="2026-04-26T10:00:00Z",
        )

        self.assertEqual(result, {"channel_id": "piclaw-1", "message_id": "906", "status": "filtered_cleaned"})
        self.assertEqual(deleted_channels, ["piclaw-1"])
        self.assertEqual(len(replies), 1)
        self.assertIn("频道会被关闭", replies[0])
        queue = json.loads(config.queue_path.read_text(encoding="utf-8"))
        self.assertEqual(queue["items"][0]["state"], "filtered_out")
        self.assertFalse(workspace_path.exists())

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

    def test_handle_command_runs_local_agent_command_without_codex(self) -> None:
        repo_root = self.make_repo_root()
        snapshot_path = repo_root / "registry" / "candidates" / "local-agent-latest.json"
        snapshot_path.parent.mkdir(parents=True)
        snapshot_path.write_text(json.dumps({"candidates": [{"status": "portable"}]}) + "\n", encoding="utf-8")
        self.write_queue(repo_root)
        config = self.make_config(repo_root)
        context = ChannelContext(
            channel_id="dashboard-1",
            channel_name="dashboard",
            scope="dashboard",
            slug="dashboard",
            workdir=repo_root,
        )

        def runner(_: CodexControlTask) -> CodexControlRunResult:
            raise AssertionError("LocalAgent command must not invoke Codex")

        result = handle_command(
            ParsedCommand("local_agent", "!la status"),
            context,
            config,
            runner=runner,
            now="2026-04-26T10:00:00Z",
        )

        self.assertEqual(result.status, "status")
        self.assertIn("LocalAgent 状态", result.reply)
        self.assertIn("候选快照：1", result.reply)

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

    def test_secret_set_writes_allowed_key_to_temp_home_with_masked_ephemeral_reply(self) -> None:
        repo_root = self.make_repo_root()
        cti_home = Path(tempfile.mkdtemp(prefix="discord-secret-home-"))
        config = self.make_config(repo_root, cti_home=cti_home, secret_admin_user_ids=("admin-1",))
        context = ChannelContext(
            channel_id="control-1",
            channel_name="migration-control",
            scope="control",
            workdir=repo_root,
        )
        secret_value = "fake-token-abc123456789xyz"
        events: list[tuple[str, str, dict[str, object] | None]] = []

        def transport(method: str, route: str, payload: dict[str, object] | None = None) -> object:
            events.append((method, route, payload))
            if method == "POST" and route == "/interactions/910/token-910/callback":
                assert payload is not None
                self.assertNotIn(secret_value, json.dumps(payload, ensure_ascii=False))
                return {}
            raise AssertionError(f"unexpected Discord call {method} {route}")

        result = handle_gateway_interaction_create(
            config,
            DiscordClient("token", transport=transport),
            {"control-1": context},
            {
                "id": "910",
                "application_id": "app-1",
                "channel_id": "control-1",
                "guild_id": "guild-1",
                "token": "token-910",
                "type": 2,
                "member": {"user": {"id": "admin-1"}},
                "data": {
                    "name": "secret",
                    "options": [
                        {
                            "type": 1,
                            "name": "set",
                            "options": [
                                {"name": "key", "value": "CTI_DISCORD_BOT_TOKEN"},
                                {"name": "value", "value": secret_value},
                            ],
                        }
                    ],
                },
            },
            runner=lambda task: (_ for _ in ()).throw(AssertionError(f"secret reached Codex prompt: {task.prompt}")),
            now="2026-04-26T10:00:00Z",
        )

        config_path = cti_home / "config.env"
        reply_payload = events[0][2] or {}
        reply_data = reply_payload.get("data") if isinstance(reply_payload.get("data"), dict) else {}
        reply_content = str(reply_data.get("content", ""))
        self.assertEqual(result, {"channel_id": "control-1", "message_id": "910", "status": "secret_set"})
        self.assertEqual(reply_data.get("flags"), 64)
        self.assertIn("CTI_DISCORD_BOT_TOKEN", reply_content)
        self.assertIn("重启", reply_content)
        self.assertNotIn(secret_value, reply_content)
        self.assertIn("fake", reply_content)
        self.assertIn("9xyz", reply_content)
        self.assertTrue(config_path.exists())
        self.assertEqual(config_path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(config_path.parent, cti_home)
        self.assertIn(f"CTI_DISCORD_BOT_TOKEN={secret_value}", config_path.read_text(encoding="utf-8"))
        self.assertNotIn(secret_value, json.dumps(result, ensure_ascii=False))

    def test_secret_set_rejects_invalid_key_without_leaking_value_or_writing(self) -> None:
        repo_root = self.make_repo_root()
        cti_home = Path(tempfile.mkdtemp(prefix="discord-secret-home-"))
        config = self.make_config(repo_root, cti_home=cti_home, secret_admin_user_ids=("admin-1",))
        context = ChannelContext(
            channel_id="control-1",
            channel_name="migration-control",
            scope="control",
            workdir=repo_root,
        )
        rejected_value = "fake-disallowed-secret-value"
        replies: list[str] = []

        def transport(method: str, route: str, payload: dict[str, object] | None = None) -> object:
            if method == "POST" and route == "/interactions/911/token-911/callback":
                assert payload is not None
                replies.append(json.dumps(payload, ensure_ascii=False))
                return {}
            raise AssertionError(f"unexpected Discord call {method} {route}")

        result = handle_gateway_interaction_create(
            config,
            DiscordClient("token", transport=transport),
            {"control-1": context},
            {
                "id": "911",
                "application_id": "app-1",
                "channel_id": "control-1",
                "guild_id": "guild-1",
                "token": "token-911",
                "type": 2,
                "member": {"user": {"id": "admin-1"}},
                "data": {
                    "name": "secret",
                    "options": [
                        {
                            "type": 1,
                            "name": "set",
                            "options": [
                                {"name": "key", "value": "CTI_NOT_ALLOWED"},
                                {"name": "value", "value": rejected_value},
                            ],
                        }
                    ],
                },
            },
            runner=lambda task: (_ for _ in ()).throw(AssertionError(f"secret reached Codex prompt: {task.prompt}")),
            now="2026-04-26T10:00:00Z",
        )

        self.assertEqual(result, {"channel_id": "control-1", "message_id": "911", "status": "secret_invalid_key"})
        self.assertFalse((cti_home / "config.env").exists())
        self.assertEqual(len(replies), 1)
        self.assertNotIn(rejected_value, replies[0])
        self.assertIn('"flags": 64', replies[0])

    def test_secret_show_masks_existing_values(self) -> None:
        repo_root = self.make_repo_root()
        cti_home = Path(tempfile.mkdtemp(prefix="discord-secret-home-"))
        cti_home.mkdir(parents=True, exist_ok=True)
        (cti_home / "config.env").write_text(
            "\n".join(
                [
                    "CTI_DISCORD_BOT_TOKEN=fake-token-for-show-123456",
                    "CTI_DISCORD_ALLOWED_USERS=admin-1,admin-2",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        (cti_home / "config.env").chmod(0o600)
        config = self.make_config(repo_root, cti_home=cti_home, secret_admin_user_ids=("admin-1",))
        context = ChannelContext(
            channel_id="control-1",
            channel_name="migration-control",
            scope="control",
            workdir=repo_root,
        )
        replies: list[dict[str, object]] = []

        def transport(method: str, route: str, payload: dict[str, object] | None = None) -> object:
            if method == "POST" and route == "/interactions/912/token-912/callback":
                assert payload is not None
                replies.append(payload)
                return {}
            raise AssertionError(f"unexpected Discord call {method} {route}")

        result = handle_gateway_interaction_create(
            config,
            DiscordClient("token", transport=transport),
            {"control-1": context},
            {
                "id": "912",
                "application_id": "app-1",
                "channel_id": "control-1",
                "guild_id": "guild-1",
                "token": "token-912",
                "type": 2,
                "member": {"user": {"id": "admin-1"}},
                "data": {"name": "secret", "options": [{"type": 1, "name": "show"}]},
            },
            runner=lambda task: (_ for _ in ()).throw(AssertionError(f"secret reached Codex prompt: {task.prompt}")),
            now="2026-04-26T10:00:00Z",
        )

        reply_data = (replies[0].get("data") or {}) if replies else {}
        reply_content = str(reply_data.get("content", ""))
        self.assertEqual(result, {"channel_id": "control-1", "message_id": "912", "status": "secret_show"})
        self.assertEqual(reply_data.get("flags"), 64)
        self.assertIn("CTI_DISCORD_BOT_TOKEN", reply_content)
        self.assertIn("CTI_DISCORD_ALLOWED_USERS", reply_content)
        self.assertNotIn("fake-token-for-show-123456", reply_content)
        self.assertNotIn("admin-1,admin-2", reply_content)
        self.assertIn("fake", reply_content)
        self.assertIn("3456", reply_content)

    def test_secret_command_requires_control_channel_and_admin_user(self) -> None:
        repo_root = self.make_repo_root()
        cti_home = Path(tempfile.mkdtemp(prefix="discord-secret-home-"))
        config = self.make_config(repo_root, cti_home=cti_home, secret_admin_user_ids=("admin-1",))
        migration_context = ChannelContext(
            channel_id="piclaw-1",
            channel_name="migration-piclaw",
            scope="migration",
            slug="piclaw",
            workdir=repo_root,
        )
        control_context = ChannelContext(
            channel_id="control-1",
            channel_name="migration-control",
            scope="control",
            workdir=repo_root,
        )
        replies: list[str] = []

        def transport(method: str, route: str, payload: dict[str, object] | None = None) -> object:
            if method == "POST" and route in {
                "/interactions/913/token-913/callback",
                "/interactions/914/token-914/callback",
            }:
                assert payload is not None
                replies.append(json.dumps(payload, ensure_ascii=False))
                return {}
            raise AssertionError(f"unexpected Discord call {method} {route}")

        base_interaction = {
            "application_id": "app-1",
            "guild_id": "guild-1",
            "type": 2,
            "data": {"name": "secret", "options": [{"type": 1, "name": "show"}]},
        }
        wrong_channel_result = handle_gateway_interaction_create(
            config,
            DiscordClient("token", transport=transport),
            {"piclaw-1": migration_context},
            {
                **base_interaction,
                "id": "913",
                "channel_id": "piclaw-1",
                "token": "token-913",
                "member": {"user": {"id": "admin-1"}},
            },
            now="2026-04-26T10:00:00Z",
        )
        wrong_user_result = handle_gateway_interaction_create(
            config,
            DiscordClient("token", transport=transport),
            {"control-1": control_context},
            {
                **base_interaction,
                "id": "914",
                "channel_id": "control-1",
                "token": "token-914",
                "member": {"user": {"id": "not-admin"}},
            },
            now="2026-04-26T10:00:00Z",
        )

        self.assertEqual(wrong_channel_result["status"], "secret_unauthorized")
        self.assertEqual(wrong_user_result["status"], "secret_unauthorized")
        self.assertFalse((cti_home / "config.env").exists())
        self.assertEqual(len(replies), 2)
        self.assertTrue(all('"flags": 64' in reply for reply in replies))

    def test_secret_admin_channel_is_discovered_without_implicit_codex(self) -> None:
        repo_root = self.make_repo_root()
        cti_home = Path(tempfile.mkdtemp(prefix="discord-secret-home-"))
        config = self.make_config(
            repo_root,
            cti_home=cti_home,
            secret_admin_channel_id="secret-1",
            secret_admin_user_ids=("admin-1",),
        )
        context = channel_context(
            {"id": "secret-1", "name": "migration-secrets", "type": 0, "parent_id": "private-category"},
            config,
            [],
        )

        self.assertIsNotNone(context)
        assert context is not None
        self.assertEqual(context.scope, "secret_admin")
        self.assertFalse(context.implicit_codex)
        self.assertIsNone(
            parse_channel_message(
                {"content": "CTI_DISCORD_BOT_TOKEN=should-not-enter-codex", "author": {"id": "admin-1"}},
                config,
                context,
            )
        )
        self.assertIsNone(
            parse_channel_message(
                {"content": "!codex read this secret", "author": {"id": "admin-1"}},
                config,
                context,
            )
        )

        replies: list[dict[str, object]] = []

        def transport(method: str, route: str, payload: dict[str, object] | None = None) -> object:
            if method == "POST" and route in {
                "/interactions/915/token-915/callback",
                "/interactions/916/token-916/callback",
            }:
                assert payload is not None
                replies.append(payload)
                return {}
            raise AssertionError(f"unexpected Discord call {method} {route}")

        result = handle_gateway_interaction_create(
            config,
            DiscordClient("token", transport=transport),
            {"secret-1": context},
            {
                "id": "915",
                "application_id": "app-1",
                "channel_id": "secret-1",
                "guild_id": "guild-1",
                "token": "token-915",
                "type": 2,
                "member": {"user": {"id": "admin-1"}},
                "data": {"name": "secret", "options": [{"type": 1, "name": "show"}]},
            },
            runner=lambda task: (_ for _ in ()).throw(AssertionError(f"secret reached Codex prompt: {task.prompt}")),
            now="2026-04-26T10:00:00Z",
        )

        self.assertEqual(result, {"channel_id": "secret-1", "message_id": "915", "status": "secret_show"})
        self.assertEqual((replies[0].get("data") or {}).get("flags"), 64)

        blocked_result = handle_gateway_interaction_create(
            config,
            DiscordClient("token", transport=transport),
            {"secret-1": context},
            {
                "id": "916",
                "application_id": "app-1",
                "channel_id": "secret-1",
                "guild_id": "guild-1",
                "token": "token-916",
                "type": 2,
                "member": {"user": {"id": "admin-1"}},
                "data": {"name": "codex", "options": [{"name": "task", "value": "read this secret"}]},
            },
            runner=lambda task: (_ for _ in ()).throw(AssertionError(f"non-secret reached Codex prompt: {task.prompt}")),
            now="2026-04-26T10:00:00Z",
        )

        self.assertEqual(blocked_result["status"], "secret_channel_restricted")

    def test_bridge_restart_is_admin_only_and_does_not_reach_codex(self) -> None:
        repo_root = self.make_repo_root()
        config = self.make_config(
            repo_root,
            secret_admin_channel_id="secret-1",
            secret_admin_user_ids=("admin-1",),
        )
        context = ChannelContext(
            channel_id="secret-1",
            channel_name="migration-secrets",
            scope="secret_admin",
            workdir=repo_root,
            implicit_codex=False,
        )
        replies: list[dict[str, object]] = []
        restarts: list[CodexControlConfig] = []

        def transport(method: str, route: str, payload: dict[str, object] | None = None) -> object:
            if method == "POST" and route == "/interactions/917/token-917/callback":
                assert payload is not None
                replies.append(payload)
                return {}
            raise AssertionError(f"unexpected Discord call {method} {route}")

        def bridge_restarter(restart_config: CodexControlConfig) -> CommandResult:
            restarts.append(restart_config)
            return CommandResult("bridge_restart_scheduled", "Bridge restart scheduled.")

        result = handle_gateway_interaction_create(
            config,
            DiscordClient("token", transport=transport),
            {"secret-1": context},
            {
                "id": "917",
                "application_id": "app-1",
                "channel_id": "secret-1",
                "guild_id": "guild-1",
                "token": "token-917",
                "type": 2,
                "member": {"user": {"id": "admin-1"}},
                "data": {"name": "bridge", "options": [{"type": 1, "name": "restart"}]},
            },
            runner=lambda task: (_ for _ in ()).throw(AssertionError(f"bridge restart reached Codex prompt: {task.prompt}")),
            bridge_restarter=bridge_restarter,
            now="2026-04-26T10:00:00Z",
        )

        self.assertEqual(result, {"channel_id": "secret-1", "message_id": "917", "status": "bridge_restart_scheduled"})
        self.assertEqual(restarts, [config])
        self.assertEqual((replies[0].get("data") or {}).get("flags"), 64)
        self.assertIn("Bridge restart scheduled", str((replies[0].get("data") or {}).get("content", "")))

    def test_gateway_routes_local_agent_button_to_queue_decision(self) -> None:
        repo_root = self.make_repo_root()
        snapshot_path = repo_root / "registry" / "candidates" / "local-agent-latest.json"
        snapshot_path.parent.mkdir(parents=True)
        snapshot_path.write_text(
            json.dumps(
                {
                    "candidates": [
                        {
                            "full_name": "owner/demo",
                            "repo": "demo",
                            "repo_url": "https://github.com/owner/demo",
                            "description": "Demo app",
                            "status": "portable",
                            "discovery_source": "local_agent",
                        }
                    ]
                }
            )
            + "\n",
            encoding="utf-8",
        )
        state_path = repo_root / "registry" / "auto-migration" / "discord-local-agent-commands.json"
        item_id = "github:owner/demo"
        token = decision_token_for_item_id(item_id)
        state_path.parent.mkdir(parents=True)
        state_path.write_text(json.dumps({"decision_tokens": {token: item_id}}) + "\n", encoding="utf-8")
        config = self.make_config(repo_root, secret_admin_user_ids=("admin-1",))
        context = ChannelContext(
            channel_id="local-agent-1",
            channel_name="migration-local-agent",
            scope="local_agent",
            workdir=repo_root,
            implicit_codex=False,
        )
        replies: list[dict[str, object]] = []

        def transport(method: str, route: str, payload: dict[str, object] | None = None) -> object:
            if method == "POST" and route == "/interactions/918/token-918/callback":
                assert payload is not None
                replies.append(payload)
                return {}
            raise AssertionError(f"unexpected Discord call {method} {route}")

        result = handle_gateway_interaction_create(
            config,
            DiscordClient("token", transport=transport),
            {"local-agent-1": context},
            {
                "id": "918",
                "application_id": "app-1",
                "channel_id": "local-agent-1",
                "guild_id": "guild-1",
                "token": "token-918",
                "type": 3,
                "member": {"user": {"id": "admin-1"}},
                "data": {"custom_id": f"la:queue:{token}"},
            },
            runner=lambda task: (_ for _ in ()).throw(AssertionError(f"local-agent button reached Codex prompt: {task.prompt}")),
            now="2026-04-26T10:00:00Z",
        )

        self.assertEqual(result, {"channel_id": "local-agent-1", "message_id": "918", "status": "local_agent_decision_queued"})
        self.assertEqual(replies[0]["type"], 7)
        self.assertIn("已加入待移植", str((replies[0].get("data") or {}).get("content", "")))
        queue = json.loads((repo_root / "registry" / "auto-migration" / "queue.json").read_text(encoding="utf-8"))
        self.assertEqual(queue["items"][0]["state"], "ready")

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
        turns: list[DashboardConversationTurn] = []
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
                return [{"id": "151", "content": "!codex 总结今天失败原因", "author": {"id": "u1"}}]
            if method == "PUT" and route == "/channels/dashboard-1/messages/151/reactions/%E2%9C%85/@me":
                return {}
            if method == "POST" and route == "/channels/dashboard-1/messages":
                assert payload is not None
                replies.append(str(payload.get("content", "")))
                return {"id": "reply-1"}
            raise AssertionError(f"unexpected Discord call {method} {route}")

        def runner(_: CodexControlTask) -> CodexControlRunResult:
            raise AssertionError("dashboard chat must not invoke per-message Codex worker")

        def dashboard_conversation(turn: DashboardConversationTurn) -> DashboardConversationResult:
            turns.append(turn)
            return DashboardConversationResult("completed", "今天失败主要是截图和作者信息。")

        results = process_codex_control_commands(
            config,
            DiscordClient("token", transport=transport),
            runner=runner,
            dashboard_conversation=dashboard_conversation,
            now="2026-04-26T10:00:00Z",
        )

        self.assertEqual(results, [{"channel_id": "dashboard-1", "message_id": "151", "status": "completed"}])
        self.assertEqual(len(turns), 1)
        self.assertEqual(turns[0].context.scope, "dashboard")
        self.assertEqual(turns[0].context.workdir, repo_root)
        self.assertEqual(turns[0].instruction, "总结今天失败原因")
        self.assertEqual(replies, ["今天失败主要是截图和作者信息。"])

    def test_dashboard_channel_uses_conversation_backend_instead_of_worker_resume(self) -> None:
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
        turns: list[DashboardConversationTurn] = []
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
                return [{"id": "152", "content": "!codex 继续", "author": {"id": "u1"}}]
            if method == "PUT" and route == "/channels/dashboard-1/messages/152/reactions/%E2%9C%85/@me":
                return {}
            if method == "POST" and route == "/channels/dashboard-1/messages":
                assert payload is not None
                replies.append(str(payload.get("content", "")))
                return {"id": "reply-1"}
            raise AssertionError(f"unexpected Discord call {method} {route}")

        def runner(_: CodexControlTask) -> CodexControlRunResult:
            raise AssertionError("dashboard chat must not build a resume task")

        def dashboard_conversation(turn: DashboardConversationTurn) -> DashboardConversationResult:
            turns.append(turn)
            return DashboardConversationResult("completed", "继续完成。", session_id="66666666-7777-8888-9999-aaaaaaaaaaaa")

        results = process_codex_control_commands(
            config,
            DiscordClient("token", transport=transport),
            runner=runner,
            dashboard_conversation=dashboard_conversation,
            now="2026-04-26T10:00:00Z",
        )

        self.assertEqual(results, [{"channel_id": "dashboard-1", "message_id": "152", "status": "completed"}])
        self.assertEqual(len(turns), 1)
        self.assertEqual(turns[0].instruction, "继续")
        self.assertEqual(replies, ["继续完成。"])
        state = json.loads(config.state_path.read_text(encoding="utf-8"))
        self.assertEqual(
            state["channels"]["dashboard-1"]["codex"]["session_id"],
            "66666666-7777-8888-9999-aaaaaaaaaaaa",
        )

    def test_run_codex_retries_dashboard_with_new_session_when_resume_is_missing(self) -> None:
        repo_root = self.make_repo_root()
        self.init_git_repo(repo_root)
        config = self.make_config(repo_root)
        config.state_path.parent.mkdir(parents=True, exist_ok=True)
        config.state_path.write_text(
            json.dumps(
                {
                    "channels": {
                        "dashboard-1": {
                            "channel_name": "dashboard",
                            "slug": "dashboard",
                            "codex": {"session_id": "11111111-2222-3333-4444-555555555555"},
                        }
                    }
                }
            )
            + "\n",
            encoding="utf-8",
        )
        fake_bin = repo_root / "fake-bin"
        fake_bin.mkdir()
        calls_path = repo_root / "codex-calls.txt"
        fake_codex = fake_bin / "codex"
        fake_codex.write_text(
            """#!/bin/sh
echo "$*" >> "$CODEX_FAKE_CALLS"
last=""
previous=""
for arg in "$@"; do
  if [ "$previous" = "--output-last-message" ]; then
    last="$arg"
  fi
  previous="$arg"
done
for arg in "$@"; do
  if [ "$arg" = "resume" ]; then
    echo "Error: thread/resume: thread/resume failed: no rollout found for thread id 11111111-2222-3333-4444-555555555555" >&2
    exit 1
  fi
done
printf '%s\\n' '{"type":"session","session_id":"66666666-7777-8888-9999-aaaaaaaaaaaa"}'
if [ -n "$last" ]; then
  printf '新会话完成。\\n' > "$last"
fi
exit 0
""",
            encoding="utf-8",
        )
        fake_codex.chmod(0o755)
        context = ChannelContext(
            channel_id="dashboard-1",
            channel_name="dashboard",
            scope="dashboard",
            slug="dashboard",
            workdir=repo_root,
        )
        task = build_task("继续", context, config, now="2026-04-26T10:00:00Z", task_id="152")
        old_path = os.environ.get("PATH", "")
        old_calls = os.environ.get("CODEX_FAKE_CALLS")
        os.environ["PATH"] = f"{fake_bin}:{old_path}"
        os.environ["CODEX_FAKE_CALLS"] = str(calls_path)
        try:
            result = run_codex_control_task(task)
        finally:
            os.environ["PATH"] = old_path
            if old_calls is None:
                os.environ.pop("CODEX_FAKE_CALLS", None)
            else:
                os.environ["CODEX_FAKE_CALLS"] = old_calls

        calls = calls_path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.session_id, "66666666-7777-8888-9999-aaaaaaaaaaaa")
        self.assertEqual(len(calls), 2)
        self.assertIn("resume", calls[0])
        self.assertNotIn("resume", calls[1])

    def test_dashboard_conversation_command_uses_repo_root_for_empty_workdir(self) -> None:
        repo_root = self.make_repo_root()
        config = self.make_config(repo_root)
        context = ChannelContext(
            channel_id="dashboard-1",
            channel_name="dashboard",
            scope="dashboard",
            slug="dashboard",
            workdir=Path(""),
        )

        command = build_dashboard_conversation_command(
            config,
            context,
            session_id="",
            last_message_path=repo_root / "last-message.md",
        )

        self.assertEqual(command[command.index("-C") + 1], str(repo_root))
        self.assertEqual(command[command.index("--model") + 1], "gpt-5.5")
        self.assertEqual(command[command.index("--config") + 1], 'model_reasoning_effort="xhigh"')

    def test_dashboard_conversation_resets_session_when_previous_usage_is_too_large(self) -> None:
        repo_root = self.make_repo_root()
        self.init_git_repo(repo_root)
        config = CodexControlConfig(
            repo_root=repo_root,
            queue_path=repo_root / "registry" / "auto-migration" / "queue.json",
            state_path=repo_root / "registry" / "auto-migration" / "discord-codex-control.json",
            task_root=repo_root / "registry" / "auto-migration" / "codex-control-tasks",
            model="gpt-5.5",
            dashboard_model="gpt-5.5",
            dashboard_reasoning_effort="xhigh",
            dashboard_session_max_input_tokens=100,
        )
        config.state_path.parent.mkdir(parents=True, exist_ok=True)
        config.state_path.write_text(
            json.dumps(
                {
                    "channels": {
                        "dashboard-1": {
                            "channel_name": "dashboard",
                            "slug": "dashboard",
                            "codex": {"session_id": "11111111-2222-3333-4444-555555555555"},
                        }
                    }
                }
            )
            + "\n",
            encoding="utf-8",
        )
        conversation_root = repo_root / "registry" / "auto-migration" / "dashboard-conversations" / "dashboard-1"
        conversation_root.mkdir(parents=True)
        (conversation_root / "codex.stdout.log").write_text(
            '{"type":"turn.completed","usage":{"input_tokens":101,"cached_input_tokens":90}}\n',
            encoding="utf-8",
        )
        fake_bin = repo_root / "fake-bin"
        fake_bin.mkdir()
        calls_path = repo_root / "codex-calls.txt"
        fake_codex = fake_bin / "codex"
        fake_codex.write_text(
            """#!/bin/sh
echo "$*" >> "$CODEX_FAKE_CALLS"
last=""
previous=""
for arg in "$@"; do
  if [ "$previous" = "--output-last-message" ]; then
    last="$arg"
  fi
  previous="$arg"
done
printf '%s\\n' '{"type":"thread.started","thread_id":"66666666-7777-8888-9999-aaaaaaaaaaaa"}'
if [ -n "$last" ]; then
  printf '新会话完成。\\n' > "$last"
fi
exit 0
""",
            encoding="utf-8",
        )
        fake_codex.chmod(0o755)
        context = ChannelContext(
            channel_id="dashboard-1",
            channel_name="dashboard",
            scope="dashboard",
            slug="dashboard",
            workdir=repo_root,
        )
        turn = DashboardConversationTurn("继续", context, config, now="2026-04-26T10:00:00Z", message_id="152")
        old_path = os.environ.get("PATH", "")
        old_calls = os.environ.get("CODEX_FAKE_CALLS")
        os.environ["PATH"] = f"{fake_bin}:{old_path}"
        os.environ["CODEX_FAKE_CALLS"] = str(calls_path)
        try:
            result = DashboardConversationWorker()(turn)
        finally:
            os.environ["PATH"] = old_path
            if old_calls is None:
                os.environ.pop("CODEX_FAKE_CALLS", None)
            else:
                os.environ["CODEX_FAKE_CALLS"] = old_calls

        calls = calls_path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.session_id, "66666666-7777-8888-9999-aaaaaaaaaaaa")
        self.assertEqual(len(calls), 1)
        self.assertNotIn("resume", calls[0])
        self.assertEqual(calls[0].split()[calls[0].split().index("--model") + 1], "gpt-5.5")
        self.assertEqual(calls[0].split()[calls[0].split().index("--config") + 1], 'model_reasoning_effort="xhigh"')

    def test_filter_close_refuses_empty_workdir(self) -> None:
        repo_root = self.make_repo_root()
        self.init_git_repo(repo_root)
        config = self.make_config(repo_root)
        context = ChannelContext(
            channel_id="piclaw-1",
            channel_name="migration-piclaw",
            scope="migration",
            slug="piclaw",
            item={"id": "github:rcarmo/piclaw", "source": "rcarmo/piclaw", "slug": "piclaw"},
            workdir=Path(""),
        )

        with self.assertRaisesRegex(RuntimeError, "unsafe cleanup workdir"):
            cleanup_workspace_and_branch(config, context)

        self.assertTrue((repo_root / "README.md").exists())

    def test_filter_close_refuses_repo_root_workdir(self) -> None:
        repo_root = self.make_repo_root()
        self.init_git_repo(repo_root)
        config = self.make_config(repo_root)
        context = ChannelContext(
            channel_id="piclaw-1",
            channel_name="migration-piclaw",
            scope="migration",
            slug="piclaw",
            item={"id": "github:rcarmo/piclaw", "source": "rcarmo/piclaw", "slug": "piclaw"},
            workdir=repo_root,
        )

        with self.assertRaisesRegex(RuntimeError, "unsafe cleanup workdir"):
            cleanup_workspace_and_branch(config, context)

        self.assertTrue((repo_root / "README.md").exists())

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
