from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.status_sync import developer_apps_api_url, parse_developer_apps, parse_developer_apps_api


class StatusSyncTest(unittest.TestCase):
    def test_parse_developer_apps_from_lazycat_links(self) -> None:
        content = """
        [MarkItDown](https://lazycat.cloud/appstore/detail/fun.selfstudio.app.migration.microsoft.markitdown-mcp)
        [Jellyfish](https://lazycat.cloud/appstore/detail/fun.selfstudio.app.migration.jellyfish)
        """

        apps = parse_developer_apps(content)

        self.assertEqual(
            apps,
            {
                "fun.selfstudio.app.migration.microsoft.markitdown-mcp": "MarkItDown",
                "fun.selfstudio.app.migration.jellyfish": "Jellyfish",
            },
        )

    def test_parse_developer_apps_ignores_duplicate_links(self) -> None:
        content = """
        [MarkItDown](https://lazycat.cloud/appstore/detail/fun.selfstudio.app.migration.microsoft.markitdown-mcp)
        [MarkItDown](https://lazycat.cloud/appstore/detail/fun.selfstudio.app.migration.microsoft.markitdown-mcp)
        """

        apps = parse_developer_apps(content)

        self.assertEqual(len(apps), 1)

    def test_parse_developer_apps_api_payload(self) -> None:
        payload = {
            "items": [
                {
                    "package": "fun.selfstudio.app.migration.hermes",
                    "information": {"name": "Hermes"},
                },
                {
                    "package": "fun.selfstudio.app.migration.crucix",
                    "information": {"name": "crucix"},
                },
            ]
        }

        apps = parse_developer_apps_api(payload)

        self.assertEqual(
            apps,
            {
                "fun.selfstudio.app.migration.hermes": "Hermes",
                "fun.selfstudio.app.migration.crucix": "crucix",
            },
        )

    def test_builds_developer_apps_api_url_from_page_url(self) -> None:
        self.assertEqual(
            developer_apps_api_url("https://lazycat.cloud/appstore/more/developers/178"),
            "https://appstore.api.lazycat.cloud/api/v3/user/developer/178/apps?size=100&page=0",
        )


if __name__ == "__main__":
    unittest.main()
