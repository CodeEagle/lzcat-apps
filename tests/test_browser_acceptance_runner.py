from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.browser_acceptance_runner import (
    classify_dom,
    detect_platform_error,
    write_result,
)


class DetectPlatformErrorTest(unittest.TestCase):
    def test_returns_marker_when_present(self) -> None:
        self.assertEqual(detect_platform_error("应用未启动 please retry"), "应用未启动")

    def test_case_insensitive_for_english_markers(self) -> None:
        self.assertEqual(
            detect_platform_error("page contains: 502 BAD GATEWAY here"),
            "502 Bad Gateway",
        )

    def test_returns_none_when_clean(self) -> None:
        self.assertIsNone(detect_platform_error("Welcome to the App. Click Login to continue."))

    def test_empty_returns_none(self) -> None:
        self.assertIsNone(detect_platform_error(""))


class ClassifyDomTest(unittest.TestCase):
    def test_blank_body_marked_blocking(self) -> None:
        ok, issues = classify_dom("", "<html><body></body></html>")
        self.assertFalse(ok)
        self.assertTrue(any("blank body" in i for i in issues))

    def test_real_content_passes(self) -> None:
        body = "Welcome to MyApp. Your dashboard awaits, " + "x" * 100
        ok, issues = classify_dom(body, f"<html><body>{body}</body></html>")
        self.assertTrue(ok)
        self.assertEqual(issues, [])

    def test_platform_error_marker_blocks(self) -> None:
        body = "Long enough body text " + "y" * 200 + " 应用未启动"
        ok, issues = classify_dom(body, f"<html><body>{body}</body></html>")
        self.assertFalse(ok)
        self.assertTrue(any("platform error" in i for i in issues))

    def test_unclosed_body_blocks(self) -> None:
        body = "Some real text here " + "x" * 100
        ok, issues = classify_dom(body, f"<html><body>{body}")
        self.assertFalse(ok)
        self.assertTrue(any("never closed" in i for i in issues))


class WriteResultTest(unittest.TestCase):
    def test_writes_acceptance_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "apps" / "demo").mkdir(parents=True)
            payload = {
                "status": "pass",
                "blocking_issues": [],
                "browser_use": {"dom_rendered": True, "console_errors": [], "network_failures": []},
                "checks": [],
                "screenshots": [],
            }
            path = write_result(root, "demo", payload)
            self.assertEqual(path, root / "apps" / "demo" / ".browser-acceptance.json")
            self.assertTrue(path.exists())
            saved = json.loads(path.read_text())
            self.assertEqual(saved["status"], "pass")


class FunctionalCheckerContractTest(unittest.TestCase):
    """Verify the runner output matches what functional_checker reads."""

    def test_runner_output_classifies_browser_pass(self) -> None:
        from scripts.functional_checker import classify_acceptance

        payload = {
            "status": "pass",
            "blocking_issues": [],
            "browser_use": {
                "dom_rendered": True,
                "console_errors": [],
                "network_failures": [],
            },
        }
        self.assertEqual(classify_acceptance(payload), "browser_pass")

    def test_runner_output_classifies_browser_failed_on_blocking(self) -> None:
        from scripts.functional_checker import classify_acceptance

        payload = {
            "status": "pass",
            "blocking_issues": ["platform error"],
            "browser_use": {
                "dom_rendered": True,
                "console_errors": [],
                "network_failures": [],
            },
        }
        self.assertEqual(classify_acceptance(payload), "browser_failed")

    def test_runner_output_classifies_browser_failed_on_console_errors(self) -> None:
        from scripts.functional_checker import classify_acceptance

        payload = {
            "status": "pass",
            "blocking_issues": [],
            "browser_use": {
                "dom_rendered": True,
                "console_errors": ["error: undefined is not a function"],
                "network_failures": [],
            },
        }
        self.assertEqual(classify_acceptance(payload), "browser_failed")


if __name__ == "__main__":
    unittest.main()
