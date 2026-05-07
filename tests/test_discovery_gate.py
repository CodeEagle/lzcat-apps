from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.discovery_gate import load_exclude_slugs, reconcile_queue_items


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
        self.assertEqual(item["candidate_status"], "already_migrated_by_other")
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

    def test_discovery_review_prompt_includes_lazycat_store_search_hits(self) -> None:
        queue = {
            "items": [
                {
                    "id": "github:paperclipai/paperclip",
                    "source": "paperclipai/paperclip",
                    "slug": "paperclip",
                    "state": "discovery_review",
                    "candidate_status": "needs_review",
                    "candidate": {
                        "full_name": "paperclipai/paperclip",
                        "repo_url": "https://github.com/paperclipai/paperclip",
                        "status_reason": "LazyCat app-store search returned matches; AI discovery review required.",
                        "lazycat_hits": [
                            {
                                "raw_label": "Paperclip AI",
                                "detail_url": "https://lazycat.cloud/appstore/detail/fun.selfstudio.app.paperclip",
                            }
                        ],
                    },
                }
            ]
        }

        changes = reconcile_queue_items(queue, publication_index={}, now="2026-04-26T10:00:00Z")

        self.assertEqual(changes, [{"id": "github:paperclipai/paperclip", "status": "discovery_review", "reason": "needs_ai_review"}])
        prompt = queue["items"][0]["discovery_review"]["prompt"]
        self.assertIn("懒猫商店搜索命中", prompt)
        self.assertIn("Paperclip AI", prompt)

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


    def test_excludes_slug_from_exclude_list(self) -> None:
        queue = {
            "items": [
                {
                    "id": "github:owner/codex-web",
                    "source": "owner/codex-web",
                    "slug": "codex-web",
                    "state": "ready",
                    "candidate_status": "portable",
                    "candidate": {"full_name": "owner/codex-web", "repo_url": "https://github.com/owner/codex-web"},
                }
            ]
        }

        changes = reconcile_queue_items(
            queue,
            publication_index={},
            now="2026-05-06T10:00:00Z",
            exclude_slugs={"codex-web"},
        )

        self.assertEqual(changes, [{"id": "github:owner/codex-web", "status": "filtered_out", "reason": "slug_excluded"}])
        item = queue["items"][0]
        self.assertEqual(item["state"], "filtered_out")
        self.assertEqual(item["filtered_reason"], "slug_excluded")
        self.assertIn("exclude-list.json", item["last_error"])

    def test_excluded_slug_already_filtered_is_idempotent(self) -> None:
        queue = {
            "items": [
                {
                    "id": "github:owner/codex-web",
                    "slug": "codex-web",
                    "state": "filtered_out",
                    "candidate_status": "excluded",
                    "filtered_reason": "slug_excluded",
                }
            ]
        }

        changes = reconcile_queue_items(
            queue,
            publication_index={},
            now="2026-05-06T10:00:00Z",
            exclude_slugs={"codex-web"},
        )

        self.assertEqual(changes, [])

    def test_load_exclude_slugs_reads_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "registry" / "auto-migration" / "exclude-list.json"
            target.parent.mkdir(parents=True)
            target.write_text(json.dumps({"slugs": ["codex-web", "  spaced  ", ""]}), encoding="utf-8")
            self.assertEqual(load_exclude_slugs(root), {"codex-web", "spaced"})

    def test_load_exclude_slugs_missing_returns_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(load_exclude_slugs(Path(tmp)), set())

    def test_does_not_demote_ready_with_committed_migrate_verdict(self) -> None:
        """Once the AI (or operator) issued a verdict, reconcile must
        leave the item alone — even when scout's candidate_status is
        still "needs_review" (it always is, until someone overwrites
        it). Without this guard, every promoted-to-ready item bounces
        back to discovery_review every cycle. Regression: StellaClaw
        2026-05-07T10:28Z worker run 25489902826.
        """
        queue = {
            "items": [
                {
                    "id": "github:owner/demo",
                    "slug": "demo",
                    "state": "ready",
                    "candidate_status": "needs_review",
                    "candidate": {"status": "portable"},
                    "discovery_review": {
                        "status": "migrate",
                        "score": 0.85,
                        "reviewer": "claude",
                    },
                }
            ]
        }
        changes = reconcile_queue_items(
            queue, publication_index={}, now="2026-05-07T10:30:00Z",
        )
        self.assertEqual(changes, [])
        self.assertEqual(queue["items"][0]["state"], "ready")

    def test_does_not_demote_other_states_with_committed_skip_or_needs_human(self) -> None:
        """Same protection for skip + needs_human verdicts."""
        for verdict, state, filtered_reason in (
            ("skip", "filtered_out", "ai_discovery_skip"),
            ("needs_human", "waiting_for_human", None),
        ):
            queue = {
                "items": [
                    {
                        "id": "github:owner/demo",
                        "slug": "demo",
                        "state": state,
                        "candidate_status": "needs_review",
                        "candidate": {"status": "portable"},
                        "discovery_review": {"status": verdict},
                    }
                ]
            }
            if filtered_reason:
                queue["items"][0]["filtered_reason"] = filtered_reason
            changes = reconcile_queue_items(
                queue, publication_index={}, now="2026-05-07T10:30:00Z",
            )
            self.assertEqual(queue["items"][0]["state"], state, f"verdict={verdict}")

    def test_demotes_ready_lacking_verdict_to_discovery_review(self) -> None:
        """The protection should apply only to items WITH a verdict.
        A ready item with no AI verdict (legacy / mechanical promotion)
        still gets bounced back so the AI can review it properly.
        """
        queue = {
            "items": [
                {
                    "id": "github:owner/demo",
                    "slug": "demo",
                    "state": "ready",
                    "candidate_status": "needs_review",
                    "candidate": {"status": "portable"},
                    # discovery_review absent (no verdict yet)
                }
            ]
        }
        changes = reconcile_queue_items(
            queue, publication_index={}, now="2026-05-07T10:30:00Z",
        )
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]["status"], "discovery_review")
        self.assertEqual(queue["items"][0]["state"], "discovery_review")


if __name__ == "__main__":
    unittest.main()
