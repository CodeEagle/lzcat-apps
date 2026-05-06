from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.local_agent_bridge import build_local_agent_snapshot, write_local_agent_snapshot


class LocalAgentBridgeTest(unittest.TestCase):
    def make_local_agent_root(self) -> Path:
        root = Path(tempfile.mkdtemp(prefix="local-agent-bridge-test-"))
        (root / "data").mkdir(parents=True)
        return root

    def test_build_snapshot_normalizes_projects_and_external_sources(self) -> None:
        root = self.make_local_agent_root()
        (root / "data" / "state.json").write_text(
            json.dumps(
                {
                    "projects": {
                        "owner/demo": {
                            "full_name": "owner/demo",
                            "owner": "owner",
                            "repo": "demo",
                            "repo_url": "https://github.com/owner/demo",
                            "description": "A deployable demo app",
                            "language": "Python",
                            "stars_today": 9,
                            "total_stars": 100,
                            "status": "portable",
                            "status_reason": "No matching app found",
                            "sources": ["github_trending_daily"],
                            "source_labels": ["GitHub Trending Daily"],
                        },
                        "owner/existing": {
                            "full_name": "owner/existing",
                            "repo_url": "https://github.com/owner/existing",
                            "status": "already_migrated",
                            "status_reason": "Found in existing catalog",
                        }
                    }
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (root / "data" / "external_sources.json").write_text(
            json.dumps(
                {
                    "candidates": [
                        {
                            "full_name": "outside/tool",
                            "repo_url": "https://github.com/outside/tool",
                            "description": "Mentioned by a feed",
                            "external_signal": "Mentioned by notable X account",
                            "external_url": "https://x.com/example/status/1",
                        }
                    ]
                }
            )
            + "\n",
            encoding="utf-8",
        )

        snapshot = build_local_agent_snapshot(root, now="2026-04-26T09:30:00Z")

        candidates = snapshot["candidates"]
        self.assertEqual([candidate["full_name"] for candidate in candidates], ["owner/demo", "outside/tool", "owner/existing"])
        self.assertEqual(candidates[0]["status"], "portable")
        self.assertEqual(candidates[0]["discovery_source"], "local_agent")
        self.assertEqual(candidates[0]["local_agent"]["origin"], "state.projects")
        self.assertEqual(candidates[1]["status"], "needs_review")
        self.assertEqual(candidates[1]["local_agent"]["origin"], "external_sources")
        self.assertEqual(candidates[2]["status"], "already_migrated_by_other")
        self.assertEqual(snapshot["meta"]["source"], "local_agent")
        self.assertEqual(snapshot["meta"]["generated_at"], "2026-04-26T09:30:00Z")

    def test_write_snapshot_creates_parent_directory(self) -> None:
        root = self.make_local_agent_root()
        (root / "data" / "state.json").write_text(json.dumps({"projects": {}}) + "\n", encoding="utf-8")
        output_path = root / "out" / "local-agent-latest.json"

        snapshot = write_local_agent_snapshot(root, output_path, now="2026-04-26T09:30:00Z")

        self.assertTrue(output_path.exists())
        self.assertEqual(json.loads(output_path.read_text(encoding="utf-8")), snapshot)

    def test_write_snapshot_uses_lazycat_store_search_hits_for_ai_review(self) -> None:
        root = self.make_local_agent_root()
        (root / "data" / "state.json").write_text(
            json.dumps(
                {
                    "projects": {
                        "paperclipai/paperclip": {
                            "full_name": "paperclipai/paperclip",
                            "repo": "paperclip",
                            "repo_url": "https://github.com/paperclipai/paperclip",
                            "description": "Self-hosted AI paperclip service",
                            "status": "portable",
                            "status_reason": "No matching app found",
                        }
                    }
                }
            )
            + "\n",
            encoding="utf-8",
        )
        output_path = root / "out" / "local-agent-latest.json"
        calls: list[str] = []

        def searcher(repo: dict[str, object]) -> dict[str, object]:
            calls.append(str(repo["full_name"]))
            return {
                "status": "needs_review",
                "reason": "LazyCat app-store search returned matches; AI discovery review required.",
                "searches": [{"term": "paperclip", "search_url": "https://lazycat.cloud/appstore/search?keyword=paperclip"}],
                "hits": [
                    {
                        "raw_label": "Paperclip AI",
                        "detail_url": "https://lazycat.cloud/appstore/detail/fun.selfstudio.app.paperclip",
                    }
                ],
                "errors": [],
            }

        snapshot = write_local_agent_snapshot(
            root,
            output_path,
            now="2026-04-26T09:30:00Z",
            enable_store_search=True,
            store_searcher=searcher,
        )

        self.assertEqual(calls, ["paperclipai/paperclip"])
        candidate = snapshot["candidates"][0]
        self.assertEqual(candidate["status"], "needs_review")
        self.assertEqual(candidate["lazycat_hits"][0]["raw_label"], "Paperclip AI")
        self.assertEqual(candidate["ai_store_review"]["status"], "pending")
        self.assertEqual(candidate["ai_store_review"]["source"], "lazycat_store_search")
        self.assertIn("Paperclip AI", candidate["ai_store_review"]["evidence"][0])

    def test_write_snapshot_reuses_lazycat_store_search_cache(self) -> None:
        root = self.make_local_agent_root()
        (root / "data" / "state.json").write_text(
            json.dumps(
                {
                    "projects": {
                        "owner/demo": {
                            "full_name": "owner/demo",
                            "repo": "demo",
                            "repo_url": "https://github.com/owner/demo",
                            "description": "Self-hosted demo app",
                            "status": "portable",
                        }
                    }
                }
            )
            + "\n",
            encoding="utf-8",
        )
        output_path = root / "out" / "local-agent-latest.json"
        cache_path = root / "out" / "store-search-cache.json"
        calls = 0

        def searcher(repo: dict[str, object]) -> dict[str, object]:
            nonlocal calls
            calls += 1
            return {
                "status": "portable",
                "reason": "No matching app found in LazyCat app store search.",
                "searches": [{"term": "demo"}],
                "hits": [],
                "errors": [],
            }

        first = write_local_agent_snapshot(
            root,
            output_path,
            now="2026-04-26T09:30:00Z",
            enable_store_search=True,
            store_searcher=searcher,
            store_search_cache_path=cache_path,
        )
        second = write_local_agent_snapshot(
            root,
            output_path,
            now="2026-04-26T09:31:00Z",
            enable_store_search=True,
            store_searcher=searcher,
            store_search_cache_path=cache_path,
        )

        self.assertEqual(calls, 1)
        self.assertEqual(first["candidates"][0]["lazycat_store_search"]["status"], "portable")
        self.assertEqual(second["candidates"][0]["lazycat_store_search"]["status"], "portable")

    def test_write_snapshot_refreshes_expired_store_search_cache(self) -> None:
        root = self.make_local_agent_root()
        (root / "data" / "state.json").write_text(
            json.dumps(
                {
                    "projects": {
                        "owner/demo": {
                            "full_name": "owner/demo",
                            "repo": "demo",
                            "repo_url": "https://github.com/owner/demo",
                            "description": "Self-hosted demo app",
                            "status": "portable",
                        }
                    }
                }
            )
            + "\n",
            encoding="utf-8",
        )
        output_path = root / "out" / "local-agent-latest.json"
        cache_path = root / "out" / "store-search-cache.json"
        calls = 0

        def searcher(repo: dict[str, object]) -> dict[str, object]:
            nonlocal calls
            calls += 1
            if calls == 1:
                return {
                    "status": "portable",
                    "reason": "No matching app found in LazyCat app store search.",
                    "searches": [{"term": "demo"}],
                    "hits": [],
                    "errors": [],
                }
            return {
                "status": "needs_review",
                "reason": "LazyCat app-store search returned matches; AI discovery review required.",
                "searches": [{"term": "demo"}],
                "hits": [{"raw_label": "Demo", "detail_url": "https://lazycat.cloud/appstore/detail/demo"}],
                "errors": [],
            }

        first = write_local_agent_snapshot(
            root,
            output_path,
            now="2026-04-26T09:30:00Z",
            enable_store_search=True,
            store_searcher=searcher,
            store_search_cache_path=cache_path,
            store_search_ttl_seconds=3600,
        )
        fresh = write_local_agent_snapshot(
            root,
            output_path,
            now="2026-04-26T10:00:00Z",
            enable_store_search=True,
            store_searcher=searcher,
            store_search_cache_path=cache_path,
            store_search_ttl_seconds=3600,
        )
        expired = write_local_agent_snapshot(
            root,
            output_path,
            now="2026-04-26T11:00:01Z",
            enable_store_search=True,
            store_searcher=searcher,
            store_search_cache_path=cache_path,
            store_search_ttl_seconds=3600,
        )

        self.assertEqual(calls, 2)
        self.assertEqual(first["candidates"][0]["status"], "portable")
        self.assertEqual(fresh["candidates"][0]["status"], "portable")
        self.assertEqual(expired["candidates"][0]["status"], "needs_review")
        self.assertEqual(expired["meta"]["store_search_review"]["refreshed"], 1)


if __name__ == "__main__":
    unittest.main()
