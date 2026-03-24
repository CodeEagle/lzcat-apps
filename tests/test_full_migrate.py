from __future__ import annotations

import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "full_migrate.py"


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
        manifest = (repo_root / "apps" / source_repo.name / "lzc-manifest.yml").read_text(encoding="utf-8")
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


if __name__ == "__main__":
    unittest.main()
