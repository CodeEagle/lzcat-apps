from __future__ import annotations

import json
import io
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.dashboard_daily_summary import build_daily_summary, publish_dashboard_to_discord, render_markdown, write_daily_summary


class DashboardDailySummaryTest(unittest.TestCase):
    def make_repo_root(self) -> Path:
        root = Path(tempfile.mkdtemp(prefix="dashboard-summary-test-"))
        (root / "registry" / "auto-migration").mkdir(parents=True)
        (root / "registry" / "status").mkdir(parents=True)
        (root / "registry" / "candidates").mkdir(parents=True)
        return root

    def test_build_summary_counts_queue_candidates_and_publication(self) -> None:
        root = self.make_repo_root()
        (root / "registry" / "auto-migration" / "queue.json").write_text(
            json.dumps(
                {
                    "items": [
                        {"id": "github:owner/one", "slug": "one", "source": "owner/one", "state": "ready"},
                        {
                            "id": "github:owner/two",
                            "slug": "two",
                            "source": "owner/two",
                            "state": "waiting_for_human",
                            "human_request": {"question": "作者填谁？"},
                        },
                        {"id": "github:owner/three", "slug": "three", "source": "owner/three", "state": "publish_ready"},
                    ]
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (root / "registry" / "status" / "local-publication-status.json").write_text(
            json.dumps({"apps": {"one": {"status": "published"}, "three": {"status": "draft"}}}) + "\n",
            encoding="utf-8",
        )
        (root / "registry" / "candidates" / "local-agent-latest.json").write_text(
            json.dumps(
                {
                    "candidates": [
                        {"full_name": "owner/one", "status": "portable", "stars_today": 8, "total_stars": 80},
                        {"full_name": "owner/review", "status": "needs_review", "stars_today": 2, "total_stars": 20},
                        {"full_name": "owner/done", "status": "already_migrated", "stars_today": 99, "total_stars": 990},
                        {"full_name": "owner/cli", "status": "excluded", "stars_today": 88, "total_stars": 880},
                    ]
                }
            )
            + "\n",
            encoding="utf-8",
        )

        summary = build_daily_summary(root, report_date="2026-04-26", now="2026-04-26T09:30:00Z")

        self.assertEqual(summary["queue"]["state_counts"]["ready"], 1)
        self.assertEqual(summary["queue"]["state_counts"]["waiting_for_human"], 1)
        self.assertEqual(summary["publication"]["status_counts"]["published"], 1)
        self.assertEqual(summary["local_agent"]["status_counts"]["portable"], 1)
        self.assertEqual(summary["top_candidates"][0]["full_name"], "owner/one")
        self.assertNotIn("owner/done", [candidate["full_name"] for candidate in summary["top_candidates"]])
        self.assertNotIn("owner/cli", [candidate["full_name"] for candidate in summary["top_candidates"]])
        self.assertEqual(summary["waiting_for_human"][0]["question"], "作者填谁？")

    def test_build_summary_counts_publication_status_field(self) -> None:
        root = self.make_repo_root()
        (root / "registry" / "auto-migration" / "queue.json").write_text(
            json.dumps({"items": []}) + "\n",
            encoding="utf-8",
        )
        (root / "registry" / "status" / "local-publication-status.json").write_text(
            json.dumps(
                {
                    "apps": {
                        "one": {"publication_status": "published"},
                        "two": {"publication_status": "in_progress"},
                    }
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (root / "registry" / "candidates" / "local-agent-latest.json").write_text(
            json.dumps({"candidates": []}) + "\n",
            encoding="utf-8",
        )

        summary = build_daily_summary(root, report_date="2026-04-26", now="2026-04-26T09:30:00Z")

        self.assertEqual(summary["publication"]["status_counts"]["published"], 1)
        self.assertEqual(summary["publication"]["status_counts"]["in_progress"], 1)

    def test_render_and_write_daily_summary_outputs_markdown_and_latest_files(self) -> None:
        root = self.make_repo_root()
        summary = {
            "date": "2026-04-26",
            "generated_at": "2026-04-26T09:30:00Z",
            "queue": {"total": 1, "state_counts": {"ready": 1}},
            "publication": {"total": 0, "status_counts": {}},
            "local_agent": {"total": 0, "status_counts": {}},
            "top_candidates": [],
            "waiting_for_human": [],
            "failed_items": [],
            "reward_opportunities": ["上架完成", "Playground 攻略"],
        }

        markdown = render_markdown(summary)
        self.assertIn("LazyCat 自动移植日报", markdown)
        self.assertIn("2026-04-26", markdown)

        paths = write_daily_summary(root, summary)
        self.assertTrue(paths["daily_json"].exists())
        self.assertTrue(paths["daily_markdown"].exists())
        self.assertTrue((root / "registry" / "dashboard" / "latest.json").exists())
        self.assertTrue((root / "registry" / "dashboard" / "latest.md").exists())

    def test_publish_dashboard_sends_long_markdown_in_chunks(self) -> None:
        root = self.make_repo_root()
        sent: list[str] = []

        class FakeClient:
            def ensure_text_channel(self, guild_id: str, category_id: str, channel_name: str, *, topic: str = "") -> dict[str, str]:
                return {"id": "channel-1"}

            def send_message(self, channel_id: str, content: str) -> dict[str, str]:
                sent.append(content)
                return {"id": f"message-{len(sent)}"}

            def edit_message(self, channel_id: str, message_id: str, content: str) -> dict[str, str]:
                sent.append(content)
                return {"id": message_id}

        markdown = "x" * 2500

        publish_dashboard_to_discord(
            root,
            markdown,
            token="token",
            guild_id="guild-1",
            category_id="category-1",
            channel_name="dashboard",
            client=FakeClient(),
        )

        self.assertGreater(len(sent), 1)
        self.assertTrue(all(len(chunk) <= 1900 for chunk in sent))
        self.assertEqual("".join(sent), markdown)

    def test_publish_dashboard_sends_new_message_when_existing_message_cannot_be_edited(self) -> None:
        root = self.make_repo_root()
        (root / "registry" / "dashboard").mkdir(parents=True)
        (root / "registry" / "dashboard" / "discord-state.json").write_text(
            json.dumps({"channel_id": "channel-1", "message_id": "old-message"}) + "\n",
            encoding="utf-8",
        )
        sent: list[str] = []

        class FakeClient:
            def ensure_text_channel(self, guild_id: str, category_id: str, channel_name: str, *, topic: str = "") -> dict[str, str]:
                return {"id": "channel-1"}

            def send_message(self, channel_id: str, content: str) -> dict[str, str]:
                sent.append(content)
                return {"id": "new-message"}

            def edit_message(self, channel_id: str, message_id: str, content: str) -> dict[str, str]:
                raise urllib.error.HTTPError("url", 403, "Forbidden", {}, io.BytesIO(b""))

        state = publish_dashboard_to_discord(
            root,
            "fresh dashboard",
            token="token",
            guild_id="guild-1",
            category_id="category-1",
            channel_name="dashboard",
            client=FakeClient(),
        )

        self.assertEqual(sent, ["fresh dashboard"])
        self.assertEqual(state["message_id"], "new-message")


if __name__ == "__main__":
    unittest.main()
