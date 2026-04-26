from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.dashboard_daily_summary import build_daily_summary, render_markdown, write_daily_summary


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


if __name__ == "__main__":
    unittest.main()
