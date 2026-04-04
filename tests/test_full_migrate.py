from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "full_migrate.py"
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import bootstrap_migration as bm
import full_migrate as fm


def normalize_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    return re.sub(r"-{2,}", "-", slug).strip("-")


class FullMigrateTest(unittest.TestCase):
    def make_repo_root(self) -> Path:
        temp_dir = Path(tempfile.mkdtemp(prefix="lzcat-full-migrate-test-"))
        (temp_dir / "apps").mkdir(parents=True, exist_ok=True)
        (temp_dir / "registry" / "repos").mkdir(parents=True, exist_ok=True)
        (temp_dir / "registry" / "repos" / "index.json").write_text('{"repos":[]}\n', encoding="utf-8")
        return temp_dir

    def make_source_repo_with_compose(self) -> Path:
        temp_dir = Path(tempfile.mkdtemp(prefix="lzcat-source-compose-"))
        (temp_dir / "docker-compose.yml").write_text(
            """
services:
  web:
    image: ghcr.io/example/web:1.2.3
    ports:
      - "3000:3000"
    environment:
      OPENAI_API_KEY: ${OPENAI_API_KEY}
    volumes:
      - ./data:/app/data
    depends_on:
      - redis
  redis:
    image: redis:7
    volumes:
      - redis-data:/data
volumes:
  redis-data:
""".strip()
            + "\n",
            encoding="utf-8",
        )
        (temp_dir / ".env.example").write_text("OPENAI_API_KEY=\n", encoding="utf-8")
        (temp_dir / "README.md").write_text("# Compose App\n", encoding="utf-8")
        return temp_dir

    def make_source_repo_with_multi_build_compose(self) -> Path:
        temp_dir = Path(tempfile.mkdtemp(prefix="lzcat-source-multi-build-"))
        (temp_dir / "docker-compose.yml").write_text(
            """
services:
  backend:
    build:
      context: ./backend
    ports:
      - "8000:8000"
    volumes:
      - backend_data:/app/data
  frontend:
    build:
      context: ./frontend
    ports:
      - "3000:3000"
    depends_on:
      - backend
volumes:
  backend_data:
""".strip()
            + "\n",
            encoding="utf-8",
        )
        (temp_dir / "backend").mkdir(parents=True, exist_ok=True)
        (temp_dir / "frontend").mkdir(parents=True, exist_ok=True)
        (temp_dir / "backend" / "Dockerfile").write_text("FROM python:3.11-slim\nCOPY . /app\nEXPOSE 8000\n", encoding="utf-8")
        (temp_dir / "frontend" / "Dockerfile").write_text("FROM node:20-alpine\nCOPY . /app\nEXPOSE 3000\n", encoding="utf-8")
        (temp_dir / "README.md").write_text("# Multi Build App\n", encoding="utf-8")
        return temp_dir

    def make_source_repo_with_dockerfile(self) -> Path:
        temp_dir = Path(tempfile.mkdtemp(prefix="lzcat-source-dockerfile-"))
        (temp_dir / "Dockerfile").write_text(
            """
FROM python:3.11-slim
WORKDIR /app
COPY . /app
EXPOSE 8088
VOLUME ["/app/data"]
HEALTHCHECK CMD curl -f http://127.0.0.1:8088/health || exit 1
CMD ["python", "-m", "http.server", "8088"]
""".strip()
            + "\n",
            encoding="utf-8",
        )
        (temp_dir / ".env.example").write_text("API_TOKEN=\n", encoding="utf-8")
        return temp_dir

    def make_source_repo_with_unversioned_image_and_local_dockerfiles(self) -> Path:
        temp_dir = Path(tempfile.mkdtemp(prefix="lzcat-source-local-dockerfiles-"))
        (temp_dir / "docker-compose.yml").write_text(
            """
services:
  api:
    image: acme/example-api
    environment:
      DB_USER: ${POSTGRES_USER}
      DB_PASSWORD: ${POSTGRES_PWD}
  frontend:
    image: acme/example-frontend
    environment:
      API_URL: ${PUBLIC_API_URL}
      DEMO_LINK: ${DEMO_LINK:- }
    ports:
      - "3000:3000"
    depends_on:
      - api
""".strip()
            + "\n",
            encoding="utf-8",
        )
        (temp_dir / "api").mkdir(parents=True, exist_ok=True)
        (temp_dir / "frontend").mkdir(parents=True, exist_ok=True)
        (temp_dir / "api" / "Dockerfile").write_text("FROM python:3.11-slim\n", encoding="utf-8")
        (temp_dir / "frontend" / "Dockerfile").write_text("FROM node:20-alpine\n", encoding="utf-8")
        return temp_dir

    def make_native_desktop_repo_with_platform_dockerfiles(self) -> Path:
        temp_dir = Path(tempfile.mkdtemp(prefix="lzcat-native-desktop-"))
        (temp_dir / "CMakeLists.txt").write_text("cmake_minimum_required(VERSION 3.16)\nproject(native-client)\n", encoding="utf-8")
        (temp_dir / "xmake.lua").write_text("target('native-client')\n", encoding="utf-8")
        (temp_dir / "README.md").write_text(
            """
# Native Client

一个支持 Windows、macOS、Linux 和 Nintendo Switch 的 PC client。
支持 gamepad、touch、mouse 和 keyboard 操作。
""".strip()
            + "\n",
            encoding="utf-8",
        )
        (temp_dir / "scripts" / "ps4").mkdir(parents=True, exist_ok=True)
        (temp_dir / "scripts" / "ps4" / "Dockerfile").write_text(
            "FROM alpine:3.20\nRUN echo ps4-toolchain\n",
            encoding="utf-8",
        )
        return temp_dir

    def run_script(self, repo_root: Path, source: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "python3",
                str(SCRIPT),
                str(source),
                "--repo-root",
                str(repo_root),
                "--no-build",
            ],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_compose_repo_runs_to_preflight(self) -> None:
        repo_root = self.make_repo_root()
        source_repo = self.make_source_repo_with_compose()
        result = self.run_script(repo_root, source_repo)
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("[7/10] 运行预检", result.stdout)
        slug = normalize_slug(source_repo.name)
        config = json.loads((repo_root / "registry" / "repos" / f"{slug}.json").read_text(encoding="utf-8"))
        manifest = (repo_root / "apps" / slug / "lzc-manifest.yml").read_text(encoding="utf-8")
        self.assertEqual(config["build_strategy"], "official_image")
        self.assertIn("backend: http://web:3000/", manifest)
        self.assertIn("OPENAI_API_KEY", manifest)

    def test_dockerfile_repo_runs_to_preflight(self) -> None:
        repo_root = self.make_repo_root()
        source_repo = self.make_source_repo_with_dockerfile()
        result = self.run_script(repo_root, source_repo)
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        slug = normalize_slug(source_repo.name)
        config = json.loads((repo_root / "registry" / "repos" / f"{slug}.json").read_text(encoding="utf-8"))
        manifest = (repo_root / "apps" / slug / "lzc-manifest.yml").read_text(encoding="utf-8")
        self.assertEqual(config["build_strategy"], "upstream_dockerfile")
        self.assertIn("backend: http://", manifest)
        self.assertIn("8088", manifest)

    def test_multi_build_compose_records_service_builds(self) -> None:
        repo_root = self.make_repo_root()
        source_repo = self.make_source_repo_with_multi_build_compose()
        result = self.run_script(repo_root, source_repo)
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        slug = normalize_slug(source_repo.name)
        config = json.loads((repo_root / "registry" / "repos" / f"{slug}.json").read_text(encoding="utf-8"))
        manifest = (repo_root / "apps" / slug / "lzc-manifest.yml").read_text(encoding="utf-8")
        self.assertEqual(config["build_strategy"], "upstream_dockerfile")
        self.assertEqual(sorted(item["target_service"] for item in config["service_builds"]), ["backend", "frontend"])
        self.assertIn('"image_name":', json.dumps(config))
        self.assertIn("backend: http://frontend:3000/", manifest)

    def test_unversioned_images_with_local_dockerfiles_become_service_builds(self) -> None:
        repo_root = self.make_repo_root()
        source_repo = self.make_source_repo_with_unversioned_image_and_local_dockerfiles()
        result = self.run_script(repo_root, source_repo)
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        slug = normalize_slug(source_repo.name)
        config = json.loads((repo_root / "registry" / "repos" / f"{slug}.json").read_text(encoding="utf-8"))
        manifest = (repo_root / "apps" / slug / "lzc-manifest.yml").read_text(encoding="utf-8")
        self.assertEqual(config["build_strategy"], "upstream_dockerfile")
        self.assertEqual(sorted(item["target_service"] for item in config["service_builds"]), ["api", "frontend"])
        self.assertIn("DB_USER=${POSTGRES_USER}", manifest)
        self.assertIn("DB_PASSWORD=${POSTGRES_PWD}", manifest)
        self.assertIn(f"API_URL=https://{slug}.${{LAZYCAT_BOX_DOMAIN}}/api", manifest)
        self.assertIn("DEMO_LINK=", manifest)

    def test_rerun_same_target_overwrites_managed_files(self) -> None:
        repo_root = self.make_repo_root()
        source_repo = self.make_source_repo_with_dockerfile()
        first = self.run_script(repo_root, source_repo)
        second = self.run_script(repo_root, source_repo)
        self.assertEqual(first.returncode, 0, msg=first.stderr)
        self.assertEqual(second.returncode, 0, msg=second.stderr)

    def test_native_desktop_repo_with_platform_dockerfile_is_rejected(self) -> None:
        repo_root = self.make_repo_root()
        source_repo = self.make_native_desktop_repo_with_platform_dockerfiles()
        result = self.run_script(repo_root, source_repo)
        slug = normalize_slug(source_repo.name)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("原生客户端/桌面应用", result.stdout)
        self.assertFalse((repo_root / "apps" / slug).exists())
        self.assertFalse((repo_root / "registry" / "repos" / f"{slug}.json").exists())

    def test_preflight_flags_heredoc_in_command(self) -> None:
        repo_root = self.make_repo_root()
        app_dir = repo_root / "apps" / "bad-app"
        app_dir.mkdir(parents=True, exist_ok=True)
        (repo_root / "registry" / "repos" / "bad-app.json").write_text(
            json.dumps(
                {
                    "enabled": True,
                    "upstream_repo": "acme/bad-app",
                    "check_strategy": "github_release",
                    "build_strategy": "official_image",
                    "official_image_registry": "ghcr.io/acme/bad-app",
                    "service_port": 8080,
                    "service_cmd": [],
                    "image_targets": ["bad-app"],
                    "dependencies": [],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (app_dir / "lzc-manifest.yml").write_text(
            "\n".join(
                [
                    "lzc-sdk-version: '0.1'",
                    "package: fun.selfstudio.app.migration.bad-app",
                    "version: 1.0.0",
                    "min_os_version: 1.3.8",
                    "name: Bad App",
                    "description: bad app",
                    "license: MIT",
                    "homepage: https://example.com/bad-app",
                    "author: Acme",
                    "application:",
                    "  subdomain: bad-app",
                    "  public_path:",
                    "    - /",
                    "  upstreams:",
                    "    -",
                    "      location: /",
                    "      backend: http://bad-app:8080/",
                    "services:",
                    "  bad-app:",
                    "    image: registry.lazycat.cloud/placeholder/bad-app:latest",
                    "    command: |",
                    "      sh -lc 'cat <<EOF > /tmp/config",
                    "      hello",
                    "      EOF",
                    "      exec app'",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        (app_dir / "lzc-build.yml").write_text("lzc-sdk-version: '0.1'\nmanifest: ./lzc-manifest.yml\npkgout: ./\nicon: ./icon.png\n", encoding="utf-8")
        (app_dir / "README.md").write_text("# Bad App\n", encoding="utf-8")
        (app_dir / "icon.png").write_bytes(b"png")

        ok, issues = fm.preflight_check(repo_root, "bad-app")
        self.assertFalse(ok)
        self.assertTrue(any("heredoc syntax" in issue for issue in issues), issues)


if __name__ == "__main__":
    unittest.main()
