from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.functional_checker import acceptance_result_path, build_functional_check, classify_acceptance


class FunctionalCheckerTest(unittest.TestCase):
    def test_classify_acceptance_pass(self) -> None:
        result = {
            "status": "pass",
            "blocking_issues": [],
            "browser_use": {"dom_rendered": True, "console_errors": [], "network_failures": []},
        }

        self.assertEqual(classify_acceptance(result), "browser_pass")

    def test_classify_acceptance_failed_when_blocking_issues_exist(self) -> None:
        result = {
            "status": "pass",
            "blocking_issues": [{"category": "routing", "summary": "API 404"}],
            "browser_use": {"dom_rendered": True, "console_errors": [], "network_failures": []},
        }

        self.assertEqual(classify_acceptance(result), "browser_failed")

    def test_classify_acceptance_pending_without_result(self) -> None:
        self.assertEqual(classify_acceptance(None), "browser_pending")

    def test_classify_acceptance_failed_without_rendered_dom(self) -> None:
        result = {
            "status": "pass",
            "blocking_issues": [],
            "browser_use": {"dom_rendered": False, "console_errors": [], "network_failures": []},
        }

        self.assertEqual(classify_acceptance(result), "browser_failed")

    def test_build_functional_check_reads_plan_result_path(self) -> None:
        repo_root = Path(tempfile.mkdtemp(prefix="functional-check-test-"))
        app_dir = repo_root / "apps" / "demo"
        app_dir.mkdir(parents=True)
        (app_dir / "lzc-manifest.yml").write_text(
            "\n".join(
                [
                    "package: fun.selfstudio.app.migration.demo",
                    "name: Demo",
                    "application:",
                    "  subdomain: demo",
                    "  routes:",
                    "    - /=http://demo:3000/",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        result_path = repo_root / "apps" / "demo" / "acceptance" / "browser-use-result.json"
        result_path.parent.mkdir(parents=True)
        result_path.write_text(
            json.dumps(
                {
                    "status": "pass",
                    "blocking_issues": [],
                    "browser_use": {"dom_rendered": True, "console_errors": [], "network_failures": []},
                }
            ),
            encoding="utf-8",
        )

        output = build_functional_check(repo_root, "demo", box_domain="box.heiyu.space")

        self.assertEqual(acceptance_result_path(repo_root, output["browser_acceptance_plan"]), result_path)
        self.assertEqual(output["status"], "pass")
        self.assertEqual(output["browser_acceptance_status"], "browser_pass")


if __name__ == "__main__":
    unittest.main()
