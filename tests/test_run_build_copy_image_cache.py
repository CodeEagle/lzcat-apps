from __future__ import annotations

import unittest

from scripts.run_build import parse_my_images_output


class RunBuildCopyImageCacheTest(unittest.TestCase):
    def test_parse_my_images_output_extracts_source_to_lazycat_mapping(self) -> None:
        output = """
┌─────────┬───────────────────────┬──────────────────────────────────────────────────────────────┬────────────────────┐
│ (index) │ Source Image          │ Lazycat Image                                                │ Updated At         │
├─────────┼───────────────────────┼──────────────────────────────────────────────────────────────┼────────────────────┤
│ 0       │ 'memohai/web:0.6.3'   │ 'registry.lazycat.cloud/invokerlaw/memohai/web:5bc16d9be1' │ '4/4/2026, 2:21'   │
│ 1       │ 'postgres:18-alpine'  │ 'registry.lazycat.cloud/invokerlaw/library/postgres:abcd'  │ '4/4/2026, 2:20'   │
└─────────┴───────────────────────┴──────────────────────────────────────────────────────────────┴────────────────────┘
"""
        parsed = parse_my_images_output(output)
        self.assertEqual(
            parsed["memohai/web:0.6.3"],
            "registry.lazycat.cloud/invokerlaw/memohai/web:5bc16d9be1",
        )
        self.assertEqual(
            parsed["postgres:18-alpine"],
            "registry.lazycat.cloud/invokerlaw/library/postgres:abcd",
        )


if __name__ == "__main__":
    unittest.main()
