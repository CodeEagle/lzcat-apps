from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.project_config import load_project_config


class ProjectConfigTest(unittest.TestCase):
    def test_loads_developer_apps_url(self) -> None:
        repo_root = Path(tempfile.mkdtemp(prefix="project-config-test-"))
        (repo_root / "project-config.json").write_text(
            json.dumps(
                {
                    "lazycat": {
                        "developer_apps_url": "https://lazycat.cloud/appstore/more/developers/178",
                        "developer_id": "178",
                        "status_sync": {
                            "enabled": True,
                            "source": "developer_apps_page",
                            "purpose": "Track apps already published by this developer and update migration status.",
                        },
                    }
                }
            )
            + "\n",
            encoding="utf-8",
        )

        config = load_project_config(repo_root)

        self.assertEqual(config.lazycat.developer_id, "178")
        self.assertEqual(
            config.lazycat.developer_apps_url,
            "https://lazycat.cloud/appstore/more/developers/178",
        )
        self.assertTrue(config.lazycat.status_sync_enabled)

    def test_loads_discord_and_migration_policy(self) -> None:
        repo_root = Path(tempfile.mkdtemp(prefix="project-config-test-"))
        (repo_root / "project-config.json").write_text(
            json.dumps(
                {
                    "migration": {
                        "template_branch": "template",
                        "workspace_root": "/tmp/lzcat-workspaces",
                        "codex_worker_model": "gpt-5.5",
                        "desktop_screenshots_required": 2,
                        "mobile_screenshots_required": 3,
                        "playground_required": True,
                    },
                    "discord": {
                        "enabled": True,
                        "guild_id": "123",
                        "category_id": "456",
                        "channel_prefix": "migration",
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )

        config = load_project_config(repo_root)

        self.assertEqual(config.migration.template_branch, "template")
        self.assertEqual(config.migration.workspace_root, "/tmp/lzcat-workspaces")
        self.assertEqual(config.migration.codex_worker_model, "gpt-5.5")
        self.assertEqual(config.migration.desktop_screenshots_required, 2)
        self.assertEqual(config.migration.mobile_screenshots_required, 3)
        self.assertTrue(config.migration.playground_required)
        self.assertTrue(config.discord.enabled)
        self.assertEqual(config.discord.guild_id, "123")
        self.assertEqual(config.discord.category_id, "456")
        self.assertEqual(config.discord.channel_prefix, "migration")

    def test_missing_file_uses_disabled_status_sync(self) -> None:
        repo_root = Path(tempfile.mkdtemp(prefix="project-config-test-"))

        config = load_project_config(repo_root)

        self.assertEqual(config.lazycat.developer_apps_url, "")
        self.assertFalse(config.lazycat.status_sync_enabled)
        self.assertEqual(config.migration.template_branch, "template")
        self.assertEqual(config.migration.codex_worker_model, "gpt-5.5")
        self.assertFalse(config.discord.enabled)


if __name__ == "__main__":
    unittest.main()
