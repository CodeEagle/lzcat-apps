from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.discord_local_agent_commands import (
    LocalAgentCommandConfig,
    command_channel_name,
    decision_token_for_item_id,
    handle_decision_interaction,
    handle_command_text,
    local_agent_candidate_id,
    process_local_agent_commands,
)
from scripts.discord_migration_notifier import DiscordClient


class DiscordLocalAgentCommandsTest(unittest.TestCase):
    def make_repo_root(self) -> Path:
        return Path(tempfile.mkdtemp(prefix="discord-local-agent-commands-test-"))

    def make_local_agent_root(self, repo_root: Path) -> Path:
        local_agent_root = repo_root / "LocalAgent"
        data_dir = local_agent_root / "data"
        data_dir.mkdir(parents=True)
        (data_dir / "state.json").write_text(
            json.dumps(
                {
                    "projects": {
                        "owner/demo": {
                            "full_name": "owner/demo",
                            "repo_url": "https://github.com/owner/demo",
                            "description": "Demo app",
                            "status": "portable",
                            "total_stars": 42,
                        },
                        "owner/list": {
                            "full_name": "owner/list",
                            "repo_url": "https://github.com/owner/list",
                            "description": "Needs review item",
                            "status": "needs_review",
                            "total_stars": 7,
                        },
                    }
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (data_dir / "external_sources.json").write_text(json.dumps({"candidates": []}) + "\n", encoding="utf-8")
        return local_agent_root

    def test_command_channel_name_uses_migration_prefix(self) -> None:
        self.assertEqual(command_channel_name("migration"), "migration-local-agent")
        self.assertEqual(command_channel_name("LazyCat Ops"), "lazycat-ops-local-agent")

    def test_status_command_reports_snapshot_and_queue_counts(self) -> None:
        repo_root = self.make_repo_root()
        local_agent_root = self.make_local_agent_root(repo_root)
        snapshot_path = repo_root / "registry" / "candidates" / "local-agent-latest.json"
        snapshot_path.parent.mkdir(parents=True)
        snapshot_path.write_text(
            json.dumps({"candidates": [{"status": "portable"}, {"status": "needs_review"}]}) + "\n",
            encoding="utf-8",
        )
        queue_path = repo_root / "registry" / "auto-migration" / "queue.json"
        queue_path.parent.mkdir(parents=True)
        queue_path.write_text(
            json.dumps({"items": [{"state": "ready"}, {"state": "discovery_review"}, {"state": "filtered_out"}]}) + "\n",
            encoding="utf-8",
        )
        config = LocalAgentCommandConfig(
            repo_root=repo_root,
            local_agent_root=local_agent_root,
            snapshot_path=snapshot_path,
            queue_path=queue_path,
        )

        result = handle_command_text("!la status", config, now="2026-04-26T10:00:00Z")

        self.assertEqual(result.status, "status")
        self.assertIn("LocalAgent", result.reply)
        self.assertIn("候选快照：2", result.reply)
        self.assertIn("portable=1", result.reply)
        self.assertIn("ready=1", result.reply)

    def test_import_command_refreshes_snapshot(self) -> None:
        repo_root = self.make_repo_root()
        local_agent_root = self.make_local_agent_root(repo_root)
        snapshot_path = repo_root / "registry" / "candidates" / "local-agent-latest.json"
        config = LocalAgentCommandConfig(repo_root=repo_root, local_agent_root=local_agent_root, snapshot_path=snapshot_path)

        result = handle_command_text("/la import", config, now="2026-04-26T10:00:00Z")

        self.assertEqual(result.status, "imported")
        self.assertIn("导入 2 个候选", result.reply)
        payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["meta"]["candidate_count"], 2)

    def test_queue_command_lists_local_agent_queue_items(self) -> None:
        repo_root = self.make_repo_root()
        local_agent_root = self.make_local_agent_root(repo_root)
        queue_path = repo_root / "registry" / "auto-migration" / "queue.json"
        queue_path.parent.mkdir(parents=True)
        queue_path.write_text(
            json.dumps(
                {
                    "items": [
                        {
                            "id": "github:owner/demo",
                            "source": "owner/demo",
                            "slug": "demo",
                            "state": "ready",
                            "candidate": {"discovery_source": "local_agent", "description": "Demo app"},
                        },
                        {
                            "id": "github:other/app",
                            "source": "other/app",
                            "slug": "app",
                            "state": "ready",
                            "candidate": {"discovery_source": "scout"},
                        },
                    ]
                }
            )
            + "\n",
            encoding="utf-8",
        )
        config = LocalAgentCommandConfig(repo_root=repo_root, local_agent_root=local_agent_root, queue_path=queue_path)

        result = handle_command_text("!la queue 3", config, now="2026-04-26T10:00:00Z")

        self.assertEqual(result.status, "queue")
        self.assertIn("owner/demo", result.reply)
        self.assertNotIn("other/app", result.reply)

    def test_process_local_agent_commands_replies_and_tracks_last_message(self) -> None:
        repo_root = self.make_repo_root()
        local_agent_root = self.make_local_agent_root(repo_root)
        state_path = repo_root / "registry" / "auto-migration" / "discord-local-agent-commands.json"
        events: list[tuple[str, str, dict[str, object] | None]] = []

        def transport(method: str, route: str, payload: dict[str, object] | None = None) -> object:
            events.append((method, route, payload))
            if method == "GET" and route == "/guilds/guild-1/channels":
                return [{"id": "channel-1", "name": "migration-local-agent", "type": 0, "parent_id": "category-1"}]
            if method == "GET" and route == "/channels/channel-1/messages?limit=20":
                return [
                    {"id": "bot-1", "content": "!la status", "author": {"bot": True}},
                    {"id": "human-1", "content": "!la import", "author": {"id": "u1", "username": "lincoln"}},
                ]
            if method == "POST" and route == "/channels/channel-1/messages":
                return {"id": "reply-1"}
            raise AssertionError(f"unexpected Discord call {method} {route}")

        config = LocalAgentCommandConfig(
            repo_root=repo_root,
            local_agent_root=local_agent_root,
            snapshot_path=repo_root / "registry" / "candidates" / "local-agent-latest.json",
            state_path=state_path,
            guild_id="guild-1",
            category_id="category-1",
            channel_prefix="migration",
        )

        results = process_local_agent_commands(config, DiscordClient("token", transport=transport), now="2026-04-26T10:00:00Z")

        self.assertEqual(results, [{"message_id": "human-1", "status": "imported"}])
        self.assertTrue(any(event[0:2] == ("POST", "/channels/channel-1/messages") for event in events))
        state = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(state["last_message_id"], "human-1")

    def test_process_local_agent_commands_reports_snapshot_once_and_reuses_outside_category_channel(self) -> None:
        repo_root = self.make_repo_root()
        local_agent_root = self.make_local_agent_root(repo_root)
        snapshot_path = repo_root / "registry" / "candidates" / "local-agent-latest.json"
        snapshot_path.parent.mkdir(parents=True)
        snapshot_path.write_text(
            json.dumps({"candidates": [{"status": "portable"}, {"status": "needs_review"}]}) + "\n",
            encoding="utf-8",
        )
        state_path = repo_root / "registry" / "auto-migration" / "discord-local-agent-commands.json"
        posts: list[str] = []

        def transport(method: str, route: str, payload: dict[str, object] | None = None) -> object:
            if method == "GET" and route == "/guilds/guild-1/channels":
                return [{"id": "channel-1", "name": "migration-local-agent", "type": 0, "parent_id": None}]
            if method == "GET" and route == "/channels/channel-1/messages?limit=20":
                return []
            if method == "POST" and route == "/channels/channel-1/messages":
                assert payload is not None
                posts.append(str(payload.get("content", "")))
                return {"id": f"reply-{len(posts)}"}
            raise AssertionError(f"unexpected Discord call {method} {route}")

        config = LocalAgentCommandConfig(
            repo_root=repo_root,
            local_agent_root=local_agent_root,
            snapshot_path=snapshot_path,
            state_path=state_path,
            guild_id="guild-1",
            category_id="full-category",
            channel_prefix="migration",
            decision_card_limit=0,
        )

        first = process_local_agent_commands(config, DiscordClient("token", transport=transport), now="2026-04-26T10:00:00Z")
        second = process_local_agent_commands(config, DiscordClient("token", transport=transport), now="2026-04-26T10:01:00Z")

        self.assertEqual(first, [{"message_id": "", "status": "local_agent_reported"}])
        self.assertEqual(second, [])
        self.assertEqual(len(posts), 1)
        self.assertIn("LocalAgent 状态", posts[0])
        self.assertIn("候选快照：2", posts[0])
        state = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(state["channel_id"], "channel-1")
        self.assertIn("last_snapshot_signature", state)

    def test_process_local_agent_commands_publishes_decision_cards_for_actionable_candidates(self) -> None:
        repo_root = self.make_repo_root()
        local_agent_root = self.make_local_agent_root(repo_root)
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
                        },
                        {
                            "full_name": "owner/list",
                            "repo": "list",
                            "repo_url": "https://github.com/owner/list",
                            "description": "Needs review item",
                            "status": "needs_review",
                            "discovery_source": "local_agent",
                        },
                    ]
                }
            )
            + "\n",
            encoding="utf-8",
        )
        state_path = repo_root / "registry" / "auto-migration" / "discord-local-agent-commands.json"
        posts: list[dict[str, object]] = []

        def transport(method: str, route: str, payload: dict[str, object] | None = None) -> object:
            if method == "GET" and route == "/guilds/guild-1/channels":
                return [{"id": "channel-1", "name": "migration-local-agent", "type": 0, "parent_id": "category-1"}]
            if method == "GET" and route == "/channels/channel-1/messages?limit=20":
                return []
            if method == "POST" and route == "/channels/channel-1/messages":
                assert payload is not None
                posts.append(payload)
                return {"id": f"reply-{len(posts)}"}
            raise AssertionError(f"unexpected Discord call {method} {route}")

        config = LocalAgentCommandConfig(
            repo_root=repo_root,
            local_agent_root=local_agent_root,
            snapshot_path=snapshot_path,
            state_path=state_path,
            guild_id="guild-1",
            category_id="category-1",
            channel_prefix="migration",
            decision_card_limit=2,
        )

        results = process_local_agent_commands(config, DiscordClient("token", transport=transport), now="2026-04-26T10:00:00Z")

        self.assertIn({"message_id": "", "status": "local_agent_reported"}, results)
        self.assertIn({"message_id": "", "status": "local_agent_decision_cards_reported", "count": "2"}, results)
        card_posts = [post for post in posts if post.get("components")]
        self.assertEqual(len(card_posts), 2)
        first_card = card_posts[0]
        self.assertIn("LocalAgent 候选", str(first_card.get("content", "")))
        self.assertIn("进入待移植", json.dumps(first_card["components"], ensure_ascii=False))
        state = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertIn("github:owner/demo", state["decision_cards"])
        self.assertIn("github:owner/list", state["decision_cards"])

    def test_handle_decision_interaction_queues_candidate_and_updates_card(self) -> None:
        repo_root = self.make_repo_root()
        snapshot_path = repo_root / "registry" / "candidates" / "local-agent-latest.json"
        snapshot_path.parent.mkdir(parents=True)
        candidate = {
            "full_name": "owner/demo",
            "repo": "demo",
            "repo_url": "https://github.com/owner/demo",
            "description": "Demo app",
            "status": "portable",
            "discovery_source": "local_agent",
        }
        snapshot_path.write_text(json.dumps({"candidates": [candidate]}) + "\n", encoding="utf-8")
        state_path = repo_root / "registry" / "auto-migration" / "discord-local-agent-commands.json"
        item_id = local_agent_candidate_id(candidate)
        token = decision_token_for_item_id(item_id)
        state_path.parent.mkdir(parents=True)
        state_path.write_text(
            json.dumps({"decision_tokens": {token: item_id}, "decision_cards": {item_id: {"message_id": "card-1"}}}) + "\n",
            encoding="utf-8",
        )
        config = LocalAgentCommandConfig(
            repo_root=repo_root,
            snapshot_path=snapshot_path,
            queue_path=repo_root / "registry" / "auto-migration" / "queue.json",
            state_path=state_path,
            guild_id="guild-1",
            decision_user_ids=("admin-1",),
        )

        result = handle_decision_interaction(
            {
                "id": "interaction-1",
                "type": 3,
                "guild_id": "guild-1",
                "channel_id": "channel-1",
                "member": {"user": {"id": "admin-1"}},
                "data": {"custom_id": f"la:queue:{token}"},
            },
            config,
            now="2026-04-26T10:00:00Z",
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.status, "local_agent_decision_queued")
        self.assertIn("已加入待移植", result.reply)
        self.assertFalse(result.ephemeral)
        queue = json.loads((repo_root / "registry" / "auto-migration" / "queue.json").read_text(encoding="utf-8"))
        self.assertEqual(queue["items"][0]["id"], "github:owner/demo")
        self.assertEqual(queue["items"][0]["state"], "ready")
        state = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(state["decision_cards"][item_id]["decision"], "queue")

    def test_handle_decision_interaction_rejects_non_admin(self) -> None:
        repo_root = self.make_repo_root()
        config = LocalAgentCommandConfig(repo_root=repo_root, guild_id="guild-1", decision_user_ids=("admin-1",))

        result = handle_decision_interaction(
            {
                "id": "interaction-1",
                "type": 3,
                "guild_id": "guild-1",
                "channel_id": "channel-1",
                "member": {"user": {"id": "other-user"}},
                "data": {"custom_id": "la:queue:missing"},
            },
            config,
            now="2026-04-26T10:00:00Z",
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.status, "local_agent_decision_unauthorized")
        self.assertTrue(result.ephemeral)


if __name__ == "__main__":
    unittest.main()
