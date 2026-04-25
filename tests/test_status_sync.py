from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.status_sync import parse_developer_apps


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


if __name__ == "__main__":
    unittest.main()
