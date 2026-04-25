from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.publication_status import (
    build_publication_index,
    build_status_snapshot,
    write_status_snapshot,
)


class PublicationStatusTest(unittest.TestCase):
    def make_repo_root(self) -> Path:
        return Path(tempfile.mkdtemp(prefix="publication-status-test-"))

    def write_manifest(self, repo_root: Path, slug: str, package: str, name: str) -> None:
        app_root = repo_root / "apps" / slug
        app_root.mkdir(parents=True)
        (app_root / "lzc-manifest.yml").write_text(
            f"""
lzc-sdk-version: '0.1'
package: {package}
version: 0.1.0
name: {name}
homepage: https://github.com/owner/{slug}
""".lstrip(),
            encoding="utf-8",
        )

    def write_registry(self, repo_root: Path, slug: str, upstream_repo: str, migration_status: str) -> None:
        registry_root = repo_root / "registry" / "repos"
        registry_root.mkdir(parents=True, exist_ok=True)
        (registry_root / f"{slug}.json").write_text(
            json.dumps(
                {
                    "enabled": True,
                    "upstream_repo": upstream_repo,
                    "migration_status": migration_status,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    def write_developer_apps(self, repo_root: Path, apps: dict[str, str]) -> None:
        status_root = repo_root / "registry" / "status"
        status_root.mkdir(parents=True, exist_ok=True)
        (status_root / "developer-apps.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "source": "developer_apps_page",
                    "apps": apps,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    def test_build_status_snapshot_marks_published_apps_from_developer_page(self) -> None:
        repo_root = self.make_repo_root()
        package = "fun.selfstudio.app.migration.owner.demo"
        self.write_manifest(repo_root, "demo", package, "Demo")
        self.write_registry(repo_root, "demo", "owner/demo", "migrated")
        self.write_developer_apps(repo_root, {package: "Demo Store Name"})

        snapshot = build_status_snapshot(repo_root, generated_at="2026-04-26T00:00:00Z")

        self.assertEqual(snapshot["meta"]["local_app_count"], 1)
        self.assertEqual(snapshot["meta"]["published_count"], 1)
        self.assertEqual(snapshot["apps"]["demo"]["publication_status"], "published")
        self.assertEqual(snapshot["apps"]["demo"]["store_label"], "Demo Store Name")
        self.assertEqual(snapshot["apps"]["demo"]["upstream_repo"], "owner/demo")

    def test_build_status_snapshot_keeps_unpublished_in_progress_state(self) -> None:
        repo_root = self.make_repo_root()
        self.write_manifest(repo_root, "demo", "fun.selfstudio.app.migration.owner.demo", "Demo")
        self.write_registry(repo_root, "demo", "owner/demo", "in_progress")
        self.write_developer_apps(repo_root, {})

        snapshot = build_status_snapshot(repo_root, generated_at="2026-04-26T00:00:00Z")

        self.assertEqual(snapshot["meta"]["published_count"], 0)
        self.assertEqual(snapshot["apps"]["demo"]["publication_status"], "in_progress")
        self.assertEqual(snapshot["apps"]["demo"]["migration_status"], "in_progress")

    def test_build_publication_index_matches_upstream_repo_case_insensitively(self) -> None:
        snapshot = {
            "apps": {
                "demo": {
                    "slug": "demo",
                    "package": "fun.selfstudio.app.migration.owner.demo",
                    "upstream_repo": "Owner/Demo",
                    "publication_status": "published",
                }
            }
        }

        index = build_publication_index(snapshot)

        self.assertEqual(index["by_upstream_repo"]["owner/demo"]["slug"], "demo")

    def test_write_status_snapshot_writes_local_publication_status(self) -> None:
        repo_root = self.make_repo_root()
        package = "fun.selfstudio.app.migration.owner.demo"
        self.write_manifest(repo_root, "demo", package, "Demo")
        self.write_registry(repo_root, "demo", "owner/demo", "migrated")
        self.write_developer_apps(repo_root, {package: "Demo"})

        output_path = write_status_snapshot(repo_root, generated_at="2026-04-26T00:00:00Z")

        self.assertEqual(output_path, repo_root / "registry" / "status" / "local-publication-status.json")
        payload = json.loads(output_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["apps"]["demo"]["publication_status"], "published")


if __name__ == "__main__":
    unittest.main()
