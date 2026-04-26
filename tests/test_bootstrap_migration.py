from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "bootstrap_migration.py"
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import bootstrap_migration as bm


def fake_png(width: int = 256, height: int = 256) -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        + (13).to_bytes(4, "big")
        + b"IHDR"
        + width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
        + b"\x08\x06\x00\x00\x00"
        + b"\x00\x00\x00\x00"
    )


class BootstrapMigrationTest(unittest.TestCase):
    def make_repo_root(self) -> Path:
        temp_dir = Path(tempfile.mkdtemp(prefix="lzcat-bootstrap-test-"))
        (temp_dir / "apps").mkdir(parents=True, exist_ok=True)
        (temp_dir / "registry" / "repos").mkdir(parents=True, exist_ok=True)
        (temp_dir / "registry" / "repos" / "index.json").write_text('{"repos":[]}\n', encoding="utf-8")
        return temp_dir

    def run_script(self, repo_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "python3",
                str(SCRIPT),
                "--repo-root",
                str(repo_root),
                *args,
            ],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_cli_scaffold_single_service(self) -> None:
        repo_root = self.make_repo_root()
        result = self.run_script(
            repo_root,
            "--slug",
            "demo-app",
            "--project-name",
            "Demo App",
            "--upstream-repo",
            "acme/demo-app",
            "--description",
            "Demo app for scaffold test",
            "--description-zh",
            "用于脚手架测试的 Demo 应用",
            "--homepage",
            "https://example.com/demo-app",
            "--license",
            "MIT",
            "--author",
            "Acme",
            "--version",
            "1.2.3",
            "--build-strategy",
            "official_image",
            "--official-image-registry",
            "ghcr.io/acme/demo-app",
            "--service-port",
            "8080",
            "--env",
            "OPENAI_API_KEY",
            "--data-path",
            "/lzcapp/var/data/demo-app:/app/data",
            "--startup-note",
            "Create the first admin account after install",
            "--no-fetch-upstream",
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        manifest = (repo_root / "apps" / "demo-app" / "lzc-manifest.yml").read_text(encoding="utf-8")
        config = json.loads((repo_root / "registry" / "repos" / "demo-app.json").read_text(encoding="utf-8"))
        index = json.loads((repo_root / "registry" / "repos" / "index.json").read_text(encoding="utf-8"))

        self.assertIn("package: fun.selfstudio.app.migration.demo-app", manifest)
        self.assertIn("backend: http://demo-app:8080/", manifest)
        self.assertIn("OPENAI_API_KEY", manifest)
        self.assertEqual(config["build_strategy"], "official_image")
        self.assertEqual(config["official_image_registry"], "ghcr.io/acme/demo-app")
        self.assertIn("demo-app.json", index["repos"])

    def test_spec_scaffold_multi_service_with_content(self) -> None:
        repo_root = self.make_repo_root()
        spec_path = repo_root / "spec.json"
        spec_path.write_text(
            json.dumps(
                {
                    "slug": "stack-app",
                    "project_name": "Stack App",
                    "upstream_repo": "acme/stack-app",
                    "description": "Stack app scaffold",
                    "description_zh": "多服务脚手架示例",
                    "homepage": "https://example.com/stack-app",
                    "license": "Apache-2.0",
                    "author": "Acme",
                    "version": "2.0.0",
                    "check_strategy": "github_tag",
                    "build_strategy": "official_image",
                    "official_image_registry": "docker.io/acme/stack-app",
                    "service_port": 3000,
                    "image_targets": ["web", "api"],
                    "env_vars": [
                        {
                            "name": "API_KEY",
                            "required": True,
                            "description": "API key"
                        }
                    ],
                    "data_paths": [
                        {
                            "host": "/lzcapp/var/data/stack-app",
                            "container": "/data",
                            "description": "Application data"
                        }
                    ],
                    "startup_notes": [
                        "Seed the initial admin account after first start"
                    ],
                    "application": {
                        "subdomain": "stack-app",
                        "routes": [
                            "/=file:///lzcapp/pkg/content/home"
                        ],
                        "public_path": ["/", "/api/"],
                        "upstreams": [
                            {
                                "location": "/api/",
                                "backend": "http://api:8080/api/"
                            },
                            {
                                "location": "/",
                                "backend": "http://web:3000/"
                            }
                        ]
                    },
                    "services": {
                        "web": {
                            "image": "registry.lazycat.cloud/placeholder/stack-app:web",
                            "depends_on": ["api"],
                            "environment": ["NODE_ENV=production"]
                        },
                        "api": {
                            "image": "registry.lazycat.cloud/placeholder/stack-app:api",
                            "environment": ["API_KEY"],
                            "binds": ["/lzcapp/var/data/stack-app:/data"],
                            "healthcheck": {
                                "test": [
                                    "CMD-SHELL",
                                    "curl -f http://127.0.0.1:8080/health >/dev/null || exit 1"
                                ],
                                "interval": "30s",
                                "timeout": "10s",
                                "retries": 5
                            }
                        }
                    },
                    "include_content": True
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        result = self.run_script(
            repo_root,
            "--spec",
            str(spec_path),
            "--no-fetch-upstream",
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        manifest = (repo_root / "apps" / "stack-app" / "lzc-manifest.yml").read_text(encoding="utf-8")
        build_yml = (repo_root / "apps" / "stack-app" / "lzc-build.yml").read_text(encoding="utf-8")
        checklist = (repo_root / "apps" / "stack-app" / "UPSTREAM_DEPLOYMENT_CHECKLIST.md").read_text(encoding="utf-8")

        self.assertIn("location: /api/", manifest)
        self.assertIn("backend: http://web:3000/", manifest)
        self.assertIn("healthcheck:", manifest)
        self.assertIn("contentdir: ./content", build_yml)
        self.assertTrue((repo_root / "apps" / "stack-app" / "content" / "README.md").exists())
        self.assertIn("PROJECT_SLUG: stack-app", checklist)

    def test_rejects_heredoc_in_command(self) -> None:
        repo_root = self.make_repo_root()
        result = self.run_script(
            repo_root,
            "--slug",
            "bad-command-app",
            "--project-name",
            "Bad Command App",
            "--upstream-repo",
            "acme/bad-command-app",
            "--description",
            "App with heredoc in command",
            "--homepage",
            "https://example.com/bad-command-app",
            "--license",
            "MIT",
            "--author",
            "Acme",
            "--version",
            "1.0.0",
            "--build-strategy",
            "official_image",
            "--official-image-registry",
            "ghcr.io/acme/bad-command-app",
            "--service-port",
            "8080",
            "--command",
            "sh -lc 'cat <<EOF > /tmp/config\nhello\nEOF\nexec app'",
            "--no-fetch-upstream",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must not use heredoc syntax", result.stderr)

    def test_discovers_repo_icon_from_docs_directory(self) -> None:
        source_repo = Path(tempfile.mkdtemp(prefix="lzcat-icon-source-"))
        (source_repo / "docs").mkdir(parents=True, exist_ok=True)
        icon_path = source_repo / "docs" / "icon-256.png"
        icon_path.write_bytes(fake_png(256, 256))
        (source_repo / "public").mkdir(parents=True, exist_ok=True)
        (source_repo / "public" / "logo-small.png").write_bytes(fake_png(64, 64))

        self.assertEqual(bm.discover_repo_icon(source_repo), icon_path)

    def test_prefers_primary_icon_over_web_touch_icon(self) -> None:
        source_repo = Path(tempfile.mkdtemp(prefix="lzcat-touch-icon-source-"))
        (source_repo / "docs").mkdir(parents=True, exist_ok=True)
        icon_path = source_repo / "docs" / "icon-256.png"
        icon_path.write_bytes(fake_png(256, 256))
        (source_repo / "runtime" / "web" / "static").mkdir(parents=True, exist_ok=True)
        touch_icon = source_repo / "runtime" / "web" / "static" / "apple-touch-icon.png"
        touch_icon.write_bytes(fake_png(180, 180))
        web_icon = source_repo / "runtime" / "web" / "static" / "icon-512.png"
        web_icon.write_bytes(fake_png(512, 512))

        self.assertEqual(bm.discover_repo_icon(source_repo), icon_path)

    def test_discovers_repo_logo_when_icon_name_is_absent(self) -> None:
        source_repo = Path(tempfile.mkdtemp(prefix="lzcat-logo-source-"))
        (source_repo / "assets").mkdir(parents=True, exist_ok=True)
        logo_path = source_repo / "assets" / "logo.png"
        logo_path.write_bytes(fake_png(512, 512))

        self.assertEqual(bm.discover_repo_icon(source_repo), logo_path)

    def test_discovers_repo_icon_from_github_assets(self) -> None:
        source_repo = Path(tempfile.mkdtemp(prefix="lzcat-github-icon-source-"))
        (source_repo / ".github" / "assets").mkdir(parents=True, exist_ok=True)
        icon_path = source_repo / ".github" / "assets" / "app-icon.png"
        icon_path.write_bytes(fake_png(256, 256))

        self.assertEqual(bm.discover_repo_icon(source_repo), icon_path)

    def test_build_registry_config_sorts_dict_lists_stably(self) -> None:
        spec = {
            "upstream_repo": "acme/helix-like",
            "check_strategy": "github_release",
            "build_strategy": "upstream_dockerfile",
            "publish_to_store": False,
            "official_image_registry": "",
            "precompiled_binary_url": "",
            "dockerfile_type": "dockerfile",
            "service_port": 8080,
            "service_cmd": [],
            "image_targets": [{"service": "web"}, {"service": "api"}],
            "dependencies": [],
            "service_builds": [
                {"target_service": "web", "dockerfile_path": "web/Dockerfile"},
                {"target_service": "api", "dockerfile_path": "api/Dockerfile"},
            ],
            "dockerfile_path": "Dockerfile",
            "build_context": ".",
            "overlay_paths": [],
            "upstream_submodules": [],
            "docker_platform": "",
            "image_owner": "",
            "build_args": {},
            "image_name": "",
            "official_image_fallback_tag": "",
            "repo": "",
            "deploy_param_sync": None,
            "migration_status": None,
        }

        config = bm.build_registry_config(spec)
        self.assertEqual([entry["service"] for entry in config["image_targets"]], ["api", "web"])
        self.assertEqual([entry["target_service"] for entry in config["service_builds"]], ["api", "web"])


if __name__ == "__main__":
    unittest.main()
