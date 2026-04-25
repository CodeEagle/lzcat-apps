from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.record_browser_acceptance import build_acceptance_payload


class RecordBrowserAcceptanceTest(unittest.TestCase):
    def test_build_acceptance_payload_records_blocking_issues(self) -> None:
        payload = build_acceptance_payload(
            slug="demo",
            status="fail",
            entry_url="https://demo.box.heiyu.space",
            evidence="API returned 404",
            blocking_issues=["API returned 404"],
            console_errors=["GET /api/config 404"],
            network_failures=[],
            screenshots=["apps/demo/acceptance/home.png"],
            accepted_at="2026-04-25T00:00:00Z",
        )

        self.assertEqual(payload["status"], "fail")
        self.assertEqual(payload["blocking_issues"][0]["summary"], "API returned 404")
        self.assertFalse(payload["browser_use"]["dom_rendered"])
        self.assertEqual(payload["browser_use"]["console_errors"], ["GET /api/config 404"])


if __name__ == "__main__":
    unittest.main()
