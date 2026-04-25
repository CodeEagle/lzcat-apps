from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from unittest.mock import patch

from scripts.scout_core import (
    build_search_terms,
    check_candidate,
    classify_search_hits,
    merge_repositories,
    parse_trending_repositories,
    search_lazycat,
)


class ScoutCoreTest(unittest.TestCase):
    def test_build_search_terms_includes_dash_and_space_variants(self) -> None:
        self.assertEqual(build_search_terms("paperclip-ai"), ["paperclip-ai", "paperclip ai"])

    def test_classify_strong_lazycat_match_as_already_migrated(self) -> None:
        status, reason = classify_search_hits(
            {"repo": "paperclip", "full_name": "paperclipai/paperclip"},
            [{"raw_label": "Paperclip AI", "detail_url": "https://lazycat.cloud/appstore/detail/x"}],
        )

        self.assertEqual(status, "already_migrated")
        self.assertIn("Strong", reason)

    def test_merge_repositories_combines_sources(self) -> None:
        repos = [
            {
                "source_name": "github_trending_daily",
                "source_label": "GitHub Trending Daily",
                "owner": "owner",
                "repo": "demo",
                "full_name": "owner/demo",
                "repo_url": "https://github.com/owner/demo",
                "description": "Demo",
                "language": "Python",
                "total_stars": 100,
                "stars_today": 3,
            },
            {
                "source_name": "awesome_selfhosted",
                "source_label": "Awesome Self-Hosted",
                "owner": "owner",
                "repo": "demo",
                "full_name": "owner/demo",
                "repo_url": "https://github.com/owner/demo",
                "description": "Demo app",
                "language": "",
                "total_stars": 120,
                "stars_today": 0,
            },
        ]

        merged = merge_repositories(repos)

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["sources"], ["awesome_selfhosted", "github_trending_daily"])
        self.assertEqual(merged[0]["total_stars"], 120)

    def test_parse_trending_repositories_from_jina_markdown(self) -> None:
        markdown = """
[owner / demo](http://github.com/owner/demo)

A demo self-hosted app.

Python[1,234](http://github.com/owner/demo/stargazers) 5 stars today
"""
        source = {"name": "github_trending_daily", "label": "GitHub Trending Daily"}

        repos = parse_trending_repositories(markdown, source)

        self.assertEqual(len(repos), 1)
        self.assertEqual(repos[0]["full_name"], "owner/demo")
        self.assertEqual(repos[0]["description"], "A demo self-hosted app.")
        self.assertEqual(repos[0]["language"], "Python")
        self.assertEqual(repos[0]["total_stars"], 1234)
        self.assertEqual(repos[0]["stars_today"], 5)

    @patch("scripts.scout_core.fetch_text")
    def test_search_lazycat_returns_already_migrated_for_strong_hit(self, fetch_text_mock) -> None:
        fetch_text_mock.return_value = """
[![Image 0](x) Paperclip AI](http://lazycat.cloud/appstore/detail/fun.selfstudio.app.migration.paperclip)
"""
        repo = {"repo": "paperclip", "full_name": "paperclipai/paperclip"}

        result = search_lazycat(repo)

        self.assertEqual(result["status"], "already_migrated")
        self.assertEqual(result["hits"][0]["raw_label"], "Paperclip AI")
        self.assertEqual(result["searches"][0]["term"], "paperclip")

    @patch("scripts.scout_core.search_lazycat")
    def test_check_candidate_excludes_non_deployable_without_store_search(self, search_mock) -> None:
        repo = {
            "source_name": "github_search_high_star_recent",
            "source_label": "GitHub Search High Star",
            "owner": "owner",
            "repo": "demo-sdk",
            "full_name": "owner/demo-sdk",
            "repo_url": "https://github.com/owner/demo-sdk",
            "description": "SDK for demo integrations",
            "language": "Python",
            "total_stars": 3000,
            "stars_today": 0,
            "sources": ["github_search_high_star_recent"],
            "source_labels": ["GitHub Search High Star"],
        }

        candidate = check_candidate(repo, checked_at="2026-04-25T00:00:00Z")

        search_mock.assert_not_called()
        self.assertEqual(candidate["status"], "excluded")
        self.assertEqual(candidate["status_reason"], "Likely not a deployable self-hosted app/service")
        self.assertEqual(candidate["exclusion"]["matched_keyword"], "sdk")

    @patch("scripts.scout_core.search_lazycat")
    def test_check_candidate_uses_publication_index_before_store_search(self, search_mock) -> None:
        repo = {
            "source_name": "manual_check",
            "source_label": "Manual Check",
            "owner": "owner",
            "repo": "demo",
            "full_name": "owner/demo",
            "repo_url": "https://github.com/owner/demo",
            "description": "Self-hosted demo app",
            "language": "Python",
            "total_stars": 1000,
            "stars_today": 0,
        }
        publication_index = {
            "by_upstream_repo": {
                "owner/demo": {
                    "slug": "demo",
                    "package": "fun.selfstudio.app.migration.owner.demo",
                    "publication_status": "published",
                    "store_label": "Demo",
                    "migration_status": "migrated",
                }
            }
        }

        candidate = check_candidate(repo, checked_at="2026-04-25T00:00:00Z", publication_index=publication_index)

        search_mock.assert_not_called()
        self.assertEqual(candidate["status"], "already_migrated")
        self.assertIn("developer page", candidate["status_reason"])
        self.assertEqual(candidate["local_app"]["slug"], "demo")


if __name__ == "__main__":
    unittest.main()
