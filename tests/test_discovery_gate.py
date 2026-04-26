from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.discovery_gate import reconcile_queue_items


class DiscoveryGateTest(unittest.TestCase):
    def test_filters_ready_item_when_upstream_repo_is_published(self) -> None:
        queue = {
            "items": [
                {
                    "id": "github:owner/demo",
                    "source": "owner/demo",
                    "slug": "demo",
                    "state": "ready",
                    "candidate_status": "portable",
                    "candidate": {"full_name": "owner/demo", "repo_url": "https://github.com/owner/demo"},
                }
            ]
        }
        publication_index = {
            "by_upstream_repo": {
                "owner/demo": {
                    "slug": "demo",
                    "upstream_repo": "owner/demo",
                    "publication_status": "published",
                    "store_label": "Demo",
                }
            },
            "by_slug": {},
            "by_package": {},
        }

        changes = reconcile_queue_items(queue, publication_index=publication_index, now="2026-04-26T10:00:00Z")

        self.assertEqual(changes, [{"id": "github:owner/demo", "status": "filtered_out", "reason": "published_upstream"}])
        item = queue["items"][0]
        self.assertEqual(item["state"], "filtered_out")
        self.assertEqual(item["candidate_status"], "already_migrated")
        self.assertIn("Published app", item["last_error"])

    def test_filters_protected_item_when_latest_candidate_is_already_migrated(self) -> None:
        queue = {
            "items": [
                {
                    "id": "github:owner/demo",
                    "source": "owner/demo",
                    "slug": "demo",
                    "state": "build_failed",
                    "candidate_status": "already_migrated",
                    "candidate": {"status_reason": "Strong app-store match found"},
                }
            ]
        }

        changes = reconcile_queue_items(queue, publication_index={}, now="2026-04-26T10:00:00Z")

        self.assertEqual(changes, [{"id": "github:owner/demo", "status": "filtered_out", "reason": "candidate_already_migrated"}])
        self.assertEqual(queue["items"][0]["state"], "filtered_out")
        self.assertEqual(queue["items"][0]["last_error"], "Strong app-store match found")

    def test_sends_needs_review_item_to_discovery_review(self) -> None:
        queue = {
            "items": [
                {
                    "id": "github:owner/demo",
                    "source": "owner/demo",
                    "slug": "demo",
                    "state": "filtered_out",
                    "candidate_status": "needs_review",
                    "candidate": {
                        "full_name": "owner/demo",
                        "repo_url": "https://github.com/owner/demo",
                        "status_reason": "Weak app-store match needs AI review",
                    },
                }
            ]
        }

        changes = reconcile_queue_items(queue, publication_index={}, now="2026-04-26T10:00:00Z")

        self.assertEqual(changes, [{"id": "github:owner/demo", "status": "discovery_review", "reason": "needs_ai_review"}])
        item = queue["items"][0]
        self.assertEqual(item["state"], "discovery_review")
        self.assertIn("判断是否值得迁移", item["discovery_review"]["prompt"])
        self.assertEqual(item["discovery_review"]["created_at"], "2026-04-26T10:00:00Z")

    def test_keeps_ai_skipped_item_filtered_when_candidate_still_needs_review(self) -> None:
        queue = {
            "items": [
                {
                    "id": "github:owner/list",
                    "source": "owner/list",
                    "slug": "list",
                    "state": "filtered_out",
                    "candidate_status": "needs_review",
                    "filtered_reason": "ai_discovery_skip",
                    "discovery_review": {"status": "skip", "reason": "Curated list, not app"},
                    "candidate": {"full_name": "owner/list", "repo_url": "https://github.com/owner/list"},
                }
            ]
        }

        changes = reconcile_queue_items(queue, publication_index={}, now="2026-04-26T10:00:00Z")

        self.assertEqual(changes, [])
        self.assertEqual(queue["items"][0]["state"], "filtered_out")
        self.assertEqual(queue["items"][0]["discovery_review"]["status"], "skip")

    def test_ensures_existing_discovery_review_item_has_prompt(self) -> None:
        queue = {
            "items": [
                {
                    "id": "github:owner/demo",
                    "source": "owner/demo",
                    "slug": "demo",
                    "state": "discovery_review",
                    "candidate_status": "needs_review",
                    "candidate": {"full_name": "owner/demo", "repo_url": "https://github.com/owner/demo"},
                }
            ]
        }

        changes = reconcile_queue_items(queue, publication_index={}, now="2026-04-26T10:00:00Z")

        self.assertEqual(changes, [{"id": "github:owner/demo", "status": "discovery_review", "reason": "needs_ai_review"}])
        self.assertIn("判断是否值得迁移", queue["items"][0]["discovery_review"]["prompt"])


if __name__ == "__main__":
    unittest.main()
