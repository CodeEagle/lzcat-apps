from __future__ import annotations

import sys
import unittest
import io
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.discord_migration_notifier import (
    DiscordClient,
    MigrationDiscordNotifier,
    build_progress_message,
    channel_name_for_slug,
    split_discord_message,
)


class DiscordMigrationNotifierTest(unittest.TestCase):
    def test_channel_name_for_slug_uses_prefix_and_normalizes(self) -> None:
        self.assertEqual(channel_name_for_slug("PicLaw", prefix="migration"), "migration-piclaw")
        self.assertEqual(channel_name_for_slug("owner/my_app", prefix="lzcat migration"), "lzcat-migration-my-app")

    def test_channel_name_for_slug_truncates_to_discord_limit(self) -> None:
        name = channel_name_for_slug("owner/" + "a" * 180, prefix="migration")

        self.assertLessEqual(len(name), 100)
        self.assertTrue(name.startswith("migration-"))

    def test_build_progress_message_contains_project_card_and_steps(self) -> None:
        item = {
            "id": "github:owner/piclaw",
            "source": "owner/piclaw",
            "slug": "piclaw",
            "state": "browser_pending",
            "candidate": {
                "description": "Simple legal citation manager",
                "repo_url": "https://github.com/owner/piclaw",
            },
        }

        content = build_progress_message(item, status="browser_pending", now="2026-04-26T08:00:00Z")

        self.assertIn("piclaw", content)
        self.assertIn("owner/piclaw", content)
        self.assertIn("browser_pending", content)
        self.assertIn("Simple legal citation manager", content)
        self.assertIn("桌面截图 2 张", content)
        self.assertIn("手机截图 3 张", content)
        self.assertIn("Playground", content)

    def test_split_discord_message_preserves_long_content(self) -> None:
        content = ("第一段\n" + "x" * 2100 + "\n第二段\n" + "y" * 1800)

        chunks = split_discord_message(content, limit=1900)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 1900 for chunk in chunks))
        self.assertEqual("".join(chunks), content)

    def test_client_uses_discord_v10_routes(self) -> None:
        calls: list[tuple[str, str, dict[str, object] | None]] = []

        def transport(method: str, route: str, payload: dict[str, object] | None = None) -> object:
            calls.append((method, route, payload))
            if method == "GET":
                return []
            if route.endswith("/messages"):
                return {"id": "message-1", "channel_id": "channel-1"}
            return {"id": "channel-1", "name": "migration-piclaw"}

        client = DiscordClient("token", transport=transport)
        channel = client.ensure_text_channel("guild-1", "category-1", "migration-piclaw", topic="Migrating piclaw")
        message = client.send_message(channel["id"], "hello")
        client.add_reaction(channel["id"], message["id"], "%F0%9F%91%80")
        client.edit_message(channel["id"], message["id"], "updated")

        self.assertEqual(
            calls,
            [
                ("GET", "/guilds/guild-1/channels", None),
                (
                    "POST",
                    "/guilds/guild-1/channels",
                    {"name": "migration-piclaw", "type": 0, "parent_id": "category-1", "topic": "Migrating piclaw"},
                ),
                (
                    "POST",
                    "/channels/channel-1/messages",
                    {"content": "hello", "allowed_mentions": {"parse": []}},
                ),
                ("PUT", "/channels/channel-1/messages/message-1/reactions/%F0%9F%91%80/@me", None),
                (
                    "PATCH",
                    "/channels/channel-1/messages/message-1",
                    {"content": "updated", "allowed_mentions": {"parse": []}},
                ),
            ],
        )

    def test_notifier_reuses_channel_and_edits_existing_message_state(self) -> None:
        events: list[tuple[str, str, dict[str, object] | None]] = []

        def transport(method: str, route: str, payload: dict[str, object] | None = None) -> object:
            events.append((method, route, payload))
            if method == "GET":
                return [{"id": "channel-1", "name": "migration-piclaw", "type": 0, "parent_id": "category-1"}]
            if method == "PATCH":
                return {"id": "message-1", "channel_id": "channel-1"}
            raise AssertionError(f"unexpected transport call: {method} {route}")

        item = {
            "id": "github:owner/piclaw",
            "source": "owner/piclaw",
            "slug": "piclaw",
            "state": "browser_pending",
            "discord": {"channel_id": "channel-1", "message_id": "message-1"},
        }
        notifier = MigrationDiscordNotifier(
            client=DiscordClient("token", transport=transport),
            guild_id="guild-1",
            category_id="category-1",
            channel_prefix="migration",
        )

        state = notifier.publish_update(item, status="browser_failed", now="2026-04-26T08:00:00Z")

        self.assertEqual(state["channel_id"], "channel-1")
        self.assertEqual(state["message_id"], "message-1")
        self.assertEqual(state["last_status"], "browser_failed")
        self.assertEqual(state["last_update_at"], "2026-04-26T08:00:00Z")
        self.assertEqual(events[0], ("GET", "/guilds/guild-1/channels", None))
        self.assertEqual(events[1][0:2], ("PATCH", "/channels/channel-1/messages/message-1"))

    def test_notifier_sends_new_message_when_existing_message_cannot_be_edited(self) -> None:
        events: list[tuple[str, str, dict[str, object] | None]] = []

        def transport(method: str, route: str, payload: dict[str, object] | None = None) -> object:
            events.append((method, route, payload))
            if method == "GET":
                return [{"id": "channel-1", "name": "migration-piclaw", "type": 0, "parent_id": "category-1"}]
            if method == "PATCH":
                raise urllib.error.HTTPError("url", 403, "Forbidden", {}, io.BytesIO(b""))
            if method == "POST" and route.endswith("/messages"):
                return {"id": "message-2", "channel_id": "channel-1"}
            raise AssertionError(f"unexpected transport call: {method} {route}")

        item = {
            "id": "github:owner/piclaw",
            "source": "owner/piclaw",
            "slug": "piclaw",
            "discord": {"channel_id": "channel-1", "message_id": "message-1"},
        }
        notifier = MigrationDiscordNotifier(
            client=DiscordClient("token", transport=transport),
            guild_id="guild-1",
            category_id="category-1",
            channel_prefix="migration",
        )

        state = notifier.publish_update(item, status="build_failed", now="2026-04-26T08:00:00Z")

        self.assertEqual(state["message_id"], "message-2")
        self.assertEqual(events[1][0:2], ("PATCH", "/channels/channel-1/messages/message-1"))
        self.assertEqual(events[2][0:2], ("POST", "/channels/channel-1/messages"))


if __name__ == "__main__":
    unittest.main()
