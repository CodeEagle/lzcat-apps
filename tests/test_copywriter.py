from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.copywriter import build_copywriting_package, write_copywriting_package


class CopywriterTest(unittest.TestCase):
    def make_repo_root(self) -> Path:
        repo_root = Path(tempfile.mkdtemp(prefix="copywriter-test-"))
        app_root = repo_root / "apps" / "demo"
        app_root.mkdir(parents=True)
        (app_root / "lzc-manifest.yml").write_text(
            "\n".join(
                [
                    "package: fun.selfstudio.app.migration.demo",
                    "version: 1.2.3",
                    "name: Demo App",
                    "description: Convert files into useful output",
                    "homepage: https://github.com/owner/demo",
                    "locales:",
                    "  zh:",
                    "    description: 把文件转换成有用结果",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        (app_root / "README.md").write_text(
            "# Demo App\n\n## 功能特性\n\n- Browser workflow\n- API workflow\n",
            encoding="utf-8",
        )
        (app_root / "acceptance").mkdir()
        (app_root / "acceptance" / "browser-use-result.json").write_text(
            json.dumps(
                {
                    "status": "pass",
                    "entry_url": "https://demo.box.example",
                    "browser_use": {
                        "dom_rendered": True,
                        "console_errors": [],
                        "network_failures": [],
                    },
                    "blocking_issues": [],
                    "checks": [{"name": "open_home", "evidence": "Primary workflow passed."}],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return repo_root

    def test_build_copywriting_package_requires_browser_acceptance(self) -> None:
        repo_root = self.make_repo_root()

        package = build_copywriting_package(repo_root, "demo")

        self.assertIn("Demo App", package["store_copy"])
        self.assertIn("收益素材清单", package["store_copy"])
        self.assertIn("第一条任务", package["tutorial"])
        self.assertIn("执行中", package["tutorial"])
        self.assertIn("使用心得", package["playground"])
        self.assertNotIn("验收记录", package["tutorial"])
        self.assertNotIn("本次功能测试记录", package["tutorial"])
        self.assertNotIn("上架收益提示", package["tutorial"])
        self.assertNotIn("Browser Use", package["tutorial"])
        self.assertNotIn("提交审核", package["tutorial"])
        self.assertNotIn("本次功能测试记录", package["playground"])
        self.assertNotIn("Browser Use", package["playground"])
        self.assertNotIn("发布注意事项", package["playground"])
        self.assertIn("![应用界面]", package["playground"])
        self.assertIn("../acceptance/demo-home.png", package["playground"])

    def test_playground_guide_prefers_copywriting_assets(self) -> None:
        repo_root = self.make_repo_root()
        assets_dir = repo_root / "apps" / "demo" / "copywriting" / "assets"
        assets_dir.mkdir(parents=True)
        (assets_dir / "tutorial-01-home.png").write_bytes(b"png")

        package = build_copywriting_package(repo_root, "demo")

        self.assertIn("assets/tutorial-01-home.png", package["playground"])

    def test_build_copywriting_package_blocks_without_acceptance(self) -> None:
        repo_root = self.make_repo_root()
        (repo_root / "apps" / "demo" / "acceptance" / "browser-use-result.json").unlink()

        with self.assertRaises(ValueError):
            build_copywriting_package(repo_root, "demo")

    def test_write_copywriting_package_outputs_store_copy_and_tutorial(self) -> None:
        repo_root = self.make_repo_root()

        paths = write_copywriting_package(repo_root, "demo")

        self.assertTrue(paths["store_copy"].exists())
        self.assertTrue(paths["tutorial"].exists())
        self.assertTrue(paths["playground"].exists())
        self.assertIn("Demo App", paths["store_copy"].read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
