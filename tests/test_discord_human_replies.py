from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.discord_human_replies import apply_human_replies
from scripts.discord_migration_notifier import DiscordClient


class DiscordHumanRepliesTest(unittest.TestCase):
    def test_applies_first_human_reply_and_acknowledges(self) -> None:
        calls: list[tuple[str, str, dict[str, object] | None]] = []

        def transport(method: str, route: str, payload: dict[str, object] | None = None) -> object:
            calls.append((method, route, payload))
            if method == "GET":
                self.assertEqual(route, "/channels/channel-1/messages?limit=20&after=progress-1")
                return [
                    {"id": "bot-1", "content": "status", "author": {"id": "bot", "bot": True}},
                    {"id": "human-1", "content": "选择官方作者信息，继续上架", "author": {"id": "u1", "username": "lincoln"}},
                ]
            if method == "POST":
                return {"id": "ack-1"}
            raise AssertionError(f"unexpected Discord call {method} {route}")

        queue = {
            "schema_version": 1,
            "items": [
                {
                    "id": "github:owner/demo",
                    "slug": "demo",
                    "state": "waiting_for_human",
                    "discord": {"channel_id": "channel-1", "message_id": "progress-1"},
                    "human_request": {"question": "作者信息怎么填？", "created_at": "2026-04-26T08:00:00Z"},
                }
            ],
        }

        results = apply_human_replies(queue, DiscordClient("token", transport=transport), now="2026-04-26T09:00:00Z")

        self.assertEqual(results, [{"id": "github:owner/demo", "status": "human_response_received", "message_id": "human-1"}])
        item = queue["items"][0]
        self.assertEqual(item["state"], "waiting_for_human")
        self.assertEqual(item["human_response"]["content"], "选择官方作者信息，继续上架")
        self.assertEqual(item["human_response"]["author_id"], "u1")
        self.assertEqual(item["discord"]["last_human_message_id"], "human-1")
        self.assertEqual(item["discord"]["last_human_ack_message_id"], "ack-1")
        self.assertEqual(calls[-1][0:2], ("POST", "/channels/channel-1/messages"))

    def test_ignores_waiting_items_without_human_messages(self) -> None:
        def transport(method: str, route: str, payload: dict[str, object] | None = None) -> object:
            if method == "GET":
                return [{"id": "bot-1", "content": "status", "author": {"id": "bot", "bot": True}}]
            raise AssertionError("ack should not be sent")

        queue = {
            "schema_version": 1,
            "items": [
                {
                    "id": "github:owner/demo",
                    "state": "waiting_for_human",
                    "discord": {"channel_id": "channel-1", "message_id": "progress-1"},
                    "human_request": {"question": "Need help?"},
                }
            ],
        }

        self.assertEqual(apply_human_replies(queue, DiscordClient("token", transport=transport), now="now"), [])
        self.assertNotIn("human_response", queue["items"][0])


if __name__ == "__main__":
    unittest.main()
