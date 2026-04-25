from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.run_build import browser_acceptance_allows_publish


class PublishGateTest(unittest.TestCase):
    def test_blocks_when_acceptance_missing(self) -> None:
        app_root = Path(tempfile.mkdtemp(prefix="publish-gate-test-"))

        allowed, reason = browser_acceptance_allows_publish(app_root)

        self.assertFalse(allowed)
        self.assertIn("missing Browser Use acceptance", reason)

    def test_allows_passing_acceptance(self) -> None:
        app_root = Path(tempfile.mkdtemp(prefix="publish-gate-test-"))
        acceptance_path = app_root / "acceptance" / "browser-use-result.json"
        acceptance_path.parent.mkdir(parents=True)
        acceptance_path.write_text(
            json.dumps(
                {
                    "status": "pass",
                    "blocking_issues": [],
                    "browser_use": {"dom_rendered": True, "console_errors": [], "network_failures": []},
                }
            )
            + "\n",
            encoding="utf-8",
        )

        allowed, reason = browser_acceptance_allows_publish(app_root)

        self.assertTrue(allowed)
        self.assertEqual(reason, "")

    def test_blocks_console_errors(self) -> None:
        app_root = Path(tempfile.mkdtemp(prefix="publish-gate-test-"))
        acceptance_path = app_root / "acceptance" / "browser-use-result.json"
        acceptance_path.parent.mkdir(parents=True)
        acceptance_path.write_text(
            json.dumps(
                {
                    "status": "pass",
                    "blocking_issues": [],
                    "browser_use": {"dom_rendered": True, "console_errors": ["boom"], "network_failures": []},
                }
            )
            + "\n",
            encoding="utf-8",
        )

        allowed, reason = browser_acceptance_allows_publish(app_root)

        self.assertFalse(allowed)
        self.assertIn("console errors", reason)


if __name__ == "__main__":
    unittest.main()
