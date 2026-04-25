from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.browser_acceptance_plan import build_acceptance_plan


class BrowserAcceptancePlanTest(unittest.TestCase):
    def test_builds_plan_from_manifest_and_box_domain(self) -> None:
        repo_root = Path(tempfile.mkdtemp(prefix="browser-plan-test-"))
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

        plan = build_acceptance_plan(repo_root, "demo", box_domain="box.heiyu.space")

        self.assertEqual(plan["slug"], "demo")
        self.assertEqual(plan["package"], "fun.selfstudio.app.migration.demo")
        self.assertEqual(plan["entry_url"], "https://demo.box.heiyu.space")
        self.assertEqual(plan["evidence_dir"], "apps/demo/acceptance")
        self.assertEqual(plan["checks"][0]["name"], "open_home")

    def test_falls_back_to_slug_when_manifest_has_no_subdomain(self) -> None:
        repo_root = Path(tempfile.mkdtemp(prefix="browser-plan-test-"))
        app_dir = repo_root / "apps" / "demo"
        app_dir.mkdir(parents=True)
        (app_dir / "lzc-manifest.yml").write_text(
            "\n".join(
                [
                    "package: fun.selfstudio.app.migration.demo",
                    "name: Demo",
                    "application:",
                    "  routes:",
                    "    - /=http://demo:3000/",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        plan = build_acceptance_plan(repo_root, "demo", box_domain="box.heiyu.space")

        self.assertEqual(plan["entry_url"], "https://demo.box.heiyu.space")


if __name__ == "__main__":
    unittest.main()
