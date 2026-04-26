#!/usr/bin/env python3

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import textwrap
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib import error, request

import bootstrap_migration as bm
import migration_state as ms

try:
    import yaml
except ImportError:  # pragma: no cover - optional dependency fallback
    yaml = None

INFRA_KEYWORDS = {
    "db",
    "postgres",
    "postgresql",
    "mysql",
    "mariadb",
    "redis",
    "mongo",
    "mongodb",
    "clickhouse",
    "zookeeper",
    "kafka",
    "rabbitmq",
    "minio",
    "elasticsearch",
    "grafana",
    "prometheus",
    "vector",
    "otel",
    "jaeger",
    "tempo",
    "loki",
    "broker",
}

WEB_HINTS = ("web", "ui", "frontend", "app", "server", "api", "dashboard", "console")
GATEWAY_IMAGE_NAMES = {"nginx", "caddy", "traefik", "haproxy", "envoy"}
K8S_ENV_PREFIXES = ("K8S_", "KUBE_", "KUBERNETES_", "KUBECONFIG")
COMPOSE_FILENAMES = (
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
    "docker-compose.selfhost.yml",
    "docker-compose.selfhost.yaml",
    "compose.selfhost.yml",
    "compose.selfhost.yaml",
)
DEPLOY_COMPOSE_NAME_HINTS = (
    "selfhost",
    "self-host",
    "prod",
    "production",
    "deploy",
    "release",
    "stack",
)
DEV_COMPOSE_NAME_HINTS = ("dev", "develop", "development", "local", "override", "example", "sample", "test")
DEV_COMMAND_HINTS = (" dev", "vite", "webpack", "storybook", "hot-reload")
LOW_PRIORITY_DOCKERFILE_DIRS = {
    ".github",
    "ci",
    "contrib",
    "demo",
    "demos",
    "deploy",
    "deployment",
    "dev",
    "docker",
    "docs",
    "example",
    "examples",
    "hack",
    "packaging",
    "scripts",
    "test",
    "tests",
    "tools",
}
NATIVE_PLATFORM_HINTS = {
    "android",
    "desktop",
    "ios",
    "linux",
    "mac",
    "macos",
    "ns",
    "nintendo",
    "ps4",
    "ps5",
    "psv",
    "psvita",
    "switch",
    "uwp",
    "vita",
    "win",
    "windows",
    "winrt",
    "xbox",
}
NATIVE_ROOT_BUILD_FILES = {
    "CMakeLists.txt",
    "meson.build",
    "SConstruct",
    "xmake.lua",
}
NATIVE_README_HINTS = (
    "gamepad",
    "glfw",
    "handheld",
    "keyboard",
    "macos",
    "metal",
    "mouse",
    "nanovg",
    "nintendo switch",
    "open gl",
    "opengl",
    "pc client",
    "ps4",
    "psvita",
    "steam deck",
    "sdl",
    "touch",
    "vulkan",
    "windows",
    "xbox",
)
SERVICE_README_HINTS = (
    "docker compose",
    "docker run",
    "127.0.0.1",
    "localhost",
    "open http",
    "port ",
    "reverse proxy",
    "web ui",
)
SOURCE_BUILD_STRATEGIES = {
    "dockerfile",
    "upstream_dockerfile",
    "upstream_with_target_template",
}
DEFAULT_AIPOD_GATEWAY_IMAGE = "registry.lazycat.cloud/catdogai/caddy-aipod:65e058ce"
FRONTEND_HINT_DIRS = ("web", "frontend", "ui", "site", "app", "demo")
FRONTEND_GATEWAY_LOCATIONS = ("/api", "/ws", "/assets")
BOX_CONFIG_PATH = Path.home() / ".config" / "lazycat" / "box-config.json"
MAX_ICON_BYTES = 200 * 1024


@dataclass(frozen=True)
class NormalizedSource:
    kind: str
    source: str
    path: Path | None
    upstream_repo: str = ""
    homepage: str = ""


@dataclass
class FrontendAppInfo:
    app_root: Path
    install_root: Path
    package_manager: str
    runtime: str
    build_command: str
    service_port: int
    output_path: str
    startup_command: list[str]
    rationale: str


@dataclass
class AnalysisResult:
    slug: str
    route: str
    spec: dict[str, Any]
    compose_file: Path | None = None
    dockerfile: Path | None = None
    env_files: list[Path] = field(default_factory=list)
    readmes: list[Path] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)


@dataclass
class BuildExecutionResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str
    lpk_path: Path | None = None


@dataclass
class StepState:
    current_step: int = 1


@dataclass(frozen=True)
class ComposeProxyFrontendInfo:
    config_path: Path
    backend_services: tuple[str, ...]
    locations: tuple[str, ...]

BUILD_MODES = ("auto", "build", "install", "reinstall", "validate-only")


def sh(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
    env: dict[str, str] | None = None,
) -> str:
    result = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"command failed ({result.returncode}): {' '.join(cmd)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    return result.stdout.strip()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json_file(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def prepare_container_env(base_env: dict[str, str]) -> tuple[str | None, dict[str, str], callable]:
    if command_exists("docker"):
        return "docker", dict(base_env), lambda: None
    if command_exists("podman"):
        shim_root = Path(tempfile.mkdtemp(prefix="lzcat-docker-shim-"))
        shim = shim_root / "docker"
        shim.write_text("#!/usr/bin/env bash\nexec podman \"$@\"\n", encoding="utf-8")
        shim.chmod(0o755)
        env = dict(base_env)
        env["PATH"] = f"{shim_root}:{env.get('PATH', '')}"
        return "podman", env, lambda: shutil.rmtree(shim_root, ignore_errors=True)
    return None, dict(base_env), lambda: None


def step_report(
    step: int,
    title: str,
    *,
    conclusion: str,
    outputs: list[str] | None = None,
    cache: str = "无",
    scripts: list[str] | None = None,
    risks: list[str] | None = None,
    next_step: str = "无",
) -> None:
    print(f"[{step}/10] {title}\n")
    print(f"- 当前结论：{conclusion}")
    print(f"- 当前产出：{'; '.join(outputs or ['无'])}")
    print(f"- 镜像缓存：{cache}")
    print(f"- 调用脚本：{'; '.join(scripts or ['无'])}")
    print(f"- 阻塞/风险：{'; '.join(risks or ['无'])}")
    print(f"- 下一步：{next_step}\n")


def github_repo_exists(repo: str) -> bool:
    token = os.environ.get("GH_PAT") or os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    data = bm.github_api_json(f"repos/{repo}", token)
    return isinstance(data, dict) and bool(data.get("full_name"))


def parse_github_repo(source: str) -> str | None:
    github_match = re.search(r"github\.com/([^/]+)/([^/#?]+)", source)
    if github_match:
        owner = github_match.group(1)
        repo = github_match.group(2).removesuffix(".git")
        return f"{owner}/{repo}"
    shorthand = re.fullmatch(r"([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)", source.strip())
    if shorthand:
        candidate = f"{shorthand.group(1)}/{shorthand.group(2)}"
        if github_repo_exists(candidate):
            return candidate
    return None


def parse_raw_github_compose_url(source: str) -> str | None:
    match = re.search(r"raw\.githubusercontent\.com/([^/]+)/([^/]+)/[^/]+/(.+)", source)
    if match:
        return f"{match.group(1)}/{match.group(2)}"
    return None


def infer_local_git_upstream(path: Path) -> tuple[str, str]:
    if not (path / ".git").exists():
        return "", ""
    remote = sh(["git", "remote", "get-url", "origin"], cwd=path, check=False).strip()
    if not remote:
        return "", ""
    repo = parse_github_repo(remote) or parse_raw_github_compose_url(remote) or ""
    homepage = f"https://github.com/{repo}" if repo else ""
    return repo, homepage


def normalize_source(source: str) -> NormalizedSource:
    expanded = Path(source).expanduser()
    if expanded.exists() and expanded.is_dir():
        upstream_repo, homepage = infer_local_git_upstream(expanded.resolve())
        return NormalizedSource(
            kind="local_repo",
            source=source,
            path=expanded.resolve(),
            upstream_repo=upstream_repo,
            homepage=homepage,
        )

    github_repo = parse_github_repo(source)
    if github_repo:
        return NormalizedSource(
            kind="github_repo",
            source=source,
            path=None,
            upstream_repo=github_repo,
            homepage=f"https://github.com/{github_repo}",
        )

    if source.startswith(("http://", "https://")) and source.endswith((".yml", ".yaml")):
        upstream_repo = parse_raw_github_compose_url(source) or ""
        return NormalizedSource(
            kind="compose_url",
            source=source,
            path=None,
            upstream_repo=upstream_repo,
            homepage=f"https://github.com/{upstream_repo}" if upstream_repo else "",
        )

    return NormalizedSource(
        kind="docker_image",
        source=source,
        path=None,
    )


def fetch_text(url: str) -> str:
    req = request.Request(url, headers={"User-Agent": "lzcat-full-migrate"})
    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            with request.urlopen(req, timeout=30) as response:
                return response.read().decode("utf-8")
        except Exception as exc:
            last_error = exc
            if attempt < 4:
                time.sleep(attempt * 2)
    raise RuntimeError(f"Failed to fetch {url}: {last_error}") from last_error


def safe_tar_data_filter(member: tarfile.TarInfo, dest_path: str) -> tarfile.TarInfo | None:
    try:
        return tarfile.data_filter(member, dest_path)
    except tarfile.FilterError as exc:
        print(f"[archive] skipping unsafe member {member.name}: {exc}")
        return None


def download_github_archive(repo: str, dest_root: Path) -> Path:
    repo_meta = bm.github_api_json(f"repos/{repo}")
    default_branch = "main"
    if isinstance(repo_meta, dict):
        default_branch = str(repo_meta.get("default_branch") or default_branch)

    archive_url = f"https://codeload.github.com/{repo}/tar.gz/refs/heads/{default_branch}"
    archive_path = dest_root / f"{repo.replace('/', '-')}-{default_branch}.tar.gz"
    req = request.Request(archive_url, headers={"User-Agent": "lzcat-full-migrate"})
    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            if archive_path.exists():
                archive_path.unlink()
            with request.urlopen(req, timeout=180) as response, archive_path.open("wb") as handle:
                shutil.copyfileobj(response, handle)
            break
        except Exception as exc:
            last_error = exc
            if archive_path.exists():
                archive_path.unlink()
            if attempt < 3:
                time.sleep(attempt * 2)
    else:
        clone_dir = dest_root / repo.replace("/", "-")
        gh = shutil.which("gh")
        if gh:
            try:
                sh(["gh", "repo", "clone", repo, str(clone_dir), "--", "--depth", "1"], check=True)
                return clone_dir
            except Exception as exc:
                raise RuntimeError(
                    f"GitHub archive 下载失败，gh clone 兜底也失败：{repo}\n"
                    f"archive error: {last_error}\n"
                    f"clone error: {exc}"
                ) from exc
        raise RuntimeError(f"GitHub archive 下载失败：{repo}: {last_error}") from last_error

    with tarfile.open(archive_path, "r:gz") as tar:
        tar.extractall(dest_root, filter=safe_tar_data_filter)

    extracted_dirs = sorted(path for path in dest_root.iterdir() if path.is_dir())
    if not extracted_dirs:
        raise RuntimeError(f"未能从 GitHub archive 解出仓库目录：{repo}")
    repo_dir = extracted_dirs[0]

    # If repository contains submodules, prefer a proper git clone with submodules.
    try:
        if (repo_dir / ".gitmodules").exists():
            git = shutil.which("git")
            if git:
                clone_dir = dest_root / repo.replace("/", "-")
                try:
                    sh(["git", "clone", "--depth", "1", "--recurse-submodules", f"https://github.com/{repo}.git", str(clone_dir)], check=True)
                    return clone_dir
                except Exception:
                    # fall back to archive result
                    pass
    except Exception:
        # best-effort: ignore any errors and return archive dir
        pass

    return repo_dir


def prepare_source(normalized: NormalizedSource) -> tuple[Path | None, list[str], callable]:
    if normalized.kind == "local_repo":
        assert normalized.path is not None
        return normalized.path, [str(normalized.path)], lambda: None

    temp_root = Path(tempfile.mkdtemp(prefix="lzcat-full-migrate-"))
    outputs: list[str] = []

    if normalized.kind == "github_repo":
        repo_dir = download_github_archive(normalized.upstream_repo, temp_root)
        # If .gitmodules present in the extracted archive, attempt a full clone with submodules.
        try:
            if (repo_dir / ".gitmodules").exists():
                git = shutil.which("git")
                clone_dir = temp_root / normalized.upstream_repo.replace("/", "-")
                if git:
                    try:
                        sh(["git", "clone", "--depth", "1", "--recurse-submodules", f"https://github.com/{normalized.upstream_repo}.git", str(clone_dir)], check=True)
                        outputs.append(str(clone_dir))
                        return clone_dir, outputs, lambda: shutil.rmtree(temp_root, ignore_errors=True)
                    except Exception:
                        # keep archive result
                        pass
        except Exception:
            pass
        outputs.append(str(repo_dir))
        return repo_dir, outputs, lambda: shutil.rmtree(temp_root, ignore_errors=True)

    if normalized.kind == "compose_url":
        compose_name = Path(normalized.source).name or "compose.yml"
        compose_path = temp_root / compose_name
        compose_path.write_text(fetch_text(normalized.source), encoding="utf-8")
        outputs.append(str(compose_path))
        return temp_root, outputs, lambda: shutil.rmtree(temp_root, ignore_errors=True)

    return None, outputs, lambda: shutil.rmtree(temp_root, ignore_errors=True)


def select_compose_file(source_dir: Path) -> Path | None:
    candidates: list[Path] = []
    for name in COMPOSE_FILENAMES:
        candidates.extend(source_dir.rglob(name))
    if not candidates:
        return None
    return sorted(candidates, key=lambda p: (-compose_file_score(source_dir, p), str(p)))[0]


def compose_file_score(source_dir: Path, path: Path) -> int:
    try:
        relative = path.relative_to(source_dir)
    except ValueError:
        return -1000

    parts = [part.lower() for part in relative.parts]
    filename = path.name.lower()
    stem = path.stem.lower()
    score = 0

    score -= len(parts) * 10
    if len(parts) == 1:
        score += 40

    joined = "/".join(parts)
    for hint in DEPLOY_COMPOSE_NAME_HINTS:
        if hint in filename or hint in stem or hint in joined:
            score += 80
    for hint in DEV_COMPOSE_NAME_HINTS:
        if hint in filename or hint in stem or hint in joined:
            score -= 80

    if filename.startswith("docker-compose"):
        score += 10
    if filename in {"docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"}:
        score += 5

    return score


def select_dockerfile(source_dir: Path) -> Path | None:
    candidates = sorted(source_dir.rglob("Dockerfile"), key=lambda p: (dockerfile_score(source_dir, p), str(p)), reverse=True)
    if candidates:
        return candidates[0]
    containerfiles = sorted(source_dir.rglob("Containerfile"), key=lambda p: (dockerfile_score(source_dir, p), str(p)), reverse=True)
    if containerfiles:
        return containerfiles[0]
    return None


def dockerfile_score(source_dir: Path, path: Path) -> int:
    try:
        relative = path.relative_to(source_dir)
    except ValueError:
        return -1000

    parts = [part.lower() for part in relative.parts]
    score = 0
    depth = len(parts)

    score -= depth * 10
    if relative == Path("Dockerfile") or relative == Path("Containerfile"):
        score += 300
    if depth > 1 and parts[0] in LOW_PRIORITY_DOCKERFILE_DIRS:
        score -= 140
    if any(part in NATIVE_PLATFORM_HINTS for part in parts[:-1]):
        score -= 180
    if path.name != "Dockerfile":
        score -= 20

    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return score
    if re.search(r"(?im)^\s*EXPOSE\s+\d+", text):
        score += 30
    if re.search(r"(?im)^\s*(CMD|ENTRYPOINT)\b", text):
        score += 20
    if re.search(r"(?i)\b(nginx|caddy|apache|uvicorn|gunicorn|node|python -m http\.server)\b", text):
        score += 20
    return score


def list_env_files(source_dir: Path) -> list[Path]:
    names = (".env.example", ".env.sample", ".env.template", ".env")
    found: list[Path] = []
    for name in names:
        found.extend(source_dir.rglob(name))
    return sorted(found, key=lambda p: (len(p.relative_to(source_dir).parts), str(p)))


def list_readmes(source_dir: Path) -> list[Path]:
    return sorted(source_dir.rglob("README*"), key=lambda p: (len(p.relative_to(source_dir).parts), str(p)))


def list_package_json_files(source_dir: Path) -> list[Path]:
    candidates: list[Path] = []
    for path in source_dir.rglob("package.json"):
        try:
            relative = path.relative_to(source_dir)
        except ValueError:
            continue
        if "node_modules" in relative.parts:
            continue
        candidates.append(path)
    return sorted(candidates, key=lambda p: (len(p.relative_to(source_dir).parts), str(p)))


def load_json_file(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def detect_package_manager(source_dir: Path, app_root: Path) -> tuple[str, Path] | None:
    current = app_root
    while True:
        if (current / "pnpm-lock.yaml").exists() or (current / "pnpm-workspace.yaml").exists():
            return "pnpm", current
        if (current / "package-lock.json").exists():
            return "npm", current
        if (current / "yarn.lock").exists():
            return "yarn", current
        if current == source_dir:
            break
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


def score_frontend_candidate(source_dir: Path, package_json_path: Path, payload: dict[str, Any]) -> int:
    scripts = payload.get("scripts") if isinstance(payload.get("scripts"), dict) else {}
    build_script = str(scripts.get("build") or "").strip()
    if not build_script:
        return -1000
    score = 0
    rel = package_json_path.parent.relative_to(source_dir)
    if rel == Path("."):
        score += 30
    if any(part.lower() in FRONTEND_HINT_DIRS for part in rel.parts):
        score += 60
    if any(part.lower() in LOW_PRIORITY_DOCKERFILE_DIRS for part in rel.parts):
        score -= 80
    deps: dict[str, Any] = {}
    for key in ("dependencies", "devDependencies"):
        block = payload.get(key)
        if isinstance(block, dict):
            deps.update({str(name): value for name, value in block.items()})
    dep_names = set(deps)
    if "nitro" in dep_names or "vite" in dep_names or "astro" in dep_names or "next" in dep_names:
        score += 40
    if "vite build" in build_script or "next build" in build_script or "astro build" in build_script:
        score += 40
    if (package_json_path.parent / "index.html").exists():
        score += 20
    if (package_json_path.parent / "nitro.config.ts").exists() or (package_json_path.parent / "nitro.config.js").exists():
        score += 40
    return score


def detect_frontend_app(source_dir: Path) -> FrontendAppInfo | None:
    candidates = list_package_json_files(source_dir)
    if not candidates:
        return None

    ranked: list[tuple[int, Path, dict[str, Any]]] = []
    for package_json_path in candidates:
        payload = load_json_file(package_json_path)
        if not payload:
            continue
        score = score_frontend_candidate(source_dir, package_json_path, payload)
        if score > 0:
            ranked.append((score, package_json_path, payload))

    if not ranked:
        return None

    _, package_json_path, payload = sorted(ranked, key=lambda item: (item[0], str(item[1])), reverse=True)[0]
    app_root = package_json_path.parent
    manager = detect_package_manager(source_dir, app_root)
    if not manager:
        return None
    package_manager, install_root = manager
    scripts = payload.get("scripts") if isinstance(payload.get("scripts"), dict) else {}
    build_script = str(scripts.get("build") or "").strip()
    deps: dict[str, Any] = {}
    for key in ("dependencies", "devDependencies"):
        block = payload.get(key)
        if isinstance(block, dict):
            deps.update({str(name): value for name, value in block.items()})
    dep_names = set(deps)
    vite_config = app_root / "vite.config.ts"
    vite_text = vite_config.read_text(encoding="utf-8", errors="ignore") if vite_config.exists() else ""

    rel_app_root = app_root.relative_to(source_dir)
    rel_install_root = install_root.relative_to(source_dir)
    build_root_desc = "." if rel_app_root == Path(".") else str(rel_app_root)

    if package_manager == "pnpm":
        build_command = "pnpm build" if rel_app_root == rel_install_root else f"pnpm --dir {shlex.quote(str(rel_app_root))} build"
    elif package_manager == "npm":
        if install_root != app_root:
            return None
        build_command = "npm run build"
    else:
        if install_root != app_root:
            return None
        build_command = "yarn build"

    if (
        "nitro" in dep_names
        or (app_root / "nitro.config.ts").exists()
        or (app_root / "nitro.config.js").exists()
        or "nitro(" in vite_text
    ):
        return FrontendAppInfo(
            app_root=app_root,
            install_root=install_root,
            package_manager=package_manager,
            runtime="nitro",
            build_command=build_command,
            service_port=3000,
            output_path=str(rel_app_root / ".output"),
            startup_command=["node", ".output/server/index.mjs"],
            rationale=f"检测到前端应用目录 `{build_root_desc}` 使用 Nitro 构建，需按 Node server 运行时封装。",
        )

    if "vite" in dep_names or "astro" in dep_names or "vite build" in build_script or "astro build" in build_script:
        return FrontendAppInfo(
            app_root=app_root,
            install_root=install_root,
            package_manager=package_manager,
            runtime="static",
            build_command=build_command,
            service_port=80,
            output_path=str(rel_app_root / "dist"),
            startup_command=[],
            rationale=f"检测到前端应用目录 `{build_root_desc}` 使用静态站构建，可按 nginx 托管产物封装。",
        )

    return None


def readme_excerpt(readmes: list[Path]) -> str:
    chunks: list[str] = []
    for path in readmes[:3]:
        try:
            chunks.append(path.read_text(encoding="utf-8", errors="ignore").lower())
        except OSError:
            continue
    return "\n".join(chunks)


def gpu_project_excerpt(source_dir: Path, readmes: list[Path]) -> str:
    chunks: list[str] = []
    seen: set[Path] = set()
    candidates = list(readmes[:3])
    candidates.extend(sorted((source_dir / "docs").glob("*.md"))[:6])
    pyproject = source_dir / "pyproject.toml"
    if pyproject.exists():
        candidates.append(pyproject)
    for path in candidates:
        if path in seen or not path.exists():
            continue
        seen.add(path)
        try:
            chunks.append(path.read_text(encoding="utf-8", errors="ignore").lower())
        except OSError:
            continue
    return "\n".join(chunks)


def infer_gpu_service_port(source_dir: Path, text: str) -> int:
    if (source_dir / "demo" / "web" / "app.py").exists():
        return 3000
    if "gradio demo" in text or "launch gradio demo" in text:
        return 7860
    return 8000


def detect_gpu_first_ml_project(
    source_dir: Path,
    compose_file: Path | None,
    dockerfile: Path | None,
    readmes: list[Path],
) -> dict[str, Any] | None:
    if compose_file or dockerfile:
        return None

    text = gpu_project_excerpt(source_dir, readmes)
    if not text:
        return None

    strong_markers = [
        "nvidia deep learning container",
        "--gpus all",
        "cuda environment",
        "flash attention",
        "flash_attention",
        "vllm",
    ]
    service_markers = [
        "gradio demo",
        "websocket demo",
        "real-time websocket demo",
        "launch gradio demo",
        "text-to-speech",
        "speech recognition",
    ]
    strong_hits = [marker for marker in strong_markers if marker in text]
    service_hits = [marker for marker in service_markers if marker in text]

    if len(strong_hits) < 2 or not service_hits:
        return None

    return {
        "reason": (
            "检测到该仓库更像 GPU-first 的语音/推理研究项目。"
            f" 依据：README / docs 明确要求 {', '.join(strong_hits[:4])}，且主要入口是 {', '.join(service_hits[:3])}。"
            " 按当前 SOP，应优先评估 LazyCat AIPod / AI 应用路线，而不是继续强压到 CPU/Docker 微服容器。"
        ),
        "service_port": infer_gpu_service_port(source_dir, text),
        "strong_hits": strong_hits,
        "service_hits": service_hits,
    }


def detect_non_service_native_project(
    source_dir: Path,
    compose_file: Path | None,
    dockerfile: Path | None,
    readmes: list[Path],
) -> str | None:
    if compose_file:
        return None

    readme_text = readme_excerpt(readmes)
    root_file_names = {path.name for path in source_dir.iterdir() if path.is_file()}
    native_score = 0
    service_score = 0
    reasons: list[str] = []

    native_root_files = sorted(root_file_names & NATIVE_ROOT_BUILD_FILES)
    if native_root_files:
        native_score += 3
        reasons.append(f"根目录存在原生构建文件：{', '.join(native_root_files)}")

    native_matches = sorted({hint for hint in NATIVE_README_HINTS if hint in readme_text})
    if native_matches:
        native_score += min(4, len(native_matches))
        reasons.append(f"README 明显描述为原生客户端/多平台桌面应用：{', '.join(native_matches[:6])}")

    service_matches = {hint for hint in SERVICE_README_HINTS if hint in readme_text}
    if service_matches:
        service_score += min(3, len(service_matches))

    if dockerfile:
        try:
            relative = dockerfile.relative_to(source_dir)
        except ValueError:
            relative = dockerfile
        rel_parts = [part.lower() for part in relative.parts]
        if relative == Path("Dockerfile") or relative == Path("Containerfile"):
            service_score += 3
        else:
            if rel_parts and rel_parts[0] in LOW_PRIORITY_DOCKERFILE_DIRS:
                native_score += 2
                reasons.append(f"仅发现脚本/辅助目录下的 Dockerfile：{relative}")
            if any(part in NATIVE_PLATFORM_HINTS for part in rel_parts[:-1]):
                native_score += 2
                reasons.append(f"Dockerfile 位于平台专用目录：{relative}")

    if native_score >= 6 and native_score >= service_score + 5:
        detail = "；".join(dict.fromkeys(reasons))
        return (
            "检测到该仓库更像原生客户端/桌面应用，而不是提供 HTTP 入口的 LazyCat Web 微服。"
            + (f" 依据：{detail}。" if detail else "")
        )
    return None


def load_yaml(path: Path) -> Any:
    if yaml is not None:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data if data is not None else {}

    ruby_loader = textwrap.dedent(
        """
        require "yaml"
        require "json"

        path = ARGV[0]
        text = File.read(path)
        data = nil

        if defined?(Psych) && Psych.respond_to?(:safe_load)
          begin
            data = Psych.safe_load(text, aliases: true)
          rescue ArgumentError
            begin
              data = Psych.safe_load(text, [], [], true)
            rescue ArgumentError
              data = Psych.safe_load(text)
            end
          end
        end

        if data.nil?
          begin
            data = YAML.load(text)
          rescue ArgumentError
            data = YAML.load_file(path)
          end
        end

        puts JSON.generate(data)
        """
    ).strip()
    output = sh(["ruby", "--disable-gems", "-e", ruby_loader, str(path)])
    return json.loads(output) if output else {}


def refresh_icon_path(spec: dict[str, Any], source_dir: Path | None) -> None:
    icon_path = spec.get("icon_path")
    if icon_path:
        try:
            if Path(icon_path).exists():
                return
        except (OSError, TypeError, ValueError):
            pass
    if source_dir:
        discovered = bm.discover_repo_icon(source_dir)
        spec["icon_path"] = str(discovered) if discovered else ""
    elif not icon_path:
        spec["icon_path"] = ""


def sanitize_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "data"


def image_repository(image_ref: str) -> str:
    ref = image_ref.strip()
    if "@" in ref:
        ref = ref.split("@", 1)[0]
    last = ref.rsplit("/", 1)[-1]
    if ":" in last:
        return ref.rsplit(":", 1)[0]
    return ref


def image_tag(image_ref: str) -> str:
    ref = image_ref.strip()
    if "@" in ref:
        return ref.split("@", 1)[1]
    last = ref.rsplit("/", 1)[-1]
    if ":" in last:
        return last.rsplit(":", 1)[1]
    return ""


def is_version_like_tag(tag: str) -> bool:
    if not tag:
        return False
    lowered = tag.lower()
    if lowered in {"latest", "main", "master", "stable"}:
        return False
    return bool(re.search(r"\d+\.\d+", tag))


def parse_compose_ports(service: dict[str, Any]) -> list[int]:
    ports: list[int] = []
    for raw in bm.ensure_list(service.get("ports")):
        if isinstance(raw, int):
            ports.append(raw)
            continue
        if isinstance(raw, str):
            text = raw.strip().strip('"').strip("'")
            target = text.split(":")[-1].split("/")[0]
            if target.isdigit():
                ports.append(int(target))
            continue
        if isinstance(raw, dict):
            target = raw.get("target") or raw.get("container")
            if target:
                ports.append(int(target))
    for raw in bm.ensure_list(service.get("expose")):
        if isinstance(raw, int):
            ports.append(raw)
        elif isinstance(raw, str) and raw.split("/")[0].isdigit():
            ports.append(int(raw.split("/")[0]))
    return list(dict.fromkeys(ports))


def compose_env_entry(name: str, value: Any, service_name: str) -> tuple[str, dict[str, Any]]:
    if value is None:
        return name, {"name": name, "required": True, "description": f"From compose service {service_name}"}
    rendered = str(value).strip()
    doc: dict[str, Any] = {"name": name, "description": f"From compose service {service_name}"}
    env_match = re.fullmatch(r"\$\{([^}:?-]+)(?:(:?[-?])(.*))?\}", rendered)
    if env_match:
        var_name = env_match.group(1)
        operator = env_match.group(2) or ""
        operand = (env_match.group(3) or "").strip()
        if operator in {":-", "-"}:
            doc["required"] = False
            if operand:
                doc["value"] = operand
            return f"{name}=${{{var_name}{operator}{operand}}}", doc
        doc["required"] = True
        if var_name != name:
            doc["source_name"] = var_name
            return f"{name}=${{{var_name}}}", doc
        return name, doc
    doc["required"] = False
    doc["value"] = rendered
    return f"{name}={rendered}", doc


def extract_compose_environment(service_name: str, payload: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]]]:
    rendered: list[str] = []
    docs: list[dict[str, Any]] = []
    env_block = payload.get("environment")
    if isinstance(env_block, dict):
        for key, value in env_block.items():
            line, doc = compose_env_entry(str(key), value, service_name)
            rendered.append(line)
            docs.append(doc)
    elif isinstance(env_block, list):
        for raw in env_block:
            if not isinstance(raw, str):
                continue
            if "=" in raw:
                key, value = raw.split("=", 1)
                line, doc = compose_env_entry(key, value, service_name)
            else:
                line, doc = compose_env_entry(raw, None, service_name)
            rendered.append(line)
            docs.append(doc)
    return rendered, docs


def target_host_path(slug: str, service_name: str, target: str) -> str:
    target_lower = target.lower()
    service_lower = service_name.lower()
    if any(token in target_lower for token in ("/var/lib/postgresql", "/var/lib/mysql", "/var/lib/mariadb")) or service_lower in {"db", "postgres", "postgresql", "mysql", "mariadb"}:
        return f"/lzcapp/var/db/{slug}/{sanitize_token(service_name)}"
    if service_lower == "redis" or target_lower == "/data":
        return f"/lzcapp/var/data/{slug}/{sanitize_token(service_name)}"
    # For single-service apps where service == slug, avoid redundant nesting
    tail = sanitize_token(Path(target).name or "data")
    if service_lower == slug.lower():
        return f"/lzcapp/var/data/{slug}"
    return f"/lzcapp/var/data/{slug}/{sanitize_token(service_name)}/{tail}"


_CONTENT_BIND_EXTENSIONS = frozenset(
    {".conf", ".yaml", ".yml", ".json", ".toml", ".ini", ".env", ".sh", ".template", ".lua", ".xml"}
)


def detect_content_bind(
    raw: Any,
    compose_file: Path,
) -> tuple[str | None, Path | None]:
    """Pattern 5: relative :ro config file mounts → /lzcapp/pkg/content/<name>:<target>.

    Returns (bind_string, source_path) when the volume should become a content bind,
    or (None, None) otherwise.  source_path is the resolved file to copy into content/.
    """
    if not isinstance(raw, str):
        return None, None
    parts = raw.split(":")
    if len(parts) < 3:
        return None, None
    source_str, target, mode = parts[0].strip(), parts[1].strip(), parts[2].strip()
    if "ro" not in mode.split(","):
        return None, None
    if not source_str.startswith(("./", "../")):
        return None, None
    if not target.startswith("/"):
        return None, None
    source_path = (compose_file.parent / source_str).resolve()
    if not source_path.is_file():
        return None, None
    suffix = source_path.suffix.lower()
    # Also catch multi-suffix names like nginx.conf.template
    has_config_ext = suffix in _CONTENT_BIND_EXTENSIONS or any(
        source_path.name.endswith(ext) for ext in _CONTENT_BIND_EXTENSIONS
    )
    if not has_config_ext:
        return None, None
    bind = f"/lzcapp/pkg/content/{source_path.name}:{target}"
    return bind, source_path


def parse_compose_volume(raw: Any, slug: str, service_name: str) -> tuple[str | None, dict[str, Any] | None]:
    source = ""
    target = ""
    read_only = False

    if isinstance(raw, str):
        parts = raw.split(":")
        if len(parts) == 1:
            target = parts[0]
        elif len(parts) >= 2:
            source = parts[0]
            target = parts[1]
            mode = parts[2] if len(parts) >= 3 else ""
            read_only = "ro" in mode.split(",")
    elif isinstance(raw, dict):
        target = str(raw.get("target") or raw.get("destination") or "").strip()
        source = str(raw.get("source") or raw.get("src") or "").strip()
        read_only = bool(raw.get("read_only", False))
        if str(raw.get("type") or "").strip() == "tmpfs":
            return None, None
    else:
        return None, None

    if not target.startswith("/"):
        return None, None
    if read_only:
        return None, None
    if target in {"/var/run/docker.sock", "/run/docker.sock", "/etc/localtime"}:
        return None, None
    if Path(target).suffix and not target.endswith((".d", "/")):
        return None, None

    host = target_host_path(slug, service_name, target)
    bind = f"{host}:{target}"
    doc = {
        "host": host,
        "container": target,
        "description": f"From compose service {service_name}",
    }
    return bind, doc


def compose_depends_on(payload: dict[str, Any]) -> list[str]:
    depends = payload.get("depends_on")
    if isinstance(depends, list):
        return [str(item) for item in depends if str(item).strip()]
    if isinstance(depends, dict):
        return [str(item) for item in depends.keys() if str(item).strip()]
    return []


def is_well_known_public_image(image_ref: str) -> bool:
    """Return True if image_ref is a well-known public infrastructure/gateway image."""
    ref = image_ref.strip().lower()
    repo_part = image_repository(ref)
    first_component = repo_part.split("/")[0]
    if "." in first_component or ":" in first_component:
        return False  # private registry
    base = repo_part.rsplit("/", 1)[-1]
    return base in GATEWAY_IMAGE_NAMES or base in {k.lower() for k in INFRA_KEYWORDS}


def _infer_health_check_url(test: Any, service_name: str, port: int) -> str | None:
    """Extract a health-check URL from a compose healthcheck test list."""
    if isinstance(test, list):
        cmd = " ".join(str(c) for c in test)
    elif isinstance(test, str):
        cmd = test
    else:
        return None
    m = re.search(r"(?:localhost|127\.0\.0\.1|0\.0\.0\.0):(\d+)(/[^\s\"']*)?", cmd)
    if m:
        p = int(m.group(1))
        path = (m.group(2) or "/").rstrip()
        return f"http://{service_name}:{p}{path}"
    return None


def is_k8s_only_service(name: str, payload: dict[str, Any]) -> bool:
    """Return True if this compose service is k8s-specific and should be excluded."""
    lowered = name.lower()
    if any(kw in lowered for kw in ("provisioner", "k8s-", "kubernetes-")):
        return True
    env = payload.get("environment", [])
    env_keys: list[str] = []
    if isinstance(env, list):
        env_keys = [str(item).split("=", 1)[0].upper() for item in env]
    elif isinstance(env, dict):
        env_keys = [str(k).upper() for k in env]
    return any(key.startswith(prefix) for key in env_keys for prefix in K8S_ENV_PREFIXES)


def service_score(name: str, payload: dict[str, Any]) -> int:
    lowered = name.lower()
    score = 0
    ports = parse_compose_ports(payload)
    if ports:
        score += 50
    if any(hint in lowered for hint in WEB_HINTS):
        score += 30
    if payload.get("healthcheck"):
        score += 10
    if payload.get("build") or payload.get("image"):
        score += 10
    if compose_depends_on(payload):
        score += 5
    if any(token in lowered for token in INFRA_KEYWORDS):
        score -= 120
    image_ref = str(payload.get("image", "")).lower()
    if any(token in image_ref for token in INFRA_KEYWORDS):
        score -= 120
    return score


def choose_primary_service(services: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    ranked = sorted(services.items(), key=lambda item: (service_score(item[0], item[1]), item[0]), reverse=True)
    return ranked[0]


def dedupe_env_docs(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for entry in entries:
        name = str(entry.get("name", "")).strip()
        if not name:
            continue
        current = merged.get(name, {"name": name})
        current.update({k: v for k, v in entry.items() if v not in ("", None)})
        merged[name] = current
    return list(merged.values())


def dedupe_data_paths(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[tuple[str, str], dict[str, Any]] = {}
    for entry in entries:
        key = (str(entry.get("host", "")), str(entry.get("container", "")))
        if key not in seen and key[0] and key[1]:
            seen[key] = entry
    return list(seen.values())


def infer_compose_upstreams(
    primary_name: str,
    primary_port: int,
    services: dict[str, Any],
    *,
    frontend_gateway: ComposeProxyFrontendInfo | None = None,
) -> list[dict[str, str]]:
    upstreams: list[dict[str, str]] = [
        {"location": "/", "backend": f"http://{primary_name}:{primary_port}/"}
    ]
    if frontend_gateway:
        return upstreams
    for service_name, payload in services.items():
        if service_name == primary_name or not isinstance(payload, dict):
            continue
        lowered = service_name.lower()
        ports = parse_compose_ports(payload)
        if not ports:
            continue
        service_port = ports[0]
        if lowered in {"api", "backend", "server"} or lowered.endswith("-api") or lowered.endswith("_api"):
            upstreams.insert(0, {"location": "/api/", "backend": f"http://{service_name}:{service_port}/"})
        elif lowered == "minio":
            upstreams.insert(1 if upstreams and upstreams[0]["location"] == "/api/" else 0, {"location": "/minio/", "backend": f"http://{service_name}:{service_port}/"})
    deduped: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in upstreams:
        location = item["location"]
        if location in seen:
            continue
        seen.add(location)
        deduped.append(item)
    return deduped


def compose_build_context_dir(source_root: Path, compose_file: Path, payload: dict[str, Any]) -> Path | None:
    raw_build = payload.get("build")
    if not raw_build:
        return None
    build_info = raw_build if isinstance(raw_build, dict) else {"context": str(raw_build)}
    context_rel = str(build_info.get("context") or ".").strip()
    candidate = (compose_file.parent / context_rel).resolve()
    try:
        candidate.relative_to(source_root.resolve())
    except ValueError:
        return None
    return candidate


def read_candidate_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def iter_frontend_gateway_config_candidates(
    source_root: Path,
    compose_file: Path,
    service_name: str,
    payload: dict[str, Any],
) -> list[Path]:
    candidates: list[Path] = []
    seen: set[Path] = set()

    def add_path(path: Path) -> None:
        if not path.exists() or path in seen:
            return
        seen.add(path)
        candidates.append(path)

    build_context = compose_build_context_dir(source_root, compose_file, payload)
    search_roots: list[Path] = []
    if build_context:
        search_roots.append(build_context)
    service_dir = source_root / service_name
    if service_dir.exists():
        search_roots.append(service_dir)
    for hint in FRONTEND_HINT_DIRS:
        candidate = source_root / hint
        if candidate.exists():
            search_roots.append(candidate)

    for root in search_roots:
        add_path(root / "vite.config.ts")
        add_path(root / "vite.config.js")
        add_path(root / "vite.config.mjs")
        add_path(root / "vite.config.cjs")
        add_path(root / "nginx.conf")
        add_path(root / "default.conf")
        add_path(root / "Caddyfile")
        deploy_dir = root / "deploy"
        if deploy_dir.exists():
            for pattern in ("*.conf", "*.conf.template", "*.template", "Caddyfile"):
                for matched in sorted(deploy_dir.glob(pattern))[:8]:
                    add_path(matched)
        nginx_dir = root / "nginx"
        if nginx_dir.exists():
            for pattern in ("*.conf", "*.conf.template", "*.template"):
                for matched in sorted(nginx_dir.glob(pattern))[:8]:
                    add_path(matched)
    return candidates


def detect_proxy_locations_in_text(text: str, backend_services: set[str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    lowered = text.lower()
    locations = tuple(location for location in FRONTEND_GATEWAY_LOCATIONS if location in lowered)
    if not locations:
        return (), ()

    matched_services: list[str] = []
    for service_name in sorted(backend_services):
        service_pattern = re.compile(rf"https?://{re.escape(service_name)}(?::\d+)?", re.IGNORECASE)
        if service_pattern.search(text):
            matched_services.append(service_name)
    return tuple(dict.fromkeys(locations)), tuple(dict.fromkeys(matched_services))


def detect_compose_frontend_gateway(
    source_root: Path,
    compose_file: Path,
    primary_name: str,
    primary_service: dict[str, Any],
    services: dict[str, Any],
) -> ComposeProxyFrontendInfo | None:
    backend_services = {
        service_name
        for service_name, payload in services.items()
        if service_name != primary_name and isinstance(payload, dict)
    }
    if not backend_services:
        return None

    primary_name_lower = primary_name.lower()
    frontend_like = any(token in primary_name_lower for token in ("web", "frontend", "ui", "nginx", "site", "app"))
    config_candidates = iter_frontend_gateway_config_candidates(source_root, compose_file, primary_name, primary_service)
    for candidate in config_candidates:
        text = read_candidate_text(candidate)
        if not text:
            continue
        locations, matched_services = detect_proxy_locations_in_text(text, backend_services)
        if not locations or not matched_services:
            continue
        if not frontend_like and "proxy_pass" not in text and "server.proxy" not in text and "proxy:" not in text:
            continue
        return ComposeProxyFrontendInfo(
            config_path=candidate,
            backend_services=matched_services,
            locations=locations,
        )
    return None


def rewrite_public_url_envs(environment: list[str], slug: str) -> list[str]:
    public_base = f"https://{slug}.${{LAZYCAT_BOX_DOMAIN}}"
    replacements = {
        "PUBLIC_FRONT_URL": public_base,
        "PUBLIC_API_URL": f"{public_base}/api",
        "PUBLIC_MINIO_ENDPOINT": f"{public_base}/minio",
        "API_URL": f"{public_base}/api",
    }
    rendered: list[str] = []
    for entry in environment:
        if "=" not in entry:
            rendered.append(entry)
            continue
        name, value = entry.split("=", 1)
        replacement = replacements.get(name)
        if replacement and (
            "localhost" in value
            or value in {"", f"${{{name}}}"}
            or (name == "API_URL" and value == "${PUBLIC_API_URL}")
        ):
            rendered.append(f"{name}={replacement}")
            continue
        rendered.append(entry)
    return rendered


def parse_env_files(paths: list[Path]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for path in paths:
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            text = line.strip()
            if not text or text.startswith("#"):
                continue
            text = text.removeprefix("export ").strip()
            if "=" not in text:
                continue
            key, value = text.split("=", 1)
            name = key.strip()
            if not re.fullmatch(r"[A-Z][A-Z0-9_]+", name):
                continue
            item: dict[str, Any] = {
                "name": name,
                "description": f"From {path.name}",
                "required": False,
            }
            cleaned = value.strip().strip('"').strip("'")
            if cleaned:
                item["value"] = cleaned
            entries.append(item)
    return dedupe_env_docs(entries)


def env_defaults_map(entries: list[dict[str, Any]]) -> dict[str, str]:
    defaults: dict[str, str] = {}
    for entry in entries:
        name = str(entry.get("name", "")).strip()
        if not name or "value" not in entry or entry["value"] is None:
            continue
        defaults[name] = str(entry["value"])
    return defaults


def resolve_compose_environment(environment: list[str], defaults: dict[str, str]) -> list[str]:
    resolved: list[str] = []
    for entry in environment:
        if "=" not in entry:
            resolved.append(entry)
            continue

        name, value = entry.split("=", 1)
        match = re.fullmatch(r"\$\{([^}:?-]+)(?:(:?[-?])(.*))?\}", value.strip())
        if not match:
            resolved.append(entry)
            continue

        source_name = match.group(1)
        operator = match.group(2) or ""
        operand = match.group(3) or ""

        if source_name in defaults:
            resolved.append(f"{name}={defaults[source_name]}")
            continue

        if operator in {":-", "-"}:
            resolved.append(f"{name}={operand}")
            continue

        resolved.append(entry)
    return resolved


def resolve_compose_env_docs(entries: list[dict[str, Any]], defaults: dict[str, str]) -> list[dict[str, Any]]:
    resolved: list[dict[str, Any]] = []
    for entry in entries:
        item = dict(entry)
        source_name = str(item.get("source_name") or item.get("name") or "").strip()
        if source_name in defaults and "value" not in item:
            item["value"] = defaults[source_name]
            item["required"] = False
        elif item.get("required") is False and "value" not in item and source_name == str(item.get("name", "")).strip():
            item["value"] = ""
        resolved.append(item)
    return resolved


def parse_dockerfile_ports(dockerfile_path: Path) -> list[int]:
    ports: list[int] = []
    text = dockerfile_path.read_text(encoding="utf-8", errors="ignore")
    for match in re.finditer(r"(?im)^\s*EXPOSE\s+([0-9]+)", text):
        ports.append(int(match.group(1)))
    return list(dict.fromkeys(ports))


def _scan_dockerfile_write_paths(text: str) -> list[tuple[str, str]]:
    """Scan Dockerfile text for paths that the container is likely to write to.

    Returns (container_path, source_hint) pairs.
    """
    results: list[tuple[str, str]] = []

    # 1. Explicit VOLUME directives
    for match in re.finditer(r"(?im)^\s*VOLUME\s+(.+)$", text):
        raw = match.group(1).strip()
        targets: list[str] = []
        if raw.startswith("["):
            try:
                decoded = json.loads(raw.replace("'", '"'))
                targets.extend(str(item) for item in decoded)
            except json.JSONDecodeError:
                pass
        else:
            targets.extend(part.strip().strip('"').strip("'") for part in raw.split())
        for t in targets:
            if t.startswith("/"):
                results.append((t, "Dockerfile VOLUME"))

    # 2. mkdir -p in RUN/CMD/ENTRYPOINT/entrypoint scripts
    # Exclude system-managed directories that don't hold user data and don't need bind mounts.
    _SYSTEM_PATH_PREFIXES = (
        "/tmp", "/etc/", "/var/log/", "/var/run/", "/run/",
        "/usr/", "/lib/", "/lib64/", "/proc/", "/sys/", "/dev/",
        "/bin/", "/sbin/", "/opt/",
    )
    for match in re.finditer(r"mkdir\s+-p\s+([\w/.${}~-]+)", text):
        path = match.group(1).strip()
        if path.startswith("/") and not any(path.startswith(p) for p in _SYSTEM_PATH_PREFIXES):
            results.append((path, "mkdir -p in Dockerfile"))

    # 3. Resolve HOME-relative data dirs
    home_dir = "/root"  # default for most containers
    home_match = re.search(r"(?im)^\s*ENV\s+HOME[=\s]+([^\s]+)", text)
    if home_match:
        home_dir = home_match.group(1).strip().rstrip("/")

    workdir = ""
    for match in re.finditer(r"(?im)^\s*WORKDIR\s+(.+)$", text):
        workdir = match.group(1).strip()

    # Common app-data subdirs under $HOME
    home_data_patterns = [
        ".local/share", ".config", ".cache",
    ]
    for pattern in home_data_patterns:
        full = f"{home_dir}/{pattern}"
        # Check if Dockerfile references this path
        if full in text or f"$HOME/{pattern}" in text or f"~/{pattern}" in text:
            results.append((full, f"HOME-relative data dir ({pattern})"))

    # 4. Common absolute write path patterns referenced in Dockerfile
    common_write_patterns = [
        r"/data(?:/|\s|$|\")",
        r"/app/data(?:/|\s|$|\")",
        r"/opt/[a-z_-]+/data(?:/|\s|$|\")",
        r"/var/data(?:/|\s|$|\")",
    ]
    for pat in common_write_patterns:
        if re.search(pat, text):
            # Extract the clean path
            clean = re.search(pat, text)
            if clean:
                path = clean.group(0).rstrip(' "/\n')
                if path not in [r[0] for r in results]:
                    results.append((path, "common data path pattern"))

    return results


def _scan_entrypoint_write_paths(source_dir: Path, dockerfile_path: Path) -> list[tuple[str, str]]:
    """Scan entrypoint scripts referenced by COPY in Dockerfile for write paths."""
    results: list[tuple[str, str]] = []
    text = dockerfile_path.read_text(encoding="utf-8", errors="ignore")

    # Find COPY'd shell scripts that are made executable or used as ENTRYPOINT
    entrypoint_files: list[str] = []
    for match in re.finditer(r"(?im)^\s*COPY\s+(?:--[^\s]+\s+)*(\S+\.sh)\s+", text):
        entrypoint_files.append(match.group(1))
    for match in re.finditer(r'(?im)^\s*ENTRYPOINT\s+\[?"?([^"\]\s]+)', text):
        name = match.group(1).strip("'\"")
        if name.endswith(".sh"):
            entrypoint_files.append(Path(name).name)

    for script_name in set(entrypoint_files):
        script_path = source_dir / script_name
        if not script_path.is_file():
            # Try without leading path
            script_path = source_dir / Path(script_name).name
        if not script_path.is_file():
            continue
        try:
            script_text = script_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        _SYSTEM_PATH_PREFIXES_EP = (
            "/tmp", "/etc/", "/var/log/", "/var/run/", "/run/",
            "/usr/", "/lib/", "/lib64/", "/proc/", "/sys/", "/dev/",
            "/bin/", "/sbin/", "/opt/",
        )
        for match in re.finditer(r"mkdir\s+-p\s+([\w/.${}~-]+)", script_text):
            path = match.group(1).strip()
            if path.startswith("/") and not any(path.startswith(p) for p in _SYSTEM_PATH_PREFIXES_EP):
                results.append((path, f"mkdir -p in {script_name}"))

    return results


def _scan_source_data_dirs(source_dir: Path) -> list[tuple[str, str]]:
    """Scan common source files for hardcoded data directory references."""
    results: list[tuple[str, str]] = []
    # Look for path declarations in config/source files
    patterns_by_ext = {
        (".ts", ".js", ".mjs"): [
            r'path\.join\(.*?\.local.*?share',
            r'homedir\(\).*\.local/share',
            r'["\']\.local/share/',
        ],
        (".py",): [
            r'Path\.home\(\).*\.local/share',
            r'expanduser\(.*\.local/share',
            r'XDG_DATA_HOME',
        ],
        (".go",): [
            r'os\.UserHomeDir\(\)',
            r'\.local/share/',
        ],
    }
    # Only scan top-level src/ and root files, not node_modules etc.
    scan_dirs = [source_dir / "src", source_dir / "lib", source_dir]
    scanned = set()
    for scan_dir in scan_dirs:
        if not scan_dir.is_dir():
            continue
        for ext_group, pats in patterns_by_ext.items():
            for f in scan_dir.rglob("*"):
                if f.suffix not in ext_group or f in scanned:
                    continue
                if any(skip in str(f) for skip in ("node_modules", ".git", "dist", "build", "__pycache__")):
                    continue
                scanned.add(f)
                try:
                    content = f.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue
                for pat in pats:
                    if re.search(pat, content):
                        results.append(("$HOME/.local/share/<app>", f"source code pattern in {f.name}"))
                        break
    return results


def parse_dockerfile_volumes(dockerfile_path: Path, slug: str, service_name: str, source_dir: Path | None = None) -> list[dict[str, Any]]:
    text = dockerfile_path.read_text(encoding="utf-8", errors="ignore")
    raw_paths = _scan_dockerfile_write_paths(text)

    # Also scan entrypoint scripts and source code if source_dir available
    if source_dir and source_dir.is_dir():
        raw_paths.extend(_scan_entrypoint_write_paths(source_dir, dockerfile_path))
        raw_paths.extend(_scan_source_data_dirs(source_dir))

    # Resolve HOME-relative patterns for this specific app
    home_dir = "/root"
    home_match = re.search(r"(?im)^\s*ENV\s+HOME[=\s]+([^\s]+)", text)
    if home_match:
        home_dir = home_match.group(1).strip().rstrip("/")

    entries: list[dict[str, Any]] = []
    seen_containers: set[str] = set()
    for container_path, source_hint in raw_paths:
        # Resolve $HOME placeholder from source code scan
        if container_path == "$HOME/.local/share/<app>":
            container_path = f"{home_dir}/.local/share/{slug}"

        # Skip paths we already have
        if container_path in seen_containers:
            continue
        seen_containers.add(container_path)

        if container_path.startswith("/"):
            host = target_host_path(slug, service_name, container_path)
            entries.append({"host": host, "container": container_path, "description": f"From {source_hint}"})

    return dedupe_data_paths(entries)


def parse_dockerfile_healthcheck(dockerfile_path: Path) -> dict[str, Any] | None:
    text = dockerfile_path.read_text(encoding="utf-8", errors="ignore")
    # Match HEALTHCHECK with optional flags, then CMD until end of logical line.
    # A logical line may be continued with backslash; stop at the first
    # non-continuation newline or next Dockerfile directive.
    match = re.search(
        r"(?im)^[ \t]*HEALTHCHECK\s+(?:--[^\n]+\n\s*)*CMD\s+(.+?)(?:\s*\\?\s*\n\s*(?=[A-Z]{2,})|\s*$)",
        text,
    )
    if not match:
        return None
    # Collapse continuation lines and trim trailing backslash
    raw = match.group(1).rstrip(" \\")
    command = " ".join(raw.split())
    return {
        "test": ["CMD-SHELL", command],
        "interval": "30s",
        "timeout": "10s",
        "retries": 5,
    }


def parse_release_binary_candidate(upstream_repo: str) -> dict[str, Any] | None:
    release = bm.github_api_json(f"repos/{upstream_repo}/releases/latest")
    if not isinstance(release, dict):
        return None
    tag_name = str(release.get("tag_name", "")).strip()
    assets = release.get("assets")
    if not isinstance(assets, list):
        return None
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        name = str(asset.get("name", "")).lower()
        url = str(asset.get("browser_download_url", "")).strip()
        if not url:
            continue
        if "linux" in name and any(arch in name for arch in ("amd64", "x86_64")) and name.endswith((".tar.gz", ".tgz", ".zip")):
            templated_url = url
            if tag_name:
                templated_url = templated_url.replace(f"/{tag_name}/", "/$LATEST_VERSION/")
            binary_base = re.sub(r"(\.tar\.gz|\.tgz|\.zip)$", "", Path(url).name)
            binary_base = re.sub(r"-(linux|amd64|x86_64).*$", "", binary_base)
            return {
                "url": templated_url,
                "tag_name": tag_name,
                "binary_name": sanitize_token(binary_base).replace("-", "_"),
            }
    return None


def stringify_command(command: Any) -> str:
    if isinstance(command, list):
        return " ".join(str(item) for item in command)
    return str(command or "")


def env_var_names(environment: list[str]) -> list[str]:
    names: list[str] = []
    for entry in environment:
        name = entry.split("=", 1)[0].strip()
        if name and re.fullmatch(r"[A-Z][A-Z0-9_]*", name):
            names.append(name)
    return list(dict.fromkeys(names))


def build_runtime_env_file_command(
    environment: list[str],
    *,
    workdir: str,
    env_file: str,
    env_config: str,
    final_cmd: str,
) -> str:
    names = env_var_names(environment)
    render_env_file = ""
    if names:
        rendered_pairs = " ".join(f'"{name}=${{{name}-}}"' for name in names)
        render_env_file = f"printf '%s\\n' {rendered_pairs} > {shlex.quote(env_file)}; "
    shell_script = (
        "set -e; "
        f"cd {shlex.quote(workdir)}; "
        f"{render_env_file}"
        f"NODE_ENV=development runtime-env-cra --config-name={shlex.quote(env_config)} --env-file={shlex.quote(env_file)}; "
        f"{final_cmd}"
    )
    return f"/bin/sh -lc {shlex.quote(shell_script)}"


def is_probably_dev_compose(services: dict[str, Any]) -> bool:
    if not services:
        return False
    dev_like = 0
    for payload in services.values():
        if not isinstance(payload, dict):
            continue
        build_declared = bool(payload.get("build"))
        command_text = stringify_command(payload.get("command")).lower()
        if build_declared and any(token in f" {command_text} " for token in DEV_COMMAND_HINTS):
            dev_like += 1
    return dev_like == len(services)


def detect_official_image_from_readmes(readmes: list[Path]) -> dict[str, Any] | None:
    docker_run_pattern = re.compile(r"docker\s+run[^\n`]*", re.IGNORECASE)
    image_pattern = re.compile(r"(docker\.[A-Za-z0-9.-]+/[A-Za-z0-9./_-]+:[A-Za-z0-9._-]+)")

    for readme in readmes[:3]:
        text = readme.read_text(encoding="utf-8", errors="ignore")
        for match in docker_run_pattern.finditer(text):
            snippet = match.group(0)
            image_matches = image_pattern.findall(snippet)
            if not image_matches:
                continue
            image_ref = image_matches[-1].strip()
            port = 80
            port_matches = re.findall(r"-p\s+\d+:(\d+)", snippet)
            if port_matches:
                port = int(port_matches[0])
            return {"image": image_ref, "port": port, "source": readme.name}
        image_match = image_pattern.search(text)
        if image_match:
            return {"image": image_match.group(1).strip(), "port": 80, "source": readme.name}
    return None


def choose_route_for_official_image(slug: str, meta: dict[str, Any], image_ref: str, service_port: int, note: str) -> dict[str, Any]:
    tag = image_tag(image_ref)
    version = str(meta.get("version") or "").strip()
    if not version and is_version_like_tag(tag):
        version = bm.normalize_semver(tag)
    version = version or "0.1.0"

    return {
        "slug": slug,
        "project_name": str(meta.get("project_name") or bm.titleize_slug(slug)),
        "description": str(meta.get("description") or f"{slug} on LazyCat"),
        "description_zh": f"（迁移初稿）{bm.titleize_slug(slug)} 的懒猫微服版本",
        "upstream_repo": str(meta.get("upstream_repo", "")),
        "homepage": str(meta.get("homepage", "")),
        "license": str(meta.get("license") or ""),
        "author": str(meta.get("author") or "TODO"),
        "version": version,
        "check_strategy": str(meta.get("check_strategy", "github_release")),
        "build_strategy": "official_image",
        "official_image_registry": image_repository(image_ref),
        "service_port": service_port,
        "image_targets": [slug],
        "services": {
            slug: {
                "image": image_ref,
            }
        },
        "application": {
            "subdomain": slug,
            "public_path": ["/"],
            "upstreams": [{"location": "/", "backend": f"http://{slug}:{service_port}/"}],
        },
        "env_vars": [],
        "data_paths": [],
        "startup_notes": [note],
        "_risks": [],
        "_post_write": {},
    }


def normalize_compose_build_args(raw_args: Any) -> dict[str, Any]:
    if not raw_args:
        return {}
    if isinstance(raw_args, dict):
        return dict(raw_args)
    if isinstance(raw_args, list):
        normalized: dict[str, Any] = {}
        for item in raw_args:
            if isinstance(item, str):
                key, sep, value = item.partition("=")
                key = key.strip()
                if key:
                    normalized[key] = value if sep else ""
            elif isinstance(item, dict):
                normalized.update(item)
        return normalized
    if isinstance(raw_args, str):
        key, sep, value = raw_args.partition("=")
        key = key.strip()
        return {key: value if sep else ""} if key else {}
    return {}


def detect_required_upstream_submodules(source_root: Path, dockerfile_path: Path | None) -> list[str]:
    gitmodules = source_root / ".gitmodules"
    if not gitmodules.exists() or not dockerfile_path or not dockerfile_path.exists():
        return []

    paths: list[str] = []
    for line in gitmodules.read_text(encoding="utf-8", errors="ignore").splitlines():
        match = re.match(r"\s*path\s*=\s*(.+?)\s*$", line)
        if match:
            paths.append(match.group(1).strip())
    if not paths:
        return []

    copied_roots: set[str] = set()
    dockerfile_text = dockerfile_path.read_text(encoding="utf-8", errors="ignore")
    for raw_line in dockerfile_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r"(?i)^(COPY|ADD)\s+(?:--\S+\s+)*(.+?)\s+\S+\s*$", line)
        if not match:
            continue
        for source in shlex.split(match.group(2)):
            clean = source.lstrip("./")
            if clean and clean not in {".", "*"}:
                copied_roots.add(clean.split("/", 1)[0])

    required: list[str] = []
    for path in paths:
        top = path.split("/", 1)[0]
        if top == "docs" and top not in copied_roots and path not in copied_roots:
            continue
        if top in copied_roots or path in copied_roots:
            required.append(path)
    return required


def _warn_inconsistent_service_naming(slug: str, service_names: list[str]) -> None:
    if len(service_names) < 2:
        return
    prefix = f"{slug}-"
    prefixed = [n for n in service_names if n.startswith(prefix)]
    bare = [n for n in service_names if not n.startswith(prefix)]
    if prefixed and bare:
        print(
            f"[migrate] WARNING: compose services mix slug-prefixed and bare names: "
            f"prefixed={prefixed}, bare={bare}. "
            f"Recommend manually renaming bare services to '{slug}-<name>' for consistency, "
            "and keep upstreams.backend / depends_on references in lock-step.",
            file=sys.stderr,
        )


def choose_route_for_compose(
    slug: str,
    meta: dict[str, Any],
    source_root: Path,
    compose_file: Path,
    dockerfile: Path | None,
    env_files: list[Path],
) -> dict[str, Any]:
    compose = load_yaml(compose_file)
    services = compose.get("services") if isinstance(compose, dict) else {}
    if not isinstance(services, dict) or not services:
        raise ValueError(f"compose file has no services: {compose_file}")

    primary_name, primary_service = choose_primary_service(services)
    _warn_inconsistent_service_naming(slug, list(services.keys()))
    primary_ports = parse_compose_ports(primary_service)
    primary_port = primary_ports[0] if primary_ports else 3000
    primary_image = str(primary_service.get("image", "")).strip()
    primary_build = primary_service.get("build")
    env_docs: list[dict[str, Any]] = []
    data_docs: list[dict[str, Any]] = []
    service_specs: dict[str, Any] = {}
    image_targets: list[str] = []
    dependencies: list[dict[str, Any]] = []
    service_builds: list[dict[str, Any]] = []
    risks: list[str] = []
    post_write: dict[str, str] = {}

    selected_dockerfile: Path | None = dockerfile
    build_args: dict[str, Any] = {}
    build_strategy = ""
    official_image_registry = ""
    dockerfile_path = ""
    upstream_submodules: list[str] = []
    env_defaults = env_defaults_map(parse_env_files(env_files))
    frontend_gateway = detect_compose_frontend_gateway(source_root, compose_file, primary_name, primary_service, services)

    build_services: dict[str, dict[str, Any]] = {}

    def infer_service_build(service_name: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        raw_build = payload.get("build")
        if raw_build:
            build_info = raw_build if isinstance(raw_build, dict) else {"context": str(raw_build)}
            context_rel = str(build_info.get("context") or ".").strip()
            context_dir = (compose_file.parent / context_rel).resolve()
            dockerfile_name = str(build_info.get("dockerfile") or "Dockerfile").strip()
            dockerfile_candidate = (context_dir / dockerfile_name).resolve()
            try:
                build_context_rel = str(context_dir.relative_to(source_root.resolve()))
                dockerfile_rel = str(dockerfile_candidate.relative_to(source_root.resolve()))
            except ValueError as exc:
                raise ValueError(f"compose build path escapes source root: {service_name}") from exc
            raw_args = normalize_compose_build_args(build_info.get("args"))
            # Strip infra-only build args: upstream CI mirrors/proxies with empty optional defaults
            build_args = {
                k: v for k, v in raw_args.items()
                if not re.fullmatch(r"\$\{[^}]+:-\}", str(v))
            }
            spec: dict[str, Any] = {
                "target_service": service_name,
                "build_strategy": "upstream_dockerfile",
                "source_dockerfile_path": dockerfile_rel,
                "build_context": build_context_rel,
                "build_args": build_args,
                "image_name": f"{slug}-{sanitize_token(service_name)}",
            }
            build_target = str(build_info.get("target") or "").strip()
            if build_target:
                spec["build_target"] = build_target
            return spec

        image_ref = str(payload.get("image", "")).strip()
        if not image_ref or is_version_like_tag(image_tag(image_ref)):
            return None
        service_dir = source_root / service_name
        dockerfile_candidate = service_dir / "Dockerfile"
        if not dockerfile_candidate.exists():
            return None
        return {
            "target_service": service_name,
            "build_strategy": "upstream_dockerfile",
            "source_dockerfile_path": str(dockerfile_candidate.relative_to(source_root)),
            "build_context": str(service_dir.relative_to(source_root)),
            "build_args": {},
            "image_name": f"{slug}-{sanitize_token(service_name)}",
        }

    for service_name, payload in services.items():
        build_spec = infer_service_build(service_name, payload)
        if build_spec:
            build_services[service_name] = build_spec

    # Filter k8s-only services (Kubernetes provisioner etc.) — not deployable on LazyCat
    k8s_only = {n for n in build_services if is_k8s_only_service(n, services[n])}
    if k8s_only:
        for n in k8s_only:
            del build_services[n]
        risks.append(f"已过滤 k8s 专属服务：{', '.join(sorted(k8s_only))}（含 K8S_/KUBECONFIG 环境变量）")

    if primary_name in build_services:
        primary_build_info = build_services[primary_name]
        build_args = dict(primary_build_info.get("build_args") or {})
        selected_dockerfile = source_root / str(primary_build_info["source_dockerfile_path"])

    custom_template_needed = False
    if selected_dockerfile:
        try:
            custom_template_needed = selected_dockerfile.relative_to(source_root) != Path("Dockerfile")
        except ValueError:
            custom_template_needed = True

    if build_services:
        build_strategy = "upstream_dockerfile"
        service_builds = list(build_services.values())
    elif primary_build:
        if selected_dockerfile and selected_dockerfile.exists() and custom_template_needed:
            build_strategy = "upstream_with_target_template"
            dockerfile_path = "Dockerfile.template"
            post_write[dockerfile_path] = selected_dockerfile.read_text(encoding="utf-8", errors="ignore")
        else:
            build_strategy = "upstream_dockerfile"
    elif primary_image:
        if is_version_like_tag(image_tag(primary_image)):
            build_strategy = "official_image"
            official_image_registry = image_repository(primary_image)
        elif selected_dockerfile and selected_dockerfile.exists():
            risks.append("主服务镜像 tag 不是可追踪版本，已回退为源码构建路线")
            if selected_dockerfile.name != "Dockerfile" or selected_dockerfile.parent != compose_file.parent:
                build_strategy = "upstream_with_target_template"
                dockerfile_path = "Dockerfile.template"
                post_write[dockerfile_path] = selected_dockerfile.read_text(encoding="utf-8", errors="ignore")
            else:
                build_strategy = "upstream_dockerfile"
        else:
            build_strategy = "official_image"
            official_image_registry = image_repository(primary_image)
            risks.append("主服务镜像 tag 不是 semver，后续自动更新可能需要人工介入")
    else:
        raise ValueError("无法从 compose 主服务推断 image/build 路线")

    primary_image_repo = image_repository(primary_image) if primary_image else ""
    upstream_submodules = detect_required_upstream_submodules(source_root, selected_dockerfile)

    for service_name, payload in services.items():
        if is_k8s_only_service(service_name, payload):
            continue
        service_payload: dict[str, Any] = {
            "image": f"registry.lazycat.cloud/placeholder/{slug}:{sanitize_token(service_name)}",
        }

        environment, env_items = extract_compose_environment(service_name, payload)
        env_docs.extend(resolve_compose_env_docs(env_items, env_defaults))
        if environment:
            resolved_env = resolve_compose_environment(environment, env_defaults)
            service_payload["environment"] = rewrite_public_url_envs(resolved_env, slug)

        binds: list[str] = []
        for volume in bm.ensure_list(payload.get("volumes")):
            # Pattern 5: relative :ro config file → content bind + copy source into content/
            content_bind, content_src = detect_content_bind(volume, compose_file)
            if content_bind:
                binds.append(content_bind)
                if content_src:
                    content_key = f"content/{content_src.name}"
                    if content_key not in post_write:
                        post_write[content_key] = content_src.read_text(encoding="utf-8", errors="ignore")
                continue
            bind, doc = parse_compose_volume(volume, slug, service_name)
            if bind:
                binds.append(bind)
            if doc:
                data_docs.append(doc)
        if binds:
            service_payload["binds"] = binds

        depends = compose_depends_on(payload)
        if frontend_gateway and service_name == primary_name:
            depends = []
        if depends:
            service_payload["depends_on"] = depends

        if payload.get("user"):
            service_payload["user"] = payload["user"]
        if payload.get("entrypoint"):
            service_payload["entrypoint"] = payload["entrypoint"]
        if payload.get("command"):
            service_payload["command"] = stringify_command(payload["command"])
        if payload.get("healthcheck"):
            service_payload["healthcheck"] = payload["healthcheck"]

        # Auto-generate setup_script for services that have content binds but no startup command.
        # Each content bind implies a file that must be copied into place before the service starts.
        if not service_payload.get("command") and not service_payload.get("entrypoint"):
            content_binds = [b for b in service_payload.get("binds", []) if b.startswith("/lzcapp/pkg/content/")]
            if content_binds:
                lines: list[str] = []
                seen_dirs: set[str] = set()
                for bind in content_binds:
                    src, dst = bind.split(":", 1)
                    dst_dir = str(Path(dst).parent)
                    if dst_dir != "/" and dst_dir not in seen_dirs:
                        lines.append(f"mkdir -p {dst_dir}")
                        seen_dirs.add(dst_dir)
                    lines.append(f"cp {src} {dst}")
                service_payload["setup_script"] = "\n".join(lines) + "\n"

        service_specs[service_name] = service_payload

        service_image = str(payload.get("image", "")).strip()
        if service_name == primary_name:
            if service_name in build_services:
                image_targets.append(service_name)
            elif service_image and is_well_known_public_image(service_image):
                # Public gateway image (nginx, caddy…) — treat as dependency, not build target
                dependencies.append({"target_service": service_name, "source_image": service_image})
            else:
                image_targets.append(service_name)
        elif service_image and primary_image_repo and image_repository(service_image) == primary_image_repo and build_strategy == "official_image":
            image_targets.append(service_name)
        elif service_image and service_name not in build_services:
            dependencies.append({"target_service": service_name, "source_image": service_image})

    # Ensure every build service appears in image_targets
    for svc_name in build_services:
        if svc_name not in image_targets:
            image_targets.append(svc_name)

    application = {
        "subdomain": slug,
        "public_path": ["/"],
        "upstreams": infer_compose_upstreams(
            primary_name,
            primary_port,
            services,
            frontend_gateway=frontend_gateway,
        ),
    }
    # Infer application-level health check from the primary service's compose healthcheck
    _primary_hc = service_specs.get(primary_name, {}).get("healthcheck") or {}
    _hc_url = _infer_health_check_url(_primary_hc.get("test"), primary_name, primary_port)
    if _hc_url:
        _n_services = sum(1 for n in services if not is_k8s_only_service(n, services[n]))
        application["health_check"] = {
            "test_url": _hc_url,
            "start_period": "300s" if _n_services > 3 else "60s",
        }

    version = str(meta.get("version", "") or "").strip()
    if not version and is_version_like_tag(image_tag(primary_image)):
        version = bm.normalize_semver(image_tag(primary_image))
    version = version or "0.1.0"

    startup_notes = [
        f"自动扫描到 compose 文件：{compose_file.relative_to(source_root) if compose_file.is_relative_to(source_root) else compose_file.name}",
        f"主服务推断为 `{primary_name}`，入口端口 `{primary_port}`。",
    ]
    if frontend_gateway:
        try:
            config_rel = frontend_gateway.config_path.relative_to(source_root)
        except ValueError:
            config_rel = frontend_gateway.config_path
        proxied_paths = ", ".join(frontend_gateway.locations)
        proxied_services = ", ".join(frontend_gateway.backend_services)
        startup_notes.append(
            "检测到主入口前端已在 "
            f"`{config_rel}` 里反代 {proxied_paths} 到 `{proxied_services}`，"
            "LazyCat 外层只保留 `/ -> frontend`，避免重复声明 `/api/` 导致路由语义偏移。"
        )
        startup_notes.append("已省略 frontend 对 backend 的 `depends_on`，避免平台把静态入口健康度耦合到后端启动时序。")
    if dependencies:
        startup_notes.append("依赖服务镜像已写入 dependencies，首次完整构建时会自动 copy-image。")

    return {
        "slug": slug,
        "project_name": str(meta.get("project_name") or bm.titleize_slug(slug)),
        "description": str(meta.get("description") or f"{slug} on LazyCat"),
        "description_zh": f"（迁移初稿）{bm.titleize_slug(slug)} 的懒猫微服版本",
        "upstream_repo": str(meta.get("upstream_repo", "")),
        "homepage": str(meta.get("homepage", "")),
        "license": str(meta.get("license") or ""),
        "author": str(meta.get("author") or "TODO"),
        "version": version,
        "check_strategy": str(meta.get("check_strategy", "github_release")),
        "build_strategy": build_strategy,
        "official_image_registry": official_image_registry,
        "dockerfile_path": dockerfile_path,
        "build_args": build_args,
        "service_port": primary_port,
        "image_targets": image_targets,
        "dependencies": dependencies,
        "service_builds": service_builds,
        "upstream_submodules": upstream_submodules,
        "services": service_specs,
        "application": application,
        "env_vars": dedupe_env_docs(env_docs),
        "data_paths": dedupe_data_paths(data_docs),
        "startup_notes": startup_notes,
        "include_content": any(k.startswith("content/") for k in post_write),
        "_risks": risks,
        "_post_write": post_write,
    }


def choose_route_for_dockerfile(
    slug: str,
    meta: dict[str, Any],
    source_root: Path,
    dockerfile_path: Path,
    env_files: list[Path],
) -> dict[str, Any]:
    ports = parse_dockerfile_ports(dockerfile_path)
    port = ports[0] if ports else 3000
    healthcheck = parse_dockerfile_healthcheck(dockerfile_path)
    data_paths = parse_dockerfile_volumes(dockerfile_path, slug, slug, source_root)

    build_strategy = "upstream_dockerfile"
    post_write: dict[str, str] = {}
    local_dockerfile_path = ""
    try:
        use_template = dockerfile_path.relative_to(source_root) != Path("Dockerfile")
    except ValueError:
        use_template = True
    if use_template:
        build_strategy = "upstream_with_target_template"
        local_dockerfile_path = "Dockerfile.template"
        post_write[local_dockerfile_path] = dockerfile_path.read_text(encoding="utf-8", errors="ignore")

    service = {
        slug: {
            "image": f"registry.lazycat.cloud/placeholder/{slug}:bootstrap",
        }
    }
    if healthcheck:
        service[slug]["healthcheck"] = healthcheck
    binds = [f"{entry['host']}:{entry['container']}" for entry in data_paths]
    if binds:
        service[slug]["binds"] = binds

    return {
        "slug": slug,
        "project_name": str(meta.get("project_name") or bm.titleize_slug(slug)),
        "description": str(meta.get("description") or f"{slug} on LazyCat"),
        "description_zh": f"（迁移初稿）{bm.titleize_slug(slug)} 的懒猫微服版本",
        "upstream_repo": str(meta.get("upstream_repo", "")),
        "homepage": str(meta.get("homepage", "")),
        "license": str(meta.get("license") or ""),
        "author": str(meta.get("author") or "TODO"),
        "version": str(meta.get("version") or "0.1.0"),
        "check_strategy": str(meta.get("check_strategy", "github_release")),
        "build_strategy": build_strategy,
        "dockerfile_path": local_dockerfile_path,
        "service_port": port,
        "image_targets": [slug],
        "services": service,
        "application": {
            "subdomain": slug,
            "public_path": ["/"],
            "upstreams": [{"location": "/", "backend": f"http://{slug}:{port}/"}],
        },
        "env_vars": parse_env_files(env_files),
        "data_paths": data_paths,
        "startup_notes": [
            f"自动扫描到 Dockerfile：{dockerfile_path.name}",
            "当前路线按源码构建处理，后续需确认真实入口、初始化命令和写路径。",
        ],
        "_risks": [],
        "_post_write": post_write,
    }


def render_frontend_nitro_dockerfile(frontend: FrontendAppInfo, source_dir: Path, upstream_repo: str) -> str:
    rel_app_root = frontend.app_root.relative_to(source_dir)
    app_root_ref = str(rel_app_root)
    install_root_ref = str(frontend.install_root.relative_to(source_dir))
    install_lines = {
        "pnpm": "RUN corepack enable \\\n    && corepack prepare pnpm@10.12.1 --activate \\\n    && pnpm install --frozen-lockfile \\\n    && " + frontend.build_command,
        "npm": "RUN npm ci \\\n    && " + frontend.build_command,
        "yarn": "RUN corepack enable \\\n    && yarn install --frozen-lockfile \\\n    && " + frontend.build_command,
    }
    build_section = install_lines[frontend.package_manager]
    return textwrap.dedent(
        f"""\
        FROM node:20-bookworm AS builder

        ARG UPSTREAM_REPO={upstream_repo or "TODO/TODO"}
        ARG UPSTREAM_REF=main
        ARG SOURCE_VERSION=unknown
        ARG BUILD_VERSION=0.1.0

        RUN apt-get update \\
            && apt-get install -y --no-install-recommends ca-certificates curl \\
            && rm -rf /var/lib/apt/lists/*

        WORKDIR /src

        RUN curl -fsSL "https://codeload.github.com/${{UPSTREAM_REPO}}/tar.gz/${{UPSTREAM_REF}}" \\
            | tar -xz --strip-components=1 -C /src

        WORKDIR /src/{install_root_ref}

        {build_section}

        FROM node:20-alpine

        ARG SOURCE_VERSION=unknown
        ARG BUILD_VERSION=0.1.0

        LABEL org.opencontainers.image.version="${{BUILD_VERSION}}" \\
              org.opencontainers.image.revision="${{SOURCE_VERSION}}"

        ENV NODE_ENV=production \\
            NITRO_HOST=0.0.0.0 \\
            NITRO_PORT={frontend.service_port} \\
            HOST=0.0.0.0 \\
            PORT={frontend.service_port}

        WORKDIR /app

        COPY --from=builder /src/{app_root_ref}/.output/ ./.output/

        EXPOSE {frontend.service_port}

        CMD ["node", ".output/server/index.mjs"]
        """
    ).strip() + "\n"


def render_frontend_static_dockerfile(frontend: FrontendAppInfo, source_dir: Path, upstream_repo: str) -> str:
    rel_app_root = frontend.app_root.relative_to(source_dir)
    app_root_ref = str(rel_app_root)
    install_root_ref = str(frontend.install_root.relative_to(source_dir))
    install_lines = {
        "pnpm": "RUN corepack enable \\\n    && corepack prepare pnpm@10.12.1 --activate \\\n    && pnpm install --frozen-lockfile \\\n    && " + frontend.build_command,
        "npm": "RUN npm ci \\\n    && " + frontend.build_command,
        "yarn": "RUN corepack enable \\\n    && yarn install --frozen-lockfile \\\n    && " + frontend.build_command,
    }
    build_section = install_lines[frontend.package_manager]
    return textwrap.dedent(
        f"""\
        FROM node:20-bookworm AS builder

        ARG UPSTREAM_REPO={upstream_repo or "TODO/TODO"}
        ARG UPSTREAM_REF=main
        ARG SOURCE_VERSION=unknown
        ARG BUILD_VERSION=0.1.0

        RUN apt-get update \\
            && apt-get install -y --no-install-recommends ca-certificates curl \\
            && rm -rf /var/lib/apt/lists/*

        WORKDIR /src

        RUN curl -fsSL "https://codeload.github.com/${{UPSTREAM_REPO}}/tar.gz/${{UPSTREAM_REF}}" \\
            | tar -xz --strip-components=1 -C /src

        WORKDIR /src/{install_root_ref}

        {build_section}

        FROM nginx:1.27-alpine

        ARG SOURCE_VERSION=unknown
        ARG BUILD_VERSION=0.1.0

        LABEL org.opencontainers.image.version="${{BUILD_VERSION}}" \\
              org.opencontainers.image.revision="${{SOURCE_VERSION}}"

        RUN rm -rf /usr/share/nginx/html/*

        COPY --from=builder /src/{app_root_ref}/dist/ /usr/share/nginx/html/

        EXPOSE 80

        CMD ["nginx", "-g", "daemon off;"]
        """
    ).strip() + "\n"


def choose_route_for_frontend(
    slug: str,
    meta: dict[str, Any],
    source_root: Path,
    frontend: FrontendAppInfo,
) -> dict[str, Any]:
    project_name = str(meta.get("project_name") or bm.titleize_slug(slug))
    if frontend.runtime == "nitro":
        dockerfile = render_frontend_nitro_dockerfile(frontend, source_root, str(meta.get("upstream_repo", "")))
    else:
        dockerfile = render_frontend_static_dockerfile(frontend, source_root, str(meta.get("upstream_repo", "")))

    notes = [
        frontend.rationale,
        f"构建目录：`{frontend.app_root.relative_to(source_root)}`；安装根目录：`{frontend.install_root.relative_to(source_root)}`。",
        f"自动推断构建命令：`{frontend.build_command}`。",
    ]
    if frontend.runtime == "nitro":
        notes.append("运行时按 Nitro Node server 封装，而不是把 `.output/public` 误当纯静态目录。")
    else:
        notes.append("运行时按静态站处理，由 nginx 托管构建产物目录。")

    return {
        "slug": slug,
        "project_name": project_name,
        "description": str(meta.get("description") or f"{slug} on LazyCat"),
        "description_zh": f"（迁移初稿）{project_name} 的懒猫微服前端版本",
        "upstream_repo": str(meta.get("upstream_repo", "")),
        "homepage": str(meta.get("homepage", "")),
        "license": str(meta.get("license") or ""),
        "author": str(meta.get("author") or "TODO"),
        "version": str(meta.get("version") or "0.1.0"),
        "check_strategy": str(meta.get("check_strategy") or "commit_sha"),
        "build_strategy": "target_repo_dockerfile",
        "dockerfile_path": "Dockerfile",
        "build_context": ".",
        "service_port": frontend.service_port,
        "image_targets": [f"{slug}-web"],
        "services": {
            f"{slug}-web": {
                "image": f"registry.lazycat.cloud/placeholder/{slug}:bootstrap",
            }
        },
        "application": {
            "subdomain": slug,
            "public_path": ["/"],
            "upstreams": [{"location": "/", "backend": f"http://{slug}-web:{frontend.service_port}/"}],
        },
        "env_vars": [],
        "data_paths": [],
        "startup_notes": notes,
        "_risks": [],
        "_post_write": {
            "Dockerfile": dockerfile,
        },
    }


def render_native_desktop_novnc_dockerfile(project_name: str) -> str:
    return f"""FROM debian:bookworm AS builder

ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \\
    ca-certificates \\
    build-essential \\
    cmake \\
    git \\
    pkg-config \\
    libssl-dev \\
    libmpv-dev \\
    libwebp-dev \\
    libglfw3-dev \\
    libglew-dev \\
    libgl1-mesa-dev \\
    libegl1-mesa-dev \\
    libx11-dev \\
    libxrandr-dev \\
    libxinerama-dev \\
    libxcursor-dev \\
    libxi-dev \\
    libdrm-dev \\
    libgbm-dev \\
    libwayland-dev \\
    libxkbcommon-dev \\
    libasound2-dev \\
    libpulse-dev \\
    libudev-dev \\
    libcurl4-openssl-dev \\
    libfmt-dev \\
    libtinyxml2-dev \\
    libopencc-dev \\
    zlib1g-dev && \\
    rm -rf /var/lib/apt/lists/*

WORKDIR /src
COPY . /src

RUN cmake -B build -DPLATFORM_DESKTOP=ON -DUSE_SHARED_LIB=OFF && \\
    jobs="$(nproc)"; \\
    if [ "$jobs" -gt 2 ]; then jobs=2; fi; \\
    cmake --build build -j"$jobs"

FROM debian:bookworm

ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \\
    xvfb \\
    x11vnc \\
    fluxbox \\
    novnc \\
    websockify \\
    supervisor \\
    libmpv2 \\
    libwebp7 \\
    libglfw3 \\
    libglew2.2 \\
    libgl1 \\
    libegl1 \\
    libx11-6 \\
    libxrandr2 \\
    libxinerama1 \\
    libxcursor1 \\
    libxi6 \\
    libdrm2 \\
    libgbm1 \\
    libwayland-client0 \\
    libxkbcommon0 \\
    libasound2 \\
    libpulse0 \\
    libudev1 \\
    libcurl4 \\
    libfmt9 \\
    libtinyxml2-9 \\
    libopencc1.1 \\
    zlib1g \\
    xdg-utils \\
    dbus-x11 \\
    fonts-dejavu-core \\
    fonts-noto-cjk && \\
    rm -rf /var/lib/apt/lists/*

WORKDIR /opt/{sanitize_token(project_name)}

COPY --from=builder /src/build/wiliwili /usr/local/bin/wiliwili
COPY --from=builder /src/resources ./resources

RUN mkdir -p /var/log/supervisor /tmp/.X11-unix

ENV DISPLAY=:0
ENV BRLS_RESOURCES=./resources/
EXPOSE 8080

RUN cat <<'EOF' >/usr/local/bin/start-wiliwili.sh
#!/bin/sh
set -eu
export DISPLAY=:0
cd /opt/{sanitize_token(project_name)}
exec /usr/local/bin/wiliwili
EOF

RUN cat <<'EOF' >/etc/supervisor/conf.d/wiliwili.conf
[supervisord]
nodaemon=true

[program:xvfb]
command=/usr/bin/Xvfb :0 -screen 0 1280x720x24 -ac +extension GLX +render -noreset
autorestart=true
priority=10

[program:fluxbox]
command=/usr/bin/fluxbox
environment=DISPLAY=":0"
autorestart=true
priority=20

[program:x11vnc]
command=/usr/bin/x11vnc -display :0 -forever -shared -nopw -listen 0.0.0.0 -xkb
autorestart=true
priority=30

[program:novnc]
command=/usr/share/novnc/utils/novnc_proxy --listen 8080 --vnc localhost:5900
autorestart=true
priority=40

[program:wiliwili]
command=/usr/local/bin/start-wiliwili.sh
autorestart=true
priority=50
startsecs=5
environment=DISPLAY=":0",BRLS_RESOURCES="./resources/"
directory=/opt/{sanitize_token(project_name)}
EOF

RUN chmod +x /usr/local/bin/start-wiliwili.sh

CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/wiliwili.conf"]
"""


def choose_route_for_native_desktop(
    slug: str,
    meta: dict[str, Any],
    dockerfile: Path | None,
    readmes: list[Path],
    reason: str,
) -> dict[str, Any]:
    project_name = str(meta.get("project_name") or bm.titleize_slug(slug))
    notes = [
        "检测到上游是原生桌面/掌机客户端，自动改走 noVNC 包装路线。",
        reason,
        "当前入口通过浏览器访问内置 noVNC 桌面，再启动 Linux 版客户端。",
    ]
    if dockerfile:
        notes.append(f"已忽略辅助/平台专用 Dockerfile：{dockerfile.name}")
    if readmes:
        notes.append(f"参考 README：{', '.join(path.name for path in readmes[:3])}")
    version = str(meta.get("version") or "0.1.0")
    return {
        "slug": slug,
        "project_name": project_name,
        "description": str(meta.get("description") or f"{slug} on LazyCat"),
        "description_zh": f"（迁移初稿）{project_name} 的懒猫微服桌面封装版本",
        "upstream_repo": str(meta.get("upstream_repo", "")),
        "homepage": str(meta.get("homepage", "")),
        "license": str(meta.get("license") or ""),
        "author": str(meta.get("author") or "TODO"),
        "version": version,
        "check_strategy": str(meta.get("check_strategy", "github_release")),
        "build_strategy": "upstream_with_target_template",
        "dockerfile_path": "Dockerfile.template",
        "service_port": 8080,
        "image_targets": [slug],
        "services": {
            slug: {
                "image": f"registry.lazycat.cloud/placeholder/{slug}:bootstrap",
                "healthcheck": {
                    "test": ["CMD-SHELL", "curl -f http://127.0.0.1:8080/ >/dev/null || exit 1"],
                    "interval": "30s",
                    "timeout": "10s",
                    "retries": 10,
                },
            }
        },
        "application": {
            "subdomain": slug,
            "public_path": ["/"],
            "upstreams": [{"location": "/", "backend": f"http://{slug}:8080/"}],
        },
        "env_vars": [],
        "data_paths": [],
        "startup_notes": notes,
        "_risks": [
            "这是原生 GUI 通过 noVNC 暴露的兼容路线，不是上游原生 Web 体验",
            "首次构建可能需要继续补齐桌面运行时依赖",
        ],
        "_post_write": {
            "Dockerfile.template": render_native_desktop_novnc_dockerfile(project_name),
        },
    }


def choose_route_for_binary(slug: str, meta: dict[str, Any], binary: dict[str, Any]) -> dict[str, Any]:
    return {
        "slug": slug,
        "project_name": str(meta.get("project_name") or bm.titleize_slug(slug)),
        "description": str(meta.get("description") or f"{slug} on LazyCat"),
        "description_zh": f"（迁移初稿）{bm.titleize_slug(slug)} 的懒猫微服版本",
        "upstream_repo": str(meta.get("upstream_repo", "")),
        "homepage": str(meta.get("homepage", "")),
        "license": str(meta.get("license") or ""),
        "author": str(meta.get("author") or "TODO"),
        "version": str(meta.get("version") or bm.normalize_semver(binary.get("tag_name") or "0.1.0")),
        "check_strategy": str(meta.get("check_strategy", "github_release")),
        "build_strategy": "precompiled_binary",
        "precompiled_binary_url": binary["url"],
        "service_cmd": [binary["binary_name"]],
        "service_port": 8080,
        "image_targets": [slug],
        "services": {
            slug: {
                "image": f"registry.lazycat.cloud/placeholder/{slug}:bootstrap",
            }
        },
        "application": {
            "subdomain": slug,
            "public_path": ["/"],
            "upstreams": [{"location": "/", "backend": f"http://{slug}:8080/"}],
        },
        "env_vars": [],
        "data_paths": [],
        "startup_notes": [
            "自动推断为 release binary 路线。",
            "当前只按通用单二进制服务处理，真实监听端口和启动参数仍需验收确认。",
        ],
        "_risks": ["release binary 的启动参数和真实监听端口尚未从上游文档确认"],
        "_post_write": {},
    }


def render_aipod_gateway_setup_script() -> str:
    return textwrap.dedent(
        """\
        cat <<'EOF' > /etc/caddy/Caddyfile
        {
                auto_https off
                http_port 80
                https_port 0
        }
        :80 {
                handle {
                        route {
                                lzcaipod
                                root * /lzcapp/pkg/content/ui/
                                try_files {path} /index.html
                                header Cache-Control "max-age=60, private, must-revalidate"
                                file_server
                        }
                }
        }
        EOF
        cat /etc/caddy/Caddyfile
        """
    ).strip()


def choose_route_for_gpu_aipod(
    slug: str,
    meta: dict[str, Any],
    gpu_info: dict[str, Any],
    official_image: dict[str, Any] | None,
) -> dict[str, Any]:
    project_name = str(meta.get("project_name") or bm.titleize_slug(slug))
    ai_service_name = slug
    ai_service_port = int(gpu_info.get("service_port") or 8000)
    ai_service_image = official_image["image"] if official_image else f"registry.lazycat.cloud/placeholder/{slug}-ai:bootstrap"
    return {
        "slug": slug,
        "project_name": project_name,
        "description": str(meta.get("description") or f"{slug} on LazyCat AIPod"),
        "description_zh": f"（迁移初稿）{project_name} 的懒猫微服 + 算力舱版本",
        "upstream_repo": str(meta.get("upstream_repo", "")),
        "homepage": str(meta.get("homepage", "")),
        "license": str(meta.get("license") or ""),
        "author": str(meta.get("author") or "TODO"),
        "version": str(meta.get("version") or "0.1.0"),
        "check_strategy": str(meta.get("check_strategy", "github_release")),
        "build_strategy": "official_image",
        "official_image_registry": DEFAULT_AIPOD_GATEWAY_IMAGE,
        "service_port": 80,
        "image_targets": ["gateway"],
        "services": {
            "gateway": {
                "image": "registry.lazycat.cloud/placeholder/gateway:bootstrap",
                "setup_script": render_aipod_gateway_setup_script(),
                "healthcheck": {
                    "test": ["CMD-SHELL", "curl -f http://127.0.0.1:80/ >/dev/null || exit 1"],
                    "interval": "30s",
                    "timeout": "10s",
                    "retries": 10,
                },
            }
        },
        "application": {
            "subdomain": slug,
            "public_path": ["/"],
            "upstreams": [{"location": "/", "backend": "http://gateway:80/"}],
        },
        "include_content": True,
        "ai_pod_service": "./ai-pod-service",
        "ai_pod_service_name": ai_service_name,
        "ai_pod_service_port": ai_service_port,
        "ai_pod_image": ai_service_image,
        "aipod": {"shortcut": {"disable": False}},
        "usage": "此应用需结合算力舱使用。",
        "env_vars": [],
        "data_paths": [],
        "startup_notes": [
            gpu_info["reason"],
            "已自动改走 AIPod 骨架：微服侧保留 gateway/content，GPU 推理服务迁到 ai-pod-service。",
            f"当前 AI 服务预估端口为 {ai_service_port}，预期域名为 https://{ai_service_name}-ai.{{{{ .S.BoxDomain }}}} 。",
            "若上游没有公开官方镜像，需后续手动补齐 ai-pod-service/docker-compose.yml 的真实镜像与启动命令。",
        ],
        "_risks": [
            "当前只生成 AIPod 初稿骨架，真实 GPU 服务镜像、命令、挂载与代理仍需继续补齐",
        ],
        "_post_write": {},
    }


def choose_route_for_image(source: str) -> dict[str, Any]:
    raw = source.strip()
    slug = sanitize_token(image_repository(raw).split("/")[-1])
    tag = image_tag(raw)
    version = bm.normalize_semver(tag) if is_version_like_tag(tag) else "0.1.0"
    risks = []
    if not is_version_like_tag(tag):
        risks.append("镜像 tag 不是 semver，后续自动更新可能需要人工指定版本")
    return {
        "slug": slug,
        "project_name": bm.titleize_slug(slug),
        "description": f"{slug} on LazyCat",
        "description_zh": f"（迁移初稿）{bm.titleize_slug(slug)} 的懒猫微服版本",
        "upstream_repo": "",
        "homepage": "",
        "license": "TODO",
        "author": "TODO",
        "version": version,
        "check_strategy": "github_tag",
        "build_strategy": "official_image",
        "official_image_registry": image_repository(raw),
        "service_port": 80,
        "image_targets": [slug],
        "services": {
            slug: {
                "image": f"registry.lazycat.cloud/placeholder/{slug}:bootstrap",
            }
        },
        "application": {
            "subdomain": slug,
            "public_path": ["/"],
            "upstreams": [{"location": "/", "backend": f"http://{slug}:80/"}],
        },
        "env_vars": [],
        "data_paths": [],
        "startup_notes": ["当前输入是镜像地址，端口/环境变量/写路径还需要后续验收补齐。"],
        "_risks": risks,
        "_post_write": {},
    }


def analyze_source(normalized: NormalizedSource, source_dir: Path | None, gh_token: str = "") -> AnalysisResult:
    upstream_repo = normalized.upstream_repo
    repo_name = upstream_repo.split("/", 1)[1] if upstream_repo else ""
    slug = bm.normalize_slug(repo_name or Path(normalized.source).stem or normalized.source.split("/")[-1])

    meta = bm.fetch_upstream_metadata(upstream_repo, "github_release", gh_token) if upstream_repo else {}
    # Fork repos rarely publish releases; default to commit_sha tracking.
    # If it's a fork and metadata is sparse, fall back to the parent repo's metadata.
    is_fork = meta.get("is_fork", False)
    # Use commit_sha for forks and repos with no releases/tags
    has_releases = bool(meta.get("version") or meta.get("source_version"))
    default_check_strategy = "commit_sha" if (is_fork or not has_releases) else "github_release"
    if is_fork and upstream_repo and (not meta.get("version") or not meta.get("description")):
        parent_meta = bm.github_api_json(f"repos/{upstream_repo}")
        parent_repo = ""
        if isinstance(parent_meta, dict) and isinstance(parent_meta.get("parent"), dict):
            parent_repo = str(parent_meta["parent"].get("full_name", ""))
        if parent_repo:
            parent_info = bm.fetch_upstream_metadata(parent_repo, "github_release", gh_token)
            # Fill in missing fields from parent
            for key in ("version", "description", "license", "author", "source_version", "homepage"):
                if not meta.get(key) and parent_info.get(key):
                    meta[key] = parent_info[key]
    meta.update({
        "upstream_repo": upstream_repo,
        "homepage": meta.get("homepage") or normalized.homepage,
        "check_strategy": default_check_strategy,
    })

    if normalized.kind == "docker_image":
        spec = choose_route_for_image(normalized.source)
        spec["slug"] = slug or spec["slug"]
        return AnalysisResult(
            slug=spec["slug"],
            route=spec["build_strategy"],
            spec=spec,
            risks=list(spec["_risks"]),
        )

    assert source_dir is not None
    compose_file = select_compose_file(source_dir)
    dockerfile = select_dockerfile(source_dir)
    env_files = list_env_files(source_dir)
    readmes = list_readmes(source_dir)
    frontend_app = detect_frontend_app(source_dir)
    native_project_reason = detect_non_service_native_project(source_dir, compose_file, dockerfile, readmes)
    gpu_first_reason = detect_gpu_first_ml_project(source_dir, compose_file, dockerfile, readmes)
    official_image = detect_official_image_from_readmes(readmes)
    binary = parse_release_binary_candidate(upstream_repo) if upstream_repo else None

    if compose_file:
        compose = load_yaml(compose_file)
        services = compose.get("services") if isinstance(compose, dict) else {}
        if (
            isinstance(services, dict)
            and is_probably_dev_compose(services)
            and official_image
        ):
            spec = choose_route_for_official_image(
                slug,
                meta,
                official_image["image"],
                official_image["port"],
                f"检测到开发用 compose，已优先采用 README 中的官方镜像运行方式（来源：{official_image['source']}）。",
            )
            spec["_risks"] = ["根目录 compose 更像开发环境，已跳过其服务拆分结果"]
        elif (
            isinstance(services, dict)
            and is_probably_dev_compose(services)
            and binary
        ):
            spec = choose_route_for_binary(slug, meta, binary)
            spec["_risks"] = ["根目录 compose 更像开发环境，已优先采用 release binary 路线"]
            spec["startup_notes"] = bm.ensure_list(spec.get("startup_notes")) + [
                f"检测到开发用 compose，已跳过其服务拆分结果（compose={compose_file.name}）。"
            ]
        else:
            spec = choose_route_for_compose(slug, meta, source_dir, compose_file, dockerfile, env_files)
    elif native_project_reason:
        raise ValueError(native_project_reason)
    elif gpu_first_reason:
        spec = choose_route_for_gpu_aipod(slug, meta, gpu_first_reason, official_image)
    elif dockerfile:
        spec = choose_route_for_dockerfile(slug, meta, source_dir, dockerfile, env_files)
    elif frontend_app:
        spec = choose_route_for_frontend(slug, meta, source_dir, frontend_app)
    elif upstream_repo:
        if binary:
            spec = choose_route_for_binary(slug, meta, binary)
        else:
            raise ValueError("未发现 compose、Dockerfile、可识别的前端应用或 release binary")
    else:
        raise ValueError("当前输入不是 GitHub 仓库，也没有可分析的 compose/Dockerfile")

    env_from_files = parse_env_files(env_files)
    resolved_source_names = {
        str(entry.get("source_name", "")).strip()
        for entry in bm.ensure_list(spec.get("env_vars"))
        if isinstance(entry, dict) and str(entry.get("source_name", "")).strip()
    }
    existing_env_names = {
        entry.get("name")
        for entry in bm.ensure_list(spec.get("env_vars"))
        if isinstance(entry, dict)
    }
    spec["env_vars"] = bm.ensure_list(spec.get("env_vars")) + [
        item for item in env_from_files
        if item.get("name") not in existing_env_names and item.get("name") not in resolved_source_names
    ]
    spec["startup_notes"] = bm.ensure_list(spec.get("startup_notes")) + [
        f"扫描到 env 示例文件：{', '.join(path.name for path in env_files[:3])}" if env_files else "未扫描到 env 示例文件",
        f"扫描到 README：{', '.join(path.name for path in readmes[:3])}" if readmes else "未扫描到 README",
    ]
    discovered_icon = bm.discover_repo_icon(source_dir)
    if discovered_icon and not str(spec.get("icon_path") or "").strip():
        spec["icon_path"] = str(discovered_icon)
        try:
            icon_label = discovered_icon.relative_to(source_dir).as_posix()
        except ValueError:
            icon_label = str(discovered_icon)
        spec["startup_notes"] = bm.ensure_list(spec.get("startup_notes")) + [
            f"扫描到上游图标：{icon_label}"
        ]

    return AnalysisResult(
        slug=spec["slug"],
        route=spec["build_strategy"],
        spec=spec,
        compose_file=compose_file,
        dockerfile=dockerfile,
        env_files=env_files,
        readmes=readmes,
        risks=list(spec.get("_risks", [])),
    )


def apply_post_write(repo_root: Path, slug: str, post_write: dict[str, str]) -> list[str]:
    outputs: list[str] = []
    app_dir = repo_root / "apps" / slug
    for relative, content in post_write.items():
        path = app_dir / relative
        if path.exists():
            outputs.append(str(path))
            continue  # preserve hand-tuned static content
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        outputs.append(str(path))
    return outputs


def load_app_profile(repo_root: Path, slug: str) -> dict[str, Any] | None:
    """Load .app-profile.json for an app if it exists."""
    profile_path = repo_root / "apps" / slug / ".app-profile.json"
    if not profile_path.exists():
        return None
    return json.loads(profile_path.read_text(encoding="utf-8"))


_PROFILE_GENERATED_FIELDS: frozenset[str] = frozenset({
    "project_name", "description", "description_zh", "license", "homepage", "author",
    "build_strategy", "check_strategy", "official_image_registry", "docker_platform",
    "dockerfile_path", "dockerfile_type", "build_context", "overlay_paths",
    "image_name", "service_port", "service_cmd", "image_targets",
    "dependencies", "service_builds", "build_args",
    "precompiled_binary_url", "upstream_submodules",
    "deploy_param_sync", "image_owner", "package",
    "official_image_fallback_tag", "repo",
    "application", "services", "env_vars", "data_paths",
    "include_content", "startup_notes", "usage",
})


def generate_app_profile(finalized: dict[str, Any]) -> dict[str, Any]:
    """Serialise the compose-analysis result as a .app-profile.json skeleton.

    Only persists fields that represent meaningful, reusable decisions — not
    ephemeral state like version, image refs, or runtime risks.
    """
    fixes = {
        k: v for k, v in finalized.items()
        if k in _PROFILE_GENERATED_FIELDS
        and v is not None and v != "" and v != [] and v != {}
    }

    # Do not emit env_vars entries that do not have an explicit non-empty 'value'.
    # This prevents generating profiles that claim to set variables without a concrete value.
    if "env_vars" in fixes and isinstance(fixes["env_vars"], list):
        filtered_env: list[Any] = []
        for entry in fixes["env_vars"]:
            # Preserve non-dict entries as-is (backwards compatibility)
            if not isinstance(entry, dict):
                filtered_env.append(entry)
                continue
            # Require an explicit non-empty 'value' to be present
            if "value" not in entry:
                continue
            val = entry.get("value")
            if val is None:
                continue
            if isinstance(val, str) and val.strip() == "":
                continue
            filtered_env.append(entry)
        if filtered_env:
            fixes["env_vars"] = filtered_env
        else:
            fixes.pop("env_vars", None)

    return {
        "managed_by": "full_migrate",
        "generated_from_upstream": str(finalized.get("upstream_repo") or ""),
        "fixes": fixes,
    }


def is_generated_app_profile(profile: dict[str, Any]) -> bool:
    if not isinstance(profile, dict):
        return False
    allowed_top_level = {"managed_by", "generated_from_upstream", "fixes", "content_files", "deploy_params_file"}
    if any(key not in allowed_top_level for key in profile):
        return False
    fixes = profile.get("fixes")
    if not isinstance(fixes, dict):
        return False
    return all(key in _PROFILE_GENERATED_FIELDS for key in fixes)


def refresh_generated_app_profile(existing: dict[str, Any], finalized: dict[str, Any]) -> dict[str, Any]:
    refreshed = generate_app_profile(finalized)
    for key in ("content_files", "deploy_params_file"):
        if key in existing:
            refreshed[key] = existing[key]
    return refreshed


def apply_app_profile_fixes(finalized: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    """Apply fixes from .app-profile.json to the finalized spec."""
    fixes = profile.get("fixes", {})
    for key, value in fixes.items():
        finalized[key] = value
    # If profile declares static content files, force include_content on
    if profile.get("content_files", {}).get("static"):
        finalized["include_content"] = True
    return finalized


def apply_app_post_process(repo_root: Path, finalized: dict[str, Any], analysis: AnalysisResult) -> list[str]:
    slug = finalized["slug"]
    upstream_repo = str(finalized.get("upstream_repo") or analysis.spec.get("upstream_repo") or "").strip()

    # Check for .app-profile.json with static content
    profile = load_app_profile(repo_root, slug)
    if profile and profile.get("content_files", {}).get("static"):
        # Content files are maintained as static templates in the app directory.
        # Collect paths of static files that exist (content/, deploy params, etc.)
        outputs: list[str] = []
        app_dir = repo_root / "apps" / slug
        # Report existing content files
        content_dir = app_dir / "content"
        if content_dir.is_dir():
            for f in sorted(content_dir.rglob("*")):
                if f.is_file():
                    outputs.append(str(f))
        # Report deploy params if present
        deploy_params_file = profile.get("deploy_params_file")
        if deploy_params_file:
            params_path = app_dir / deploy_params_file
            if params_path.exists():
                outputs.append(str(params_path))
        return outputs

    if matches_basic_llm_dotenv_profile(finalized, analysis):
        return post_process_basic_llm_dotenv(repo_root, finalized["slug"])
    return []


def set_deploy_param_sync_profile(
    finalized: dict[str, Any],
    *,
    script_relpath: str,
    targets: list[str],
) -> None:
    finalized["deploy_param_sync"] = {
        "script_relpath": script_relpath,
        "targets": list(dict.fromkeys(str(item).strip() for item in targets if str(item).strip())),
    }


def render_deploy_param_sync_note(finalized: dict[str, Any]) -> str | None:
    payload = finalized.get("deploy_param_sync")
    if not isinstance(payload, dict):
        return None
    targets = [str(item).strip() for item in bm.ensure_list(payload.get("targets")) if str(item).strip()]
    if not targets:
        return None
    rendered = " 和 ".join(f"`{item}`" for item in targets)
    return f"服务启动前会读取部署参数，并同步写回 {rendered}。"


def apply_generated_app_fixes(finalized: dict[str, Any], analysis: AnalysisResult) -> dict[str, Any]:
    upstream_repo = str(finalized.get("upstream_repo") or analysis.spec.get("upstream_repo") or "").strip()

    if upstream_repo == "mudler/LocalAI":
        finalized["build_strategy"] = "official_image"
        finalized["official_image_registry"] = "docker.io/localai/localai"
        finalized["image_targets"] = ["api"]
        finalized["dependencies"] = []
        finalized.pop("service_builds", None)
        finalized.pop("build_args", None)
        finalized.pop("docker_platform", None)
        finalized.pop("upstream_submodules", None)
        services = finalized.get("services")
        if isinstance(services, dict):
            api = services.get("api")
            if isinstance(api, dict):
                # Upstream compose uses `phi-2` as a quickstart example. Keeping it
                # as the packaged command makes first boot try and fail to import
                # a model, so default to an empty persistent model directory.
                if stringify_command(api.get("command")).strip() == "phi-2":
                    api.pop("command", None)
        startup_notes = finalized.setdefault("startup_notes", [])
        note = "上游 compose 的 `command: phi-2` 是示例模型参数，默认安装不预置模型；模型文件和配置由 `/models`、`/configuration` 持久化目录管理。"
        if note not in startup_notes:
            startup_notes.append(note)

    if (
        str(finalized.get("build_strategy", "")).strip() in SOURCE_BUILD_STRATEGIES
        or bool(finalized.get("service_builds"))
    ) and not str(finalized.get("docker_platform", "")).strip():
        finalized["docker_platform"] = "linux/amd64"

    if finalized.get("slug") == "cmms" and upstream_repo == "Grashjs/cmms":
        frontend = finalized.get("services", {}).get("frontend")
        if isinstance(frontend, dict):
            frontend_env = [str(item) for item in frontend.get("environment", [])]
            frontend["command"] = build_runtime_env_file_command(
                frontend_env,
                workdir="/usr/share/nginx/html",
                env_file="./.env",
                env_config="./runtime-env.js",
                final_cmd='exec nginx -g "daemon off;"',
            )
        startup_notes = finalized.setdefault("startup_notes", [])
        note = "frontend 启动前会先按容器环境重写 .env，再以 NODE_ENV=development 执行 runtime-env-cra，避免空字符串变量被判定为缺失。"
        if note not in startup_notes:
            startup_notes.append(note)


    if matches_basic_llm_dotenv_profile(finalized, analysis):
        apply_persisted_env_service_profile(
            finalized,
            service_name=finalized.get("slug", "app"),
            state_slug=finalized.get("slug", "app"),
            state_env_prefix=slug_to_env_prefix(finalized.get("slug", "app")),
            note_prefix="LLM",
            note_description="检测到应用要求通过 `.env` 提供 LLM_PROVIDER / credentials；迁移器已强制接入 Deployment Parameters，并在启动前把这些值写入持久化 `.env`。",
        )

    return finalized


def render_config_ui_server() -> str:
    return textwrap.dedent(
        """\
        import http from "node:http";
        import { access, mkdir, readFile, writeFile } from "node:fs/promises";
        import { constants as fsConstants } from "node:fs";
        import { dirname } from "node:path";
        import { execFile } from "node:child_process";
        import { promisify } from "node:util";

        const execFileAsync = promisify(execFile);
        const port = Number(process.env.PORT || 3210);
        const appName = process.env.CONFIG_UI_APP_NAME || "Application";
        const schemaPath = process.env.CONFIG_UI_SCHEMA_PATH || "";
        const statePath = process.env.CONFIG_UI_STATE_PATH || "";
        const readyMarker = process.env.CONFIG_UI_READY_MARKER || "";
        const renderCommand = process.env.CONFIG_UI_RENDER_COMMAND || "";
        const settingsPath = process.env.CONFIG_UI_SETTINGS_PATH || "/settings/config";

        function escapeHtml(value) {
          return String(value)
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#39;");
        }

        async function readText(path) {
          if (!path) return "";
          return readFile(path, "utf8").catch(() => "");
        }

        async function writeText(path, content) {
          await mkdir(dirname(path), { recursive: true });
          await writeFile(path, content, "utf8");
        }

        async function fileExists(path) {
          if (!path) return false;
          try {
            await access(path, fsConstants.F_OK);
            return true;
          } catch {
            return false;
          }
        }

        function parseEnvFile(raw) {
          const result = {};
          for (const line of String(raw || "").split(/\\r?\\n/)) {
            const trimmed = line.trim();
            if (!trimmed || trimmed.startsWith("#")) continue;
            const match = trimmed.match(/^([A-Za-z_][A-Za-z0-9_]*)=(.*)$/);
            if (!match) continue;
            let value = match[2] || "";
            if ((value.startsWith("'") && value.endsWith("'")) || (value.startsWith('"') && value.endsWith('"'))) {
              value = value.slice(1, -1);
            }
            value = value.replace(/'\\\\''/g, "'");
            result[match[1]] = value;
          }
          return result;
        }

        function shellQuote(value) {
          return `'${String(value || "").replaceAll("'", `'\\\\''`)}'`;
        }

        async function loadSchema() {
          const raw = await readText(schemaPath);
          return JSON.parse(raw || "{}");
        }

        function findProvider(schema, providerId) {
          return (schema.providers || []).find((item) => item.id === providerId) || null;
        }

        function findModel(provider, modelPreset) {
          return (provider?.models || []).find((item) => item.id === modelPreset) || null;
        }

        function deriveInitialValues(schema, persisted) {
          const providerId = persisted.DEER_FLOW_MODEL_PROVIDER_PRESET || process.env.DEER_FLOW_MODEL_PROVIDER_PRESET || schema.defaultProvider || schema.providers?.[0]?.id || "";
          const provider = findProvider(schema, providerId) || schema.providers?.[0] || null;
          const modelPresetFromState = persisted.DEER_FLOW_MODEL_PRESET || "";
          const modelPresetFromEnv = provider?.models?.find((item) => item.modelId === (process.env.DEER_FLOW_MODEL_ID || ""))?.id || "";
          const providerApiKey = provider?.id === "openrouter"
            ? (persisted.OPENROUTER_API_KEY || process.env.OPENROUTER_API_KEY || "")
            : (persisted.OPENAI_API_KEY || process.env.OPENAI_API_KEY || "");
          const modelPreset = modelPresetFromState || modelPresetFromEnv || provider?.defaultModel || provider?.models?.[0]?.id || "";
          const selectedModel = findModel(provider, modelPreset) || provider?.models?.[0] || null;
          return {
            provider: provider?.id || "",
            modelPreset,
            baseUrl: persisted.DEER_FLOW_MODEL_BASE_URL || process.env.DEER_FLOW_MODEL_BASE_URL || provider?.baseUrl || "",
            apiKey: providerApiKey || persisted.DEER_FLOW_MODEL_API_KEY || process.env.DEER_FLOW_MODEL_API_KEY || "",
            tavilyApiKey: persisted.TAVILY_API_KEY || process.env.TAVILY_API_KEY || "",
            jinaApiKey: persisted.JINA_API_KEY || process.env.JINA_API_KEY || "",
          };
        }

        function validateAndMaterialize(schema, submitted) {
          const provider = findProvider(schema, submitted.provider);
          if (!provider) {
            throw new Error("Pick a supported provider preset.");
          }
          const model = findModel(provider, submitted.modelPreset);
          if (!model) {
            throw new Error("Pick a supported model preset.");
          }
          if (!String(submitted.apiKey || "").trim()) {
            throw new Error("API Key is required before DeerFlow can start.");
          }
          const submittedBaseUrl = String(submitted.baseUrl || "").trim();
          const resolvedBaseUrl = submittedBaseUrl || provider.baseUrl || "";
          if (provider.requiresBaseUrl && !resolvedBaseUrl) {
            throw new Error("Base URL is required for the custom OpenAI-compatible provider.");
          }
          return {
            DEER_FLOW_MODEL_PROVIDER_PRESET: provider.id,
            DEER_FLOW_MODEL_PRESET: model.id,
            DEER_FLOW_MODEL_NAME: model.name,
            DEER_FLOW_MODEL_DISPLAY_NAME: model.displayName,
            DEER_FLOW_MODEL_ID: model.modelId,
            DEER_FLOW_MODEL_BASE_URL: resolvedBaseUrl,
            DEER_FLOW_MODEL_USE_RESPONSES_API: model.useResponsesApi ? "true" : "false",
            DEER_FLOW_MODEL_TEMPERATURE: String(model.temperature ?? "0.7"),
            DEER_FLOW_MODEL_API_KEY: String(submitted.apiKey || "").trim(),
            OPENAI_API_KEY: provider.id === "openrouter" ? "" : String(submitted.apiKey || "").trim(),
            OPENROUTER_API_KEY: provider.id === "openrouter" ? String(submitted.apiKey || "").trim() : "",
            TAVILY_API_KEY: String(submitted.tavilyApiKey || "").trim(),
            JINA_API_KEY: String(submitted.jinaApiKey || "").trim(),
          };
        }

        async function saveState(envMap) {
          const lines = [
            "# Generated by LazyCat config-ui.",
            ...Object.entries(envMap).map(([key, value]) => `${key}=${shellQuote(value)}`),
            "",
          ];
          await writeText(statePath, lines.join("\\n"));
        }

        async function runRender() {
          if (!renderCommand) return;
          await execFileAsync("sh", ["-lc", renderCommand], {
            env: process.env,
            timeout: 30000,
          });
        }

        async function buildPayload() {
          const schema = await loadSchema();
          const persisted = parseEnvFile(await readText(statePath));
          const values = deriveInitialValues(schema, persisted);
          return {
            schema,
            values,
            ready: await fileExists(readyMarker),
          };
        }

        function renderPage(payload) {
          return `<!doctype html>
        <html lang="en">
        <head>
          <meta charset="utf-8">
          <meta name="viewport" content="width=device-width, initial-scale=1">
          <title>${escapeHtml(payload.schema.title || `Configure ${appName}`)}</title>
          <style>
            :root { --bg:#050816; --bg-2:#0b1124; --panel:rgba(8,16,34,.82); --line:rgba(96,165,250,.24); --line-2:rgba(45,212,191,.18); --text:#e5f0ff; --muted:#8aa0c4; --accent:#4fd1ff; --accent-2:#8b5cf6; --ok:#37f0b0; --warn:#ffb84d; }
            * { box-sizing:border-box; }
            body { margin:0; min-height:100vh; font-family: ui-sans-serif, system-ui, sans-serif; background:radial-gradient(circle at top, rgba(79,209,255,.16) 0%, transparent 28%), radial-gradient(circle at right, rgba(139,92,246,.18) 0%, transparent 24%), linear-gradient(180deg, var(--bg) 0%, var(--bg-2) 100%); color:var(--text); }
            body::before { content:""; position:fixed; inset:0; pointer-events:none; background-image:linear-gradient(rgba(79,209,255,.06) 1px, transparent 1px), linear-gradient(90deg, rgba(79,209,255,.06) 1px, transparent 1px); background-size:32px 32px; mask-image:linear-gradient(180deg, rgba(0,0,0,.5), transparent); }
            .wrap { max-width:960px; margin:0 auto; padding:40px 20px 56px; position:relative; z-index:1; }
            .hero { margin-bottom:24px; }
            .hero h1 { margin:0 0 12px; font-size:40px; letter-spacing:.02em; text-transform:uppercase; }
            .hero p { margin:0; max-width:720px; line-height:1.7; color:var(--muted); }
            .panel { background:linear-gradient(180deg, rgba(12,20,40,.88), rgba(7,13,28,.92)); border:1px solid var(--line); border-radius:28px; padding:24px; box-shadow:0 0 0 1px rgba(79,209,255,.08) inset, 0 24px 90px rgba(2,8,23,.55); backdrop-filter:blur(18px); }
            .status { margin-bottom:18px; padding:14px 16px; border-radius:16px; background:rgba(55,240,176,.08); color:var(--ok); border:1px solid rgba(55,240,176,.24); font-weight:600; box-shadow:0 0 24px rgba(55,240,176,.08) inset; }
            .grid { display:grid; grid-template-columns:repeat(auto-fit, minmax(240px, 1fr)); gap:16px; }
            label { display:block; font-size:12px; font-weight:700; margin-bottom:8px; letter-spacing:.12em; text-transform:uppercase; color:#c8dbff; }
            .field { margin-bottom:16px; }
            select, input { width:100%; min-height:48px; border-radius:16px; border:1px solid var(--line); padding:0 14px; background:rgba(5,12,26,.88); color:var(--text); outline:none; box-shadow:0 0 0 1px transparent inset; }
            select:focus, input:focus { border-color:rgba(79,209,255,.55); box-shadow:0 0 0 1px rgba(79,209,255,.32), 0 0 24px rgba(79,209,255,.12); }
            input:disabled { color:#6e82a6; border-color:rgba(96,165,250,.12); }
            .hint { margin-top:6px; font-size:12px; color:var(--muted); }
            .actions { display:flex; gap:12px; align-items:center; margin-top:8px; flex-wrap:wrap; }
            button { min-height:48px; padding:0 22px; border:1px solid rgba(79,209,255,.3); border-radius:999px; background:linear-gradient(90deg, rgba(79,209,255,.18), rgba(139,92,246,.2)); color:#f7fbff; font-weight:700; letter-spacing:.06em; text-transform:uppercase; cursor:pointer; box-shadow:0 0 20px rgba(79,209,255,.16); }
            button.secondary { background:rgba(8,16,34,.7); color:#b7cbef; border-color:rgba(96,165,250,.22); box-shadow:none; }
            .inline { display:flex; gap:12px; flex-wrap:wrap; }
            .pill { display:inline-flex; align-items:center; min-height:38px; padding:0 14px; border-radius:999px; background:rgba(12,24,48,.88); border:1px solid var(--line-2); color:#bdefff; font-size:13px; box-shadow:0 0 18px rgba(45,212,191,.08) inset; }
            @media (max-width: 640px) { .hero h1 { font-size:32px; } .panel { padding:18px; border-radius:22px; } }
          </style>
        </head>
        <body>
          <main class="wrap">
            <section class="hero">
              <h1>${escapeHtml(payload.schema.title || `Configure ${appName}`)}</h1>
              <p>${escapeHtml(payload.schema.description || "Choose a provider preset and default model before starting the app.")}</p>
            </section>
            <section class="panel">
              <div id="status" class="status">${payload.ready ? "Configuration found. You can update it here at any time." : "Configuration is required before DeerFlow can start."}</div>
              <div class="grid">
                <div class="field">
                  <label for="provider">Provider</label>
                  <select id="provider"></select>
                  <div class="hint">Hosted presets supported by this package. The base URL is filled automatically.</div>
                </div>
                <div class="field">
                  <label for="modelPreset">Default Model</label>
                  <select id="modelPreset"></select>
                  <div id="modelHint" class="hint"></div>
                </div>
              </div>
              <div class="grid">
                <div class="field">
                  <label for="apiKey">API Key</label>
                  <input id="apiKey" type="password" autocomplete="off" placeholder="Paste the provider API key">
                  <div class="hint">Stored in the app data directory and exposed as <code>OPENAI_API_KEY</code> or <code>OPENROUTER_API_KEY</code>, depending on the selected provider.</div>
                </div>
                <div class="field">
                  <label for="baseUrl">Base URL</label>
                  <input id="baseUrl" type="url" autocomplete="off" placeholder="Required for custom OpenAI-compatible endpoints">
                  <div id="baseUrlHint" class="hint">Automatically filled for presets like OpenRouter. Required for custom endpoints.</div>
                </div>
              </div>
              <div class="grid">
                <div class="field">
                  <label for="tavilyApiKey">Tavily API Key</label>
                  <input id="tavilyApiKey" type="password" autocomplete="off" placeholder="Optional search key">
                  <div class="hint">Optional. Enables DeerFlow web search.</div>
                </div>
                <div class="field">
                  <label for="jinaApiKey">Jina API Key</label>
                  <input id="jinaApiKey" type="password" autocomplete="off" placeholder="Optional fetch key">
                  <div class="hint">Optional. Enables DeerFlow web fetch.</div>
                </div>
                <div class="field">
                  <label>Resolved Profile</label>
                  <div id="resolved" class="inline"></div>
                </div>
              </div>
              <div class="actions">
                <button id="save" type="button">${escapeHtml(payload.schema.submitLabel || "Save and Start")}</button>
                <button id="openApp" class="secondary" type="button">Open App</button>
              </div>
            </section>
          </main>
          <script>
            const schema = __SCHEMA_JSON__;
            const initialValues = __VALUES_JSON__;
            const providerEl = document.getElementById("provider");
            const modelEl = document.getElementById("modelPreset");
            const apiKeyEl = document.getElementById("apiKey");
            const baseUrlEl = document.getElementById("baseUrl");
            const baseUrlHintEl = document.getElementById("baseUrlHint");
            const tavilyEl = document.getElementById("tavilyApiKey");
            const jinaEl = document.getElementById("jinaApiKey");
            const modelHintEl = document.getElementById("modelHint");
            const resolvedEl = document.getElementById("resolved");
            const statusEl = document.getElementById("status");

            function currentProvider() {
              return schema.providers.find((item) => item.id === providerEl.value) || schema.providers[0];
            }

            function currentModel() {
              const provider = currentProvider();
              return (provider.models || []).find((item) => item.id === modelEl.value) || provider.models[0];
            }

            function updateProviderOptions() {
              providerEl.innerHTML = "";
              for (const provider of schema.providers || []) {
                const option = document.createElement("option");
                option.value = provider.id;
                option.textContent = provider.label;
                providerEl.appendChild(option);
              }
              providerEl.value = initialValues.provider || schema.defaultProvider || schema.providers[0]?.id || "";
            }

            function updateModelOptions() {
              const provider = currentProvider();
              modelEl.innerHTML = "";
              for (const model of provider.models || []) {
                const option = document.createElement("option");
                option.value = model.id;
                option.textContent = model.label;
                modelEl.appendChild(option);
              }
              const fallback = provider.defaultModel || provider.models[0]?.id || "";
              const selected = (provider.models || []).some((item) => item.id === initialValues.modelPreset) ? initialValues.modelPreset : fallback;
              modelEl.value = selected;
              updateBaseUrlField();
              updateResolved();
            }

            function updateBaseUrlField() {
              const provider = currentProvider();
              const defaultBaseUrl = provider.baseUrl || "";
              const requiresBaseUrl = Boolean(provider.requiresBaseUrl);
              if (!baseUrlEl.dataset.touched || providerEl.dataset.providerChanged === "true") {
                baseUrlEl.value = initialValues.baseUrl || defaultBaseUrl;
              }
              baseUrlEl.disabled = !requiresBaseUrl && Boolean(defaultBaseUrl);
              baseUrlEl.required = requiresBaseUrl;
              baseUrlEl.placeholder = requiresBaseUrl
                ? "https://your-openai-compatible-endpoint/v1"
                : (defaultBaseUrl || "Uses provider default");
              baseUrlHintEl.textContent = requiresBaseUrl
                ? "Required for custom OpenAI-compatible providers."
                : (defaultBaseUrl ? "Preset provider. Base URL is managed automatically." : "Optional. Leave empty to use the provider default.");
              providerEl.dataset.providerChanged = "false";
            }

            function updateResolved() {
              const provider = currentProvider();
              const model = currentModel();
              modelHintEl.textContent = model.summary || "";
              const resolvedBaseUrl = baseUrlEl.value || provider.baseUrl || "";
              const bits = [
                "Provider: " + provider.label,
                "Model ID: " + model.modelId,
                "Label: " + model.displayName,
                resolvedBaseUrl ? "Base URL: " + resolvedBaseUrl : "Base URL: provider default",
                model.useResponsesApi ? "Responses API: enabled" : "Responses API: disabled",
              ];
              resolvedEl.innerHTML = "";
              for (const bit of bits) {
                const span = document.createElement("span");
                span.className = "pill";
                span.textContent = bit;
                resolvedEl.appendChild(span);
              }
            }

            function payload() {
              return {
                provider: providerEl.value,
                modelPreset: modelEl.value,
                baseUrl: baseUrlEl.value,
                apiKey: apiKeyEl.value,
                tavilyApiKey: tavilyEl.value,
                jinaApiKey: jinaEl.value,
              };
            }

            async function save() {
              const res = await fetch("/__config/api/config", {
                method: "POST",
                headers: { "content-type": "application/json", accept: "application/json" },
                body: JSON.stringify(payload()),
              });
              const data = await res.json();
              statusEl.textContent = data.error || data.summary || (data.ready ? "Configuration saved. DeerFlow is starting in the background." : "Configuration saved.");
            }

            providerEl.addEventListener("change", () => {
              providerEl.dataset.providerChanged = "true";
              initialValues.modelPreset = "";
              updateModelOptions();
            });
            modelEl.addEventListener("change", () => {
              updateResolved();
            });
            baseUrlEl.addEventListener("input", () => {
              baseUrlEl.dataset.touched = "true";
              updateResolved();
            });
            document.getElementById("save").addEventListener("click", () => { save().catch((error) => { statusEl.textContent = error.message; }); });
            document.getElementById("openApp").addEventListener("click", () => { window.location.href = "/"; });

            updateProviderOptions();
            updateModelOptions();
            apiKeyEl.value = initialValues.apiKey || "";
            baseUrlEl.value = initialValues.baseUrl || "";
            tavilyEl.value = initialValues.tavilyApiKey || "";
            jinaEl.value = initialValues.jinaApiKey || "";
          </script>
        </body>
        </html>`
            .replace("__SCHEMA_JSON__", JSON.stringify(payload.schema || {}))
            .replace("__VALUES_JSON__", JSON.stringify(payload.values || {}));
        }

        async function readBody(req) {
          const chunks = [];
          for await (const chunk of req) chunks.push(chunk);
          return Buffer.concat(chunks).toString("utf8");
        }

        const server = http.createServer(async (req, res) => {
          const payload = await buildPayload();

          if (req.url === "/health") {
            res.writeHead(200, { "content-type": "application/json" });
            res.end(JSON.stringify({ ready: payload.ready }));
            return;
          }

          if (req.url === "/internal/ready") {
            res.writeHead(payload.ready ? 204 : 401);
            res.end();
            return;
          }

          if (req.url === "/__config/api/schema") {
            res.writeHead(200, { "content-type": "application/json" });
            res.end(JSON.stringify(payload));
            return;
          }

          if (req.url === "/__config/api/config" && req.method === "POST") {
            try {
              const body = JSON.parse((await readBody(req)) || "{}");
              const envMap = validateAndMaterialize(payload.schema, body);
              await saveState(envMap);
              await runRender();
              const nextPayload = await buildPayload();
              res.writeHead(nextPayload.ready ? 200 : 422, { "content-type": "application/json" });
              res.end(JSON.stringify({
                ready: nextPayload.ready,
                summary: nextPayload.ready ? `${appName} configuration saved.` : "Configuration is still incomplete.",
              }));
            } catch (error) {
              res.writeHead(422, { "content-type": "application/json" });
              res.end(JSON.stringify({ ready: false, error: error instanceof Error ? error.message : String(error) }));
            }
            return;
          }

          if (req.url === "/" || req.url === settingsPath || req.url === "/settings/config") {
            res.writeHead(200, { "content-type": "text/html; charset=utf-8" });
            res.end(renderPage(payload));
            return;
          }

          res.writeHead(404, { "content-type": "text/plain; charset=utf-8" });
          res.end("not found");
        });

        server.listen(port, "0.0.0.0", () => {
          console.error(`[config-ui] listening on :${port}`);
        });
        """
    )


def render_config_gate_server() -> str:
    return textwrap.dedent(
        """\
        import http from "node:http";
        import https from "node:https";
        import { mkdir, readFile, rm, writeFile } from "node:fs/promises";
        import { dirname } from "node:path";
        import { pathToFileURL } from "node:url";

        const port = Number(process.env.PORT || 8080);
        const appName = process.env.CONFIG_GATE_APP_NAME || "Application";
        const pageTitle = process.env.CONFIG_GATE_PAGE_TITLE || `Configure ${appName}`;
        const setupHint = process.env.CONFIG_GATE_SETUP_HINT || "Fill in the required configuration, then save to start the app.";
        const configPath = process.env.CONFIG_GATE_CONFIG_PATH || "";
        const templatePath = process.env.CONFIG_GATE_TEMPLATE_PATH || "";
        const readyMarker = process.env.CONFIG_GATE_READY_MARKER || "";
        const validatorModulePath = process.env.CONFIG_GATE_VALIDATOR_MODULE || "";
        const targetUrl = new URL(process.env.CONFIG_GATE_TARGET_URL || "http://127.0.0.1:80");
        const targetHealthUrl = process.env.CONFIG_GATE_TARGET_HEALTH_URL || "";

        function escapeHtml(value) {
          return String(value)
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#39;");
        }

        async function ensureParent(filePath) {
          await mkdir(dirname(filePath), { recursive: true });
        }

        async function readText(filePath) {
          if (!filePath) return "";
          return readFile(filePath, "utf8").catch(() => "");
        }

        async function writeText(filePath, value) {
          await ensureParent(filePath);
          await writeFile(filePath, value, "utf8");
        }

        async function touchReadyMarker() {
          if (!readyMarker) return;
          await writeText(readyMarker, "ready\\n");
        }

        async function clearReadyMarker() {
          if (!readyMarker) return;
          await rm(readyMarker, { force: true }).catch(() => {});
        }

        async function loadValidator() {
          if (!validatorModulePath) {
            return { validateConfig: async () => ({ ready: true, summary: "No validator configured." }) };
          }
          const mod = await import(pathToFileURL(validatorModulePath).href + `?ts=${Date.now()}`);
          if (typeof mod.validateConfig !== "function") {
            throw new Error(`Validator module missing validateConfig(): ${validatorModulePath}`);
          }
          return mod;
        }

        async function ensureConfigExists() {
          const existing = await readText(configPath);
          if (existing.trim()) return existing;
          const template = await readText(templatePath);
          if (template.trim()) {
            await writeText(configPath, template);
            return template;
          }
          return existing;
        }

        async function getConfigState() {
          const content = await ensureConfigExists();
          const validator = await loadValidator();
          const result = await validator.validateConfig(content, { appName, configPath });
          const ready = Boolean(result && result.ready);
          if (ready) {
            await touchReadyMarker();
          } else {
            await clearReadyMarker();
          }
          return {
            ready,
            summary: result?.summary || "",
            error: result?.error || "",
            content,
          };
        }

        async function readBody(req) {
          const chunks = [];
          for await (const chunk of req) chunks.push(chunk);
          return Buffer.concat(chunks).toString("utf8");
        }

        async function probeTarget() {
          const probeUrl = targetHealthUrl || targetUrl.toString();
          try {
            const controller = new AbortController();
            const timer = setTimeout(() => controller.abort(), 3000);
            const res = await fetch(probeUrl, {
              signal: controller.signal,
              headers: { accept: "application/json,text/plain,*/*" },
            });
            clearTimeout(timer);
            return res.ok;
          } catch {
            return false;
          }
        }

        function renderPage(state) {
          const statusClass = state.ready ? "status ready" : "status blocked";
          const statusText = state.ready
            ? (state.targetReachable ? `${appName} is starting. This page will switch automatically.` : "Configuration saved. Waiting for backend services to become reachable.")
            : (state.error || state.summary || "Configuration is required before startup.");
          return `<!doctype html>
        <html lang="en">
        <head>
          <meta charset="utf-8">
          <meta name="viewport" content="width=device-width, initial-scale=1">
          <title>${escapeHtml(pageTitle)}</title>
          <style>
            :root { --bg:#f3efe6; --panel:#fffaf2; --line:#d7cbb4; --text:#221c14; --muted:#6f6457; --accent:#1f6feb; --warn:#b54708; --ok:#157347; }
            * { box-sizing:border-box; }
            body { margin:0; min-height:100vh; font-family: ui-sans-serif, system-ui, sans-serif; background:linear-gradient(180deg, #faf6ef 0%, var(--bg) 100%); color:var(--text); }
            .wrap { max-width:960px; margin:0 auto; padding:32px 20px 48px; }
            .panel { background:rgba(255,250,242,.95); border:1px solid var(--line); border-radius:24px; padding:24px; box-shadow:0 20px 40px rgba(34,28,20,.08); }
            h1 { margin:0 0 12px; font-size:32px; }
            p { margin:0; color:var(--muted); line-height:1.6; }
            .status { margin-top:18px; padding:14px 16px; border-radius:16px; font-weight:600; }
            .status.blocked { background:#fff1e6; color:var(--warn); border:1px solid #f7d6bf; }
            .status.ready { background:#e8f5ee; color:var(--ok); border:1px solid #c8e7d3; }
            textarea { width:100%; min-height:420px; margin-top:18px; padding:16px; border-radius:18px; border:1px solid var(--line); background:#fff; color:var(--text); font:13px/1.5 ui-monospace, SFMono-Regular, Menlo, monospace; resize:vertical; }
            .row { display:flex; gap:12px; align-items:center; margin-top:16px; flex-wrap:wrap; }
            button { min-height:44px; padding:0 18px; border:0; border-radius:999px; background:var(--accent); color:#fff; font-weight:700; cursor:pointer; }
            button[disabled] { opacity:.6; cursor:progress; }
            .hint { font-size:13px; color:var(--muted); }
          </style>
        </head>
        <body>
          <main class="wrap">
            <section class="panel">
              <h1>${escapeHtml(pageTitle)}</h1>
              <p>${escapeHtml(setupHint)}</p>
              <div id="status" class="${statusClass}">${escapeHtml(statusText)}</div>
              <textarea id="config">${escapeHtml(state.content)}</textarea>
              <div class="row">
                <button id="save" type="button">Save and Start</button>
                <span class="hint">Config path: ${escapeHtml(configPath)}</span>
              </div>
            </section>
          </main>
          <script>
            const statusEl = document.getElementById("status");
            const saveButton = document.getElementById("save");
            const configInput = document.getElementById("config");

            function renderStatus(state) {
              const ready = Boolean(state.ready);
              statusEl.className = ready ? "status ready" : "status blocked";
              statusEl.textContent = ready
                ? (state.targetReachable ? "Configuration saved. Switching to the application..." : "Configuration saved. Waiting for backend services to start...")
                : (state.error || state.summary || "Configuration is required before startup.");
              if (ready && state.targetReachable) {
                window.location.reload();
              }
            }

            async function refresh() {
              const res = await fetch("/__lazycat/config-status", { headers: { accept: "application/json" } });
              renderStatus(await res.json());
            }

            saveButton.addEventListener("click", async () => {
              saveButton.disabled = true;
              try {
                const res = await fetch("/__lazycat/config", {
                  method: "POST",
                  headers: { "content-type": "application/json", accept: "application/json" },
                  body: JSON.stringify({ content: configInput.value }),
                });
                renderStatus(await res.json());
              } finally {
                saveButton.disabled = false;
              }
            });

            setInterval(() => { refresh().catch(() => {}); }, 3000);
          </script>
        </body>
        </html>`;
        }

        function proxyHttp(req, res) {
          const isHttps = targetUrl.protocol === "https:";
          const requestImpl = isHttps ? https.request : http.request;
          const upstreamReq = requestImpl(
            {
              protocol: targetUrl.protocol,
              hostname: targetUrl.hostname,
              port: targetUrl.port || (isHttps ? 443 : 80),
              method: req.method,
              path: req.url,
              headers: { ...req.headers, host: req.headers.host },
            },
            (upstreamRes) => {
              res.writeHead(upstreamRes.statusCode || 502, upstreamRes.headers);
              upstreamRes.pipe(res);
            },
          );
          upstreamReq.on("error", (error) => {
            res.writeHead(502, { "content-type": "application/json" });
            res.end(JSON.stringify({ error: `proxy failed: ${error.message}` }));
          });
          req.pipe(upstreamReq);
        }

        const server = http.createServer(async (req, res) => {
          const state = await getConfigState();
          const targetReachable = state.ready ? await probeTarget() : false;
          const payload = {
            ready: state.ready,
            summary: state.summary,
            error: state.error,
            targetReachable,
          };

          if (req.url === "/health") {
            res.writeHead(200, { "content-type": "application/json" });
            res.end(JSON.stringify(payload));
            return;
          }

          if (req.url === "/__lazycat/config-status") {
            res.writeHead(200, { "content-type": "application/json" });
            res.end(JSON.stringify(payload));
            return;
          }

          if (req.url === "/__lazycat/config" && req.method === "GET") {
            res.writeHead(200, { "content-type": "application/json" });
            res.end(JSON.stringify({ ...payload, content: state.content }));
            return;
          }

          if (req.url === "/__lazycat/config" && req.method === "POST") {
            let content = "";
            try {
              content = JSON.parse((await readBody(req)) || "{}").content || "";
            } catch {
              res.writeHead(400, { "content-type": "application/json" });
              res.end(JSON.stringify({ ready: false, error: "Invalid JSON payload." }));
              return;
            }
            await writeText(configPath, content);
            const nextState = await getConfigState();
            const nextTargetReachable = nextState.ready ? await probeTarget() : false;
            res.writeHead(nextState.ready ? 200 : 422, { "content-type": "application/json" });
            res.end(JSON.stringify({
              ready: nextState.ready,
              summary: nextState.summary,
              error: nextState.error,
              targetReachable: nextTargetReachable,
              content: nextState.content,
            }));
            return;
          }

          if (state.ready && targetReachable) {
            proxyHttp(req, res);
            return;
          }

          res.writeHead(200, { "content-type": "text/html; charset=utf-8" });
          res.end(renderPage({ ...state, targetReachable }));
        });

        server.listen(port, "0.0.0.0", () => {
          console.error(`[config-gate] listening on :${port}`);
        });
        """
    )


def render_persist_env_bootstrap(
    *,
    state_dir_env: str,
    config_dir_env: str,
    config_path_env: str,
    env_names: list[str],
    preserve_existing_names: list[str] | None = None,
    app_dir: str = "/app",
    app_env_path: str = "/app/.env",
) -> str:
    preserve_existing_names = preserve_existing_names or []
    env_names_literal = ", ".join(json.dumps(name) for name in env_names)
    preserve_literal = ", ".join(json.dumps(name) for name in preserve_existing_names)
    return textwrap.dedent(
        f"""\
        import {{ access, mkdir, readFile, writeFile }} from "node:fs/promises";
        import {{ constants as fsConstants }} from "node:fs";
        import {{ spawn }} from "node:child_process";

        const APP_DIR = {json.dumps(app_dir)};
        const STATE_DIR = process.env.{state_dir_env} || "/app-state";
        const CONFIG_DIR = process.env.{config_dir_env} || `${{STATE_DIR}}/config`;
        const CONFIG_PATH = process.env.{config_path_env} || `${{CONFIG_DIR}}/.env`;
        const DOTENV_PATH = {json.dumps(app_env_path)};
        const ENV_NAMES = [{env_names_literal}];
        const PRESERVE_EXISTING_NAMES = new Set([{preserve_literal}]);
        const RUNTIME_MANIFEST_PATH = "/lzcapp/run/manifest.yml";
        const PACKAGE_MANIFEST_PATH = "/lzcapp/pkg/manifest.yml";

        async function exists(path) {{
          try {{
            await access(path, fsConstants.F_OK);
            return true;
          }} catch {{
            return false;
          }}
        }}

        function envContent(values, comment) {{
          return [
            comment,
            ...Object.entries(values).map(([key, value]) => `${{key}}=${{String(value || "").replace(/\\r?\\n/g, " ").trim()}}`),
            "",
          ].join("\\n");
        }}

        function parseEnvText(raw) {{
          const result = {{}};
          for (const line of String(raw || "").split(/\\r?\\n/)) {{
            const match = line.match(/^([A-Za-z_][A-Za-z0-9_]*)=(.*)$/);
            if (!match) continue;
            result[match[1]] = match[2] || "";
          }}
          return result;
        }}

        function parseManifestEnv(raw) {{
          const result = {{}};
          for (const line of String(raw || "").split(/\\r?\\n/)) {{
            const match = line.match(/^\\s*-\\s+([A-Za-z_][A-Za-z0-9_]*)=(.*)\\s*$/);
            if (!match) continue;
            const key = match[1];
            if (!ENV_NAMES.includes(key)) continue;
            result[key] = match[2] || "";
          }}
          return result;
        }}

        async function manifestEnv() {{
          for (const path of [RUNTIME_MANIFEST_PATH, PACKAGE_MANIFEST_PATH]) {{
            if (!(await exists(path))) continue;
            const raw = await readFile(path, "utf8").catch(() => "");
            const parsed = parseManifestEnv(raw);
            if (Object.keys(parsed).length > 0) return parsed;
          }}
          return {{}};
        }}

        async function runtimeEnv() {{
          const rendered = await manifestEnv();
          return Object.fromEntries(ENV_NAMES.map((name) => [name, process.env[name] || rendered[name] || ""]));
        }}

        async function syncConfigFiles() {{
          await mkdir(CONFIG_DIR, {{ recursive: true }});
          const content = envContent(await runtimeEnv(), "# Generated by LazyCat bootstrap.");
          await writeFile(CONFIG_PATH, content, "utf8");
          await writeFile(DOTENV_PATH, content, "utf8");
        }}

        async function mergeExistingSecrets() {{
          if (!(await exists(CONFIG_PATH))) return;
          const existing = parseEnvText(await readFile(CONFIG_PATH, "utf8").catch(() => ""));
          for (const name of PRESERVE_EXISTING_NAMES) {{
            if (!process.env[name] && existing[name]) {{
              process.env[name] = existing[name];
            }}
          }}
        }}

        await mergeExistingSecrets();
        await syncConfigFiles();

        const child = spawn("node", ["server.mjs"], {{
          cwd: APP_DIR,
          env: {{
            ...process.env,
            PORT: process.env.PORT || "3117",
          }},
          stdio: "inherit",
        }});

        child.on("exit", (code, signal) => {{
          if (signal) process.exit(0);
          process.exit(code ?? 0);
        }});
        """
    )


def slug_to_env_prefix(slug: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", str(slug or "app")).strip("_")
    return cleaned.upper() or "APP"


def matches_basic_llm_dotenv_profile(finalized: dict[str, Any], analysis: AnalysisResult) -> bool:
    services = finalized.get("services")
    if not isinstance(services, dict) or len(services) != 1:
        return False
    service_name = next(iter(services.keys()))
    if service_name != finalized.get("slug"):
        return False

    application = finalized.get("application")
    app_env = [str(item) for item in application.get("environment", [])] if isinstance(application, dict) else []
    env_docs = finalized.get("env_vars")
    env_doc_names = {
        str(item.get("name", "")).strip()
        for item in bm.ensure_list(env_docs)
        if isinstance(item, dict)
    }
    joined_env = "\n".join(app_env)
    required_markers = ("LLM_PROVIDER", "LLM_API_KEY", "LLM_MODEL", "OLLAMA_BASE_URL")
    has_required_app_env = all(marker in joined_env for marker in required_markers)
    has_required_env_docs = all(marker in env_doc_names for marker in required_markers)
    return has_required_app_env or has_required_env_docs


def apply_persisted_env_service_profile(
    finalized: dict[str, Any],
    *,
    service_name: str,
    state_slug: str,
    state_env_prefix: str,
    note_prefix: str,
    note_description: str,
) -> None:
    finalized["include_content"] = True
    startup_notes = finalized.setdefault("startup_notes", [])
    if note_description not in startup_notes:
        startup_notes.append(note_description)
    state_note = (
        f"{note_prefix} 配置持久化到 `/lzcapp/var/data/{state_slug}/runtime/config/.env`，"
        f"容器内路径映射为 `/{state_slug}-state/config/.env`。"
    )
    if state_note not in startup_notes:
        startup_notes.append(state_note)

    application = finalized.get("application", {})
    app_env = [str(item) for item in application.get("environment", [])] if isinstance(application, dict) else []
    service = finalized.get("services", {}).get(service_name)
    if not isinstance(service, dict):
        return

    state_root = f"/{state_slug}-state"
    service["command"] = f"sh -lc 'mkdir -p {state_root}/config && cd /app && node /lzcapp/pkg/content/bootstrap.mjs'"
    service_env = [str(item) for item in service.get("environment", [])]
    profile_env = [
        f"{state_env_prefix}_STATE_DIR={state_root}",
        f"{state_env_prefix}_CONFIG_DIR={state_root}/config",
        f"{state_env_prefix}_CONFIG_PATH={state_root}/config/.env",
    ]
    for item in profile_env + app_env:
        if item not in service_env:
            service_env.append(item)
    service["environment"] = service_env

    binds = [str(item) for item in service.get("binds", [])]
    runtime_bind = f"/lzcapp/var/data/{state_slug}/runtime:{state_root}"
    legacy_bind = f"/lzcapp/var/data/{state_slug}/config:/lzcapp/var/data/{state_slug}/config"
    binds = [item for item in binds if item != legacy_bind]
    if runtime_bind not in binds:
        binds.append(runtime_bind)
    service["binds"] = binds


def render_basic_llm_deploy_params() -> str:
    return textwrap.dedent(
        """\
        params:
          - id: llm.provider
            type: string
            name: LLM Provider
            description: "Required. Enter a provider such as openai, anthropic, gemini, codex, openrouter, minimax, mistral, ollama, or grok. Enter disabled to skip AI-powered features for now. You can reconfigure later from Deployment Parameters in the app details page."
          - id: llm.api_key
            type: string
            name: LLM API Key
            description: "Optional credential for the selected provider. Leave empty to skip. The configured values will be written into the app .env before startup."
            default_value: ""
            optional: true
          - id: llm.model
            type: string
            name: LLM Model
            description: "Optional model override. Leave empty to use the provider default."
            default_value: ""
            optional: true
          - id: llm.base_url
            type: string
            name: LLM Base URL
            description: "Optional custom base URL, mainly for Ollama or OpenAI-compatible endpoints."
            default_value: ""
            optional: true
        """
    )


def post_process_basic_llm_dotenv(repo_root: Path, slug: str) -> list[str]:
    app_dir = repo_root / "apps" / slug
    content_dir = app_dir / "content"
    content_dir.mkdir(parents=True, exist_ok=True)
    env_prefix = slug_to_env_prefix(slug)

    writes = {
        app_dir / "lzc-deploy-params.yml": render_basic_llm_deploy_params(),
        content_dir / "README.md": f"This directory contains runtime helpers for {bm.titleize_slug(slug)} on LazyCat.\n",
        content_dir / "bootstrap.mjs": render_persist_env_bootstrap(
            state_dir_env=f"{env_prefix}_STATE_DIR",
            config_dir_env=f"{env_prefix}_CONFIG_DIR",
            config_path_env=f"{env_prefix}_CONFIG_PATH",
            env_names=["LLM_PROVIDER", "LLM_API_KEY", "LLM_MODEL", "OLLAMA_BASE_URL"],
            preserve_existing_names=["LLM_API_KEY"],
        ),
    }

    outputs: list[str] = []
    for path, content in writes.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        if path.suffix in {".sh", ".mjs", ".py"}:
            path.chmod(0o755)
        outputs.append(str(path))
    return outputs
def preflight_check(repo_root: Path, slug: str) -> tuple[bool, list[str]]:
    issues: list[str] = []
    app_dir = repo_root / "apps" / slug
    config_path = repo_root / "registry" / "repos" / f"{slug}.json"
    index_path = repo_root / "registry" / "repos" / "index.json"
    manifest_path = app_dir / "lzc-manifest.yml"
    build_path = app_dir / "lzc-build.yml"
    deploy_params_path = app_dir / "lzc-deploy-params.yml"

    for required in (manifest_path, build_path, config_path, index_path, app_dir / "README.md", app_dir / "icon.png"):
        if not required.exists():
            issues.append(f"missing required file: {required}")

    if issues:
        return False, issues

    icon_path = app_dir / "icon.png"
    icon_size = icon_path.stat().st_size
    if icon_size <= 0:
        issues.append("icon.png is empty")
    elif icon_size > MAX_ICON_BYTES:
        issues.append(
            f"icon.png is too large ({icon_size} bytes); keep it under {MAX_ICON_BYTES} bytes to avoid store/build issues"
        )

    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return False, [f"invalid config json: {exc}"]

    index = json.loads(index_path.read_text(encoding="utf-8"))
    if f"{slug}.json" not in index.get("repos", []):
        issues.append(f"{slug}.json not registered in registry/repos/index.json")

    workflow_sync_script = repo_root / "scripts" / "sync_trigger_build_options.py"
    if workflow_sync_script.exists():
        sync_check = subprocess.run(
            ["python3", str(workflow_sync_script), "--check"],
            cwd=str(repo_root),
            text=True,
            capture_output=True,
            check=False,
        )
        if sync_check.returncode != 0:
            fix_result = subprocess.run(
                ["python3", str(workflow_sync_script)],
                cwd=str(repo_root),
                text=True,
                capture_output=True,
                check=False,
            )
            if fix_result.returncode != 0:
                details = (fix_result.stdout or fix_result.stderr or "").strip()
                issues.append(
                    "trigger-build workflow options are out of sync and auto-fix failed"
                    + (f": {details}" if details else "")
                )
            else:
                print("[preflight] auto-fixed trigger-build workflow sync")

    manifest = load_yaml(manifest_path)
    if not isinstance(manifest, dict):
        issues.append("manifest is not valid yaml mapping")
        return False, issues

    version = str(manifest.get("version", "")).strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        issues.append(f"manifest version is not pure semver: {version}")

    application = manifest.get("application")
    services = manifest.get("services")
    if not isinstance(application, dict):
        issues.append("manifest.application is missing")
        return False, issues
    if not isinstance(services, dict) or not services:
        issues.append("manifest.services is missing")
        return False, issues

    profile = load_app_profile(repo_root, slug)
    profile_services = (profile or {}).get("fixes", {}).get("services", {}) if isinstance(profile, dict) else {}
    if isinstance(profile_services, dict) and profile_services:
        expected_keys: set[str] = set()
        for _, payload in profile_services.items():
            if not isinstance(payload, dict):
                continue
            for entry in bm.ensure_list(payload.get("environment")):
                text = str(entry).strip()
                if "=" not in text:
                    continue
                key, value = text.split("=", 1)
                key = key.strip()
                if not key or not value.strip():
                    continue
                expected_keys.add(key)
        manifest_keys: set[str] = set()
        for _, payload in services.items():
            if not isinstance(payload, dict):
                continue
            for entry in bm.ensure_list(payload.get("environment")):
                text = str(entry).strip()
                key = text.split("=", 1)[0].strip()
                if key:
                    manifest_keys.add(key)
        missing_keys = sorted(k for k in expected_keys if k not in manifest_keys)
        if missing_keys:
            issues.append(
                f"manifest is missing environment keys present in .app-profile.json: {missing_keys}; "
                "these may have been accidentally dropped during a rename or refactor"
            )

    for upstream in bm.ensure_list(application.get("upstreams")):
        if not isinstance(upstream, dict):
            continue
        backend = str(upstream.get("backend", "")).strip()
        match = re.search(r"https?://([A-Za-z0-9_.-]+):(\d+)", backend)
        if not match:
            issues.append(f"invalid application upstream backend: {backend}")
            continue
        service_name = match.group(1)
        if service_name not in services:
            issues.append(f"backend references missing service: {service_name}")

    for entry in bm.ensure_list(config.get("service_builds")):
        if not isinstance(entry, dict):
            continue
        target = str(entry.get("target_service", "")).strip()
        if target and target not in services:
            issues.append(
                f"registry service_builds.target_service={target!r} not found in lzc-manifest.yml services "
                f"({sorted(services.keys())})"
            )
    for entry in bm.ensure_list(config.get("dependencies")):
        if not isinstance(entry, dict):
            continue
        target = str(entry.get("target_service", "")).strip()
        if target and target not in services:
            issues.append(
                f"registry dependencies.target_service={target!r} not found in lzc-manifest.yml services "
                f"({sorted(services.keys())})"
            )
    for service_name, payload in services.items():
        if not isinstance(payload, dict):
            continue
        for dep in bm.ensure_list(payload.get("depends_on")):
            dep_name = str(dep).strip()
            if dep_name and dep_name not in services:
                issues.append(
                    f"service {service_name}.depends_on references missing service: {dep_name}"
                )

    if config.get("build_strategy") == "official_image" and not str(config.get("official_image_registry", "")).strip():
        issues.append("official_image strategy requires official_image_registry")
    if config.get("build_strategy") == "precompiled_binary" and not str(config.get("precompiled_binary_url", "")).strip():
        issues.append("precompiled_binary strategy requires precompiled_binary_url")
    dockerfile_path = str(config.get("dockerfile_path", "")).strip()
    if dockerfile_path and not (app_dir / dockerfile_path).exists():
        issues.append(f"configured dockerfile_path is missing: {app_dir / dockerfile_path}")
    elif dockerfile_path:
        dockerfile_text = (app_dir / dockerfile_path).read_text(encoding="utf-8", errors="ignore")
        placeholder_markers = [
            "Replace this placeholder Dockerfile before running a real build",
            "TODO: replace this placeholder with the real build steps",
        ]
        if any(marker in dockerfile_text for marker in placeholder_markers):
            issues.append(
                f"configured dockerfile_path points to a placeholder Dockerfile: {app_dir / dockerfile_path}; "
                "replace it with a real upstream build before installing or submitting"
            )
    for service_name, payload in services.items():
        if isinstance(payload, dict) and payload.get("command") and payload.get("setup_script"):
            issues.append(f"service {service_name} defines both command and setup_script")

    build_yml = build_path.read_text(encoding="utf-8")
    manifest_text = manifest_path.read_text(encoding="utf-8")
    deploy_param_sync = config.get("deploy_param_sync")
    if "/lzcapp/pkg/content/" in manifest_text and "contentdir:" not in build_yml:
        issues.append("manifest references /lzcapp/pkg/content but lzc-build.yml is missing contentdir")
    if ('index .U "' in manifest_text or "{{ if .U" in manifest_text or "{{ if index .U" in manifest_text) and not deploy_params_path.exists():
        issues.append("manifest uses deployment parameter templates but apps/<slug>/lzc-deploy-params.yml is missing")
    if '\\"' in manifest_text and "{{" in manifest_text and ".U" in manifest_text:
        issues.append("manifest contains backslash-escaped quotes inside deployment templates; use YAML single-quoted template strings instead of \\\"")
    if isinstance(deploy_param_sync, dict):
        script_relpath = str(deploy_param_sync.get("script_relpath", "")).strip()
        if not script_relpath:
            issues.append("deploy_param_sync is missing script_relpath")
        elif not (app_dir / script_relpath).exists():
            issues.append(f"deploy_param_sync script is missing: {app_dir / script_relpath}")
        targets = [str(item).strip() for item in bm.ensure_list(deploy_param_sync.get("targets")) if str(item).strip()]
        if not targets:
            issues.append("deploy_param_sync must declare at least one target file")

    # Collect all bind-mounted container paths across services for coverage check
    all_bind_containers: set[str] = set()

    for service_name, payload in services.items():
        if not isinstance(payload, dict):
            continue
        command_text = stringify_command(payload.get("command"))
        if command_text and bm.HEREDOC_PATTERN.search(command_text):
            issues.append(
                f"service {service_name} command uses heredoc syntax; "
                "command is often rendered as folded YAML and may break shell parsing. "
                "Prefer setup_script, an external script file, or printf/envsubst."
            )
        if "volumes" in payload:
            issues.append(
                f"service {service_name} uses 'volumes' key which LazyCat silently ignores; "
                "change to 'binds' for persistent storage."
            )
        binds = [str(item) for item in bm.ensure_list(payload.get("binds"))]
        for bind in binds:
            parts = bind.split(":")
            if len(parts) >= 2:
                all_bind_containers.add(parts[1])
        if "/lzcapp/pkg/content/bootstrap.mjs" in command_text and not any(bind.endswith(":/app-state") or ":/crucix-state" in bind or ":/deer-flow-state" in bind for bind in binds):
            issues.append(
                f"service {service_name} uses bootstrap.mjs but no dedicated state-dir bind was found; prefer /lzcapp/var/data/{slug}/runtime:/app-state-style mapping"
            )
        if "/lzcapp/var/data/" in command_text and "/config" in command_text and any(":/lzcapp/var/data/" in bind for bind in binds):
            issues.append(
                f"service {service_name} writes config directly under /lzcapp/var/data inside the container; prefer binding host runtime to a normal container path like /app-state or /{slug}-state"
            )

    # Detect interactive startup patterns that may block container in LazyCat
    for dockerfile_name in ("Dockerfile", "Dockerfile.template"):
        df_path = app_dir / dockerfile_name
        if not df_path.is_file():
            continue
        df_text = df_path.read_text(encoding="utf-8", errors="ignore")
        # Check entrypoint scripts too
        scan_texts = [df_text]
        for ep_match in re.finditer(r"(?im)^\s*COPY\s+(?:--[^\s]+\s+)*(\S+\.sh)\s+", df_text):
            ep_file = app_dir / Path(ep_match.group(1)).name
            if ep_file.is_file():
                try:
                    scan_texts.append(ep_file.read_text(encoding="utf-8", errors="ignore"))
                except Exception:
                    pass
        combined = "\n".join(scan_texts)
        interactive_patterns = [
            (r"\breadline\b", "readline"),
            (r"\bprompt\b.*\binput\b", "interactive prompt"),
            (r"\bdevice.?code\b", "device code auth"),
            (r"\bperformFreshAuthentication\b", "interactive authentication"),
            (r"\bread\s+-[rsp]", "shell read from stdin"),
            (r"\bselect\b.*\bin\b.*\bdo\b", "shell interactive select"),
        ]
        for pat, label in interactive_patterns:
            if re.search(pat, combined, re.IGNORECASE):
                issues.append(
                    f"entrypoint may use interactive input ({label}); "
                    "LazyCat containers run headless — ensure the app can start "
                    "without stdin/TTY (e.g. deferred auth via web UI)."
                )
                break  # one warning is enough
        break  # only check first found Dockerfile

    # Cross-check: scan Dockerfile for write paths not covered by any bind
    for dockerfile_name in ("Dockerfile", "Dockerfile.template"):
        dockerfile_path = app_dir / dockerfile_name
        if not dockerfile_path.is_file():
            continue
        discovered = _scan_dockerfile_write_paths(
            dockerfile_path.read_text(encoding="utf-8", errors="ignore")
        )
        discovered.extend(_scan_entrypoint_write_paths(app_dir, dockerfile_path))
        for container_path, hint in discovered:
            if container_path.startswith("$"):
                continue
            # Check if any bind covers this path (exact match or parent)
            covered = any(
                container_path == b or container_path.startswith(b.rstrip("/") + "/")
                for b in all_bind_containers
            )
            if not covered:
                issues.append(
                    f"write path {container_path} (from {hint}) has no matching bind mount; "
                    "data written here will be lost on container restart."
                )
        break  # only check first found Dockerfile

    return not issues, issues


def _rename_slug_in_spec(spec: dict[str, Any], old: str, new: str) -> None:
    """Recursively replace old slug with new slug in all string values and dict keys.

    Uses exact-match for dict keys and word-boundary-aware replacement for
    string values to avoid partial matches (e.g. 'app' inside 'app-test').
    """
    # Pattern matches old slug only when not immediately followed by more
    # alphanumeric/hyphen characters (prevents partial replacement).
    pat = re.compile(re.escape(old) + r"(?![a-z0-9-])", re.IGNORECASE)

    def _replace(s: str) -> str:
        return pat.sub(new, s)

    for key in list(spec.keys()):
        if key == old:
            spec[new] = spec.pop(old)
            key = new
        val = spec[key]
        if isinstance(val, dict):
            _rename_slug_in_spec(val, old, new)
        elif isinstance(val, str):
            replaced = _replace(val)
            if replaced != val:
                spec[key] = replaced
        elif isinstance(val, list):
            new_list: list[Any] = []
            for item in val:
                if isinstance(item, str):
                    new_list.append(_replace(item))
                elif isinstance(item, dict):
                    _rename_slug_in_spec(item, old, new)
                    new_list.append(item)
                else:
                    new_list.append(item)
            spec[key] = new_list


def fork_upstream_repo(upstream_repo: str, fork_owner: str = "CodeEagle", fork_name: str = "") -> str:
    """Fork the upstream repo to fork_owner/ and make it public.

    Args:
        upstream_repo: Original repo (e.g. "owner/repo").
        fork_owner: GitHub org/user to fork into.
        fork_name: Custom repo name for the fork. If empty, uses the upstream name.

    Returns the full name of the fork (e.g. "CodeEagle/repo-name").
    If the fork already exists, returns it without re-forking.
    """
    default_name = upstream_repo.split("/", 1)[1] if "/" in upstream_repo else upstream_repo
    repo_name = fork_name or default_name
    fork_full = f"{fork_owner}/{repo_name}"

    # Check if fork already exists
    existing = bm.github_api_json(f"repos/{fork_full}")
    if isinstance(existing, dict) and existing.get("full_name", "").lower() == fork_full.lower():
        print(f"[fork] Fork already exists: {fork_full}")
        # Ensure it's public
        if existing.get("private"):
            _set_repo_visibility(fork_full, private=False)
        return fork_full

    # Create fork via gh CLI
    cmd = ["gh", "repo", "fork", upstream_repo, "--clone=false"]
    if fork_name:
        cmd.extend(["--fork-name", fork_name])
    # Only use --org for organization accounts; user accounts fork to themselves
    owner_meta = bm.github_api_json(f"users/{fork_owner}")
    if isinstance(owner_meta, dict) and owner_meta.get("type", "").lower() == "organization":
        cmd.extend(["--org", fork_owner])
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0 and "already exists" not in result.stderr:
        raise RuntimeError(f"Failed to fork {upstream_repo}: {result.stderr}")

    print(f"[fork] Forked {upstream_repo} → {fork_full}")

    # Ensure public visibility
    _set_repo_visibility(fork_full, private=False)
    return fork_full


def _set_repo_visibility(repo: str, *, private: bool = False) -> None:
    """Set repo visibility via gh CLI."""
    visibility = "--private" if private else "--public"
    subprocess.run(
        ["gh", "repo", "edit", repo, "--visibility", "public" if not private else "private"],
        capture_output=True, text=True, timeout=30,
    )
    print(f"[fork] Set {repo} visibility to {'private' if private else 'public'}")


def detect_gh_token(env: dict[str, str]) -> tuple[str, str]:
    for name in ("GH_TOKEN", "GITHUB_TOKEN", "GH_PAT"):
        token = env.get(name, "").strip()
        if token:
            return token, name
    if command_exists("gh"):
        token = sh(["gh", "auth", "token"], check=False)
        if token:
            return token, "gh auth token"
    return "", ""


def detect_lzc_cli_token(env: dict[str, str]) -> tuple[str, str]:
    token = env.get("LZC_CLI_TOKEN", "").strip()
    if token:
        return token, "env:LZC_CLI_TOKEN"
    if command_exists("lzc-cli"):
        config_value = sh(["lzc-cli", "config", "get", "token"], check=False).strip()
        if config_value:
            parts = config_value.split()
            if len(parts) >= 2:
                return parts[-1].strip(), "lzc-cli config get token"
    box_config = load_json_file(BOX_CONFIG_PATH)
    token = str(box_config.get("token", "")).strip()
    if token:
        return token, str(BOX_CONFIG_PATH)
    return "", ""


def detect_image_owner(env: dict[str, str]) -> str:
    for name in ("GHCR_USERNAME", "GITHUB_REPOSITORY_OWNER"):
        value = env.get(name, "").strip()
        if value:
            return value
    return ""


def run_local_build(
    repo_root: Path,
    slug: str,
    build_mode: str,
    env: dict[str, str],
) -> BuildExecutionResult:
    lpk_output = repo_root / "dist" / f"{slug}.lpk"
    cmd = [
        "python3",
        str(repo_root / "scripts" / "run_build.py"),
        "--config-root",
        str(repo_root / "registry"),
        "--config-file",
        f"{slug}.json",
        "--artifact-repo",
        "CodeEagle/lzcat-artifacts",
        "--app-root",
        str(repo_root / "apps" / slug),
        "--lzcat-apps-root",
        str(repo_root),
        "--lpk-output",
        str(lpk_output),
        "--force-build",
    ]
    if build_mode == "build":
        cmd.append("--dry-run")
    proc = subprocess.Popen(
        cmd,
        cwd=str(repo_root),
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    assert proc.stdout is not None
    lines: list[str] = []
    for line in proc.stdout:
        print(line, end="")
        lines.append(line)
    proc.wait()
    output = "".join(lines)
    if proc.returncode != 0:
        return BuildExecutionResult(
            command=cmd,
            returncode=proc.returncode,
            stdout=output,
            stderr=output,
            lpk_path=lpk_output,
        )

    if build_mode in {"install", "reinstall"}:
        install_cmd = ["lzc-cli", "app", "install", str(lpk_output)]
        package_id = manifest_package_id(repo_root, slug)
        uninstall_output = ""
        if build_mode == "reinstall" and package_id:
            uninstall_result = subprocess.run(
                ["lzc-cli", "app", "uninstall", package_id],
                cwd=str(repo_root),
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            uninstall_output = (uninstall_result.stdout or "") + (uninstall_result.stderr or "")
        install_result = subprocess.run(
            install_cmd,
            cwd=str(repo_root),
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        install_output = uninstall_output + (install_result.stdout or "") + (install_result.stderr or "")
        combined = output + install_output
        return BuildExecutionResult(
            command=install_cmd,
            returncode=install_result.returncode,
            stdout=combined,
            stderr=install_output,
            lpk_path=lpk_output,
        )

    return BuildExecutionResult(
        command=cmd,
        returncode=0,
        stdout=output,
        stderr="",
        lpk_path=lpk_output,
    )


def attempt_build_with_strategy(repo_root: Path, slug: str, build_mode: str, env: dict[str, str], override_strategy: str) -> BuildExecutionResult:
    """Temporarily override registry config build_strategy, run local build, and restore config."""
    registry_path = repo_root / "registry" / "repos" / f"{slug}.json"
    lpk_output = repo_root / "dist" / f"{slug}.lpk"
    if not registry_path.exists():
        return BuildExecutionResult(command=[], returncode=1, stdout="", stderr="registry config missing", lpk_path=lpk_output)
    try:
        original = registry_path.read_text(encoding="utf-8")
        cfg = json.loads(original)
    except Exception as exc:
        return BuildExecutionResult(command=[], returncode=1, stdout="", stderr=f"failed to read/parse registry json: {exc}", lpk_path=lpk_output)
    backup_path = registry_path.with_suffix(registry_path.suffix + ".bak")
    try:
        # write backup and override
        backup_path.write_text(original, encoding="utf-8")
        cfg['build_strategy'] = override_strategy
        registry_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        res = run_local_build(repo_root, slug, build_mode, env)
        return res
    finally:
        # restore original config if possible
        try:
            if backup_path.exists():
                registry_path.write_text(backup_path.read_text(encoding="utf-8"), encoding="utf-8")
                backup_path.unlink()
        except Exception:
            pass

def manifest_package_id(repo_root: Path, slug: str) -> str:
    manifest = (repo_root / "apps" / slug / "lzc-manifest.yml").read_text(encoding="utf-8")
    match = re.search(r"^package:\s*(.+)$", manifest, re.MULTILINE)
    return match.group(1).strip() if match else ""


def tail_text(text: str, max_lines: int = 40) -> str:
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ""
    return "\n".join(lines[-max_lines:])


def auto_git_commit(repo_root: Path, slug: str) -> None:
    """Stage generated app files and commit if there are staged changes."""
    app_dir = repo_root / "apps" / slug
    config_path = repo_root / "registry" / "repos" / f"{slug}.json"
    index_path = repo_root / "registry" / "repos" / "index.json"
    workflow_dir = repo_root / ".github" / "workflows"

    add_targets = [str(app_dir), str(config_path), str(index_path)]
    if workflow_dir.exists():
        add_targets.append(str(workflow_dir))

    add_result = subprocess.run(
        ["git", "add", "--"] + add_targets,
        cwd=str(repo_root),
        text=True,
        capture_output=True,
        check=False,
    )
    if add_result.returncode != 0:
        print(f"[git] git add failed: {add_result.stderr.strip()}")
        return

    staged = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=str(repo_root),
        check=False,
    )
    if staged.returncode == 0:
        print("[git] nothing to commit")
        return

    commit_result = subprocess.run(
        ["git", "commit", "-m", f"chore({slug}): scaffold app via full_migrate"],
        cwd=str(repo_root),
        text=True,
        capture_output=True,
        check=False,
    )
    if commit_result.returncode == 0:
        print(f"[git] committed: chore({slug}): scaffold app via full_migrate")
    else:
        print(f"[git] commit failed: {commit_result.stderr.strip()}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run LazyCat migration SOP from a single upstream address.")
    parser.add_argument("source", help="GitHub repo URL, owner/repo, compose URL, docker image, or local repo path")
    parser.add_argument("--repo-root", default="", help="Path to lzcat-apps repository root")
    parser.add_argument("--force", action="store_true", help="Overwrite managed files if the target app already exists")
    parser.add_argument("--no-build", action="store_true", help="Stop after preflight instead of attempting build/install")
    parser.add_argument(
        "--build-mode",
        choices=BUILD_MODES,
        default="auto",
        help="Build action after preflight: auto/build/install/reinstall/validate-only",
    )
    parser.add_argument("--resume", action="store_true",
                        help="Resume from last completed step (reads .migration-state.json)")
    parser.add_argument("--resume-from", type=int, metavar="N", default=None,
                        help="Resume from step N (1-10), keeping context from prior steps")
    parser.add_argument("--verify", action="store_true",
                        help="Run from scratch and compare against existing state for reproducibility")
    parser.add_argument("--no-commit", action="store_true",
                        help="Do not create the automatic scaffold git commit after preflight")
    parser.add_argument("--fork", nargs="?", const=True, default=None, metavar="REPO_NAME",
                        help="Fork the upstream repo to CodeEagle/ before building. "
                             "Optionally specify a custom repo name (e.g. --fork my-app). "
                             "Sets upstream_repo to fork, check_strategy to commit_sha.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve() if args.repo_root else Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    runtime_name, runtime_env, cleanup_runtime = prepare_container_env(env)
    gh_token, gh_token_source = detect_gh_token(runtime_env)
    if gh_token:
        # Keep all aliases in sync so downstream scripts don't accidentally
        # pick a stale token due to environment-variable precedence.
        runtime_env["GH_PAT"] = gh_token
        runtime_env["GH_TOKEN"] = gh_token
        runtime_env["GITHUB_TOKEN"] = gh_token
    lzc_cli_token, lzc_cli_token_source = detect_lzc_cli_token(runtime_env)
    if lzc_cli_token:
        runtime_env["LZC_CLI_TOKEN"] = lzc_cli_token
    image_owner = detect_image_owner(runtime_env)

    normalized = normalize_source(args.source)
    source_dir: Path | None = None
    cleanup = lambda: None
    step_state = StepState()

    # --- State management ---
    existing_state = None
    resolved_app_dir: Path | None = None
    # --fork with a custom name creates a new app; don't reuse existing state
    fork_is_new_app = args.fork is not None and isinstance(args.fork, str) and args.fork
    if not args.force and not getattr(args, 'verify', False) and not fork_is_new_app:
        found = ms.find_state_by_source(repo_root / "apps", args.source)
        if found:
            resolved_app_dir, existing_state = found

    if args.resume_from is not None:
        start_step = args.resume_from
    elif args.resume and existing_state:
        start_step = ms.get_last_completed_step(existing_state) + 1
    elif existing_state and not args.force:
        start_step = ms.get_last_completed_step(existing_state) + 1
    else:
        start_step = 1

    state = existing_state if existing_state else ms.new_empty_state(args.source)
    app_dir: Path | None = resolved_app_dir

    # Will be populated in Step 3 or restored from state
    finalized: dict | None = None

    requested_build_mode = "validate-only" if args.no_build else args.build_mode
    step1_outputs = [f"source={args.source}", f"kind={normalized.kind}", f"build_mode={requested_build_mode}"]
    if gh_token_source:
        step1_outputs.append(f"gh_token_source={gh_token_source}")
    if lzc_cli_token_source:
        step1_outputs.append(f"lzc_token_source={lzc_cli_token_source}")
    if image_owner:
        step1_outputs.append(f"image_owner={image_owner}")
    step1_risks: list[str] = []
    try:
        step_state.current_step = 1
        source_dir, extra_outputs, cleanup = prepare_source(normalized)
        step1_outputs.extend(extra_outputs)
        step_report(
            1,
            "收集上游信息",
            conclusion=f"已识别输入类型为 `{normalized.kind}`，并准备好可分析的上游材料。",
            outputs=step1_outputs,
            scripts=["scripts/full_migrate.py", "git clone" if normalized.kind == "github_repo" else "无"],
            risks=step1_risks,
            next_step="进入 [2/10] 选择移植路线",
        )
        # Persist to state
        state["context"]["source"] = {
            "kind": normalized.kind,
            "url": normalized.source,
            "upstream_repo": normalized.upstream_repo,
            "homepage": normalized.homepage,
        }
        state["context"]["environment"] = {
            "gh_token_source": gh_token_source or "none",
            "lzc_cli_token_source": lzc_cli_token_source or "none",
            "container_runtime": runtime_name or "none",
            "image_owner": image_owner or "",
        }
        ms.mark_step_completed(state, 1, conclusion=f"已识别输入类型为 `{normalized.kind}`")

        step_state.current_step = 2
        analysis = analyze_source(normalized, source_dir, gh_token)
        step2_outputs = [
            f"slug={analysis.slug}",
            f"route={analysis.route}",
        ]
        if analysis.compose_file:
            step2_outputs.append(f"compose={analysis.compose_file}")
        if analysis.dockerfile:
            step2_outputs.append(f"dockerfile={analysis.dockerfile}")
        for note in bm.ensure_list(analysis.spec.get("startup_notes")):
            if isinstance(note, str) and note.startswith("扫描到上游图标："):
                step2_outputs.append(note)
                break
        step_report(
            2,
            "选择移植路线",
            conclusion=f"已自动推断构建路线为 `{analysis.route}`。",
            outputs=step2_outputs,
            scripts=["scripts/full_migrate.py"],
            risks=analysis.risks,
            next_step="进入 [3/10] 注册目标 app",
        )
        # Persist route decision
        state["context"]["route_decision"] = {
            "route": analysis.route,
            "build_strategy": analysis.spec.get("build_strategy", ""),
            "check_strategy": analysis.spec.get("check_strategy", ""),
            "risks": analysis.risks,
        }
        state["context"]["version"] = {
            "upstream": analysis.spec.get("source_version", ""),
            "normalized": analysis.spec.get("version", ""),
        }
        ms.mark_step_completed(state, 2, conclusion=f"已自动推断构建路线为 `{analysis.route}`")

        # Fork upstream if requested — updates spec and slug to point to fork
        if args.fork is not None and normalized.upstream_repo:
            try:
                custom_fork_name = args.fork if isinstance(args.fork, str) else ""
                forked_repo = fork_upstream_repo(normalized.upstream_repo, fork_name=custom_fork_name)
                analysis.spec["upstream_repo"] = forked_repo
                analysis.spec["check_strategy"] = "commit_sha"
                analysis.spec["build_strategy"] = "upstream_dockerfile"
                # Custom fork name also determines the app slug, service names,
                # subdomain, image_targets, and homepage.
                if custom_fork_name:
                    old_slug = analysis.slug
                    new_slug = bm.normalize_slug(custom_fork_name)
                    analysis.slug = new_slug
                    analysis.spec["slug"] = new_slug
                    analysis.spec["homepage"] = f"https://github.com/{forked_repo}"
                    # Deep-rename old_slug → new_slug across the entire spec
                    _rename_slug_in_spec(analysis.spec, old_slug, new_slug)
                print(f"[fork] Updated spec: upstream_repo={forked_repo}, slug={analysis.slug}, check_strategy=commit_sha")
            except Exception as exc:
                print(f"[fork] WARNING: fork failed ({exc}), continuing with original upstream")

        # First time we know the slug — create app_dir and save
        app_dir = repo_root / "apps" / analysis.slug
        app_dir.mkdir(parents=True, exist_ok=True)
        ms.save_state(app_dir, state)

        step_state.current_step = 3
        if start_step > 3 and "finalized" in state.get("context", {}):
            finalized = state["context"]["finalized"]
            config_path = repo_root / "registry" / "repos" / f"{finalized['slug']}.json"
            app_dir = repo_root / "apps" / finalized["slug"]
            print(f"  [3/10] ⏭ Restored finalized spec from state")
        else:
            finalized = bm.finalize_spec(analysis.spec, gh_token, fetch_upstream=False)
            if (
                image_owner
                and (
                    str(finalized.get("build_strategy", "")).strip() in SOURCE_BUILD_STRATEGIES
                    or bool(finalized.get("service_builds"))
                )
                and not str(finalized.get("image_owner", "")).strip()
            ):
                finalized["image_owner"] = image_owner
            finalized = apply_generated_app_fixes(finalized, analysis)
            # Canonicalize finalized for deterministic output before writing files
            try:
                for list_key in ("image_targets", "dependencies", "overlay_paths", "upstream_submodules", "service_builds"):
                    if list_key in finalized and isinstance(finalized[list_key], list):
                        finalized[list_key] = sorted(finalized[list_key], key=lambda x: json.dumps(x, sort_keys=True, ensure_ascii=False) if isinstance(x, (dict, list)) else str(x))
                if "build_args" in finalized and isinstance(finalized["build_args"], dict):
                    finalized["build_args"] = {k: finalized["build_args"][k] for k in sorted(finalized["build_args"].keys())}
                if "services" in finalized and isinstance(finalized["services"], dict):
                    finalized["services"] = {k: finalized["services"][k] for k in sorted(finalized["services"].keys())}
            except Exception:
                # Best-effort canonicalization: don't fail the overall run if something unexpected appears
                pass
            _profile_path = repo_root / "apps" / finalized["slug"] / ".app-profile.json"
            existing_profile = load_app_profile(repo_root, finalized["slug"]) if _profile_path.exists() else None
            if args.force and existing_profile and is_generated_app_profile(existing_profile):
                refreshed_profile = refresh_generated_app_profile(existing_profile, finalized)
                _profile_path.write_text(
                    json.dumps(refreshed_profile, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )
                existing_profile = refreshed_profile
            elif not _profile_path.exists():
                _profile_path.parent.mkdir(parents=True, exist_ok=True)
                # If app already has a content/ dir, ensure include_content is on
                _content_dir = _profile_path.parent / "content"
                if _content_dir.is_dir() and any(_content_dir.rglob("*")):
                    finalized["include_content"] = True
                _profile_path.write_text(
                    json.dumps(generate_app_profile(finalized), indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )
            profile = existing_profile if existing_profile is not None else load_app_profile(repo_root, finalized["slug"])
            if profile:
                finalized = apply_app_profile_fixes(finalized, profile)
            config_path = repo_root / "registry" / "repos" / f"{finalized['slug']}.json"
            app_dir = repo_root / "apps" / finalized["slug"]
            step_report(
                3,
                "注册目标 app",
                conclusion=f"目标 app 将注册为 `{finalized['slug']}`。",
                outputs=[str(app_dir), str(config_path)],
                scripts=["scripts/full_migrate.py"],
                risks=["目标 app 已存在时会自动覆盖当前托管文件"] if not args.force else [],
                next_step="进入 [4/10] 建立项目骨架",
            )
            state["context"]["finalized"] = finalized
            state["context"]["registration"] = {
                "slug": finalized["slug"],
                "monorepo_path": f"apps/{finalized['slug']}",
                "config_path": f"registry/repos/{finalized['slug']}.json",
            }
            ms.mark_step_completed(state, 3, conclusion="已完成 monorepo 注册")
            ms.save_state(app_dir, state)

        step_state.current_step = 4
        if not ms.should_skip_step(state, 4) and start_step <= 4:
            effective_force = args.force
            try:
                # preserve existing migration_status from current registry if present
                existing_registry = repo_root / "registry" / "repos" / f"{finalized['slug']}.json"
                if existing_registry.exists():
                    try:
                        regobj = json.loads(existing_registry.read_text(encoding='utf-8'))
                        if isinstance(regobj, dict):
                            if regobj.get('migration_status') is not None:
                                finalized['migration_status'] = regobj['migration_status']
                            # In verify mode, prefer values from the existing registry for stable reproducibility
                            if getattr(args, 'verify', False):
                                for key in (
                                    "build_strategy",
                                    "build_context",
                                    "dockerfile_path",
                                    "dockerfile_type",
                                    "overlay_paths",
                                    "image_targets",
                                    "service_port",
                                    "service_cmd",
                                    "service_builds",
                                    "docker_platform",
                                    "dependencies",
                                    "official_image_registry",
                                    "precompiled_binary_url",
                                    "publish_to_store",
                                    "image_owner",
                                    "build_args",
                                ):
                                    if key in regobj:
                                        finalized[key] = regobj[key]
                                    else:
                                        # if registry does not have the key, remove any auto-generated value
                                        if key in finalized:
                                            try:
                                                del finalized[key]
                                            except Exception:
                                                pass

                                # Also, if existing manifest/build files exist in the repo, prefer their top-level fields
                                try:
                                    manifest_path = repo_root / "apps" / finalized["slug"] / "lzc-manifest.yml"
                                    if manifest_path.exists():
                                        manifest_text = manifest_path.read_text(encoding='utf-8')
                                        # version
                                        m = re.search(r'^\s*version:\s*(.+)$', manifest_text, flags=re.MULTILINE)
                                        if m:
                                            ver = m.group(1).strip()
                                            if (ver.startswith('\"') and ver.endswith('\"')) or (ver.startswith("'") and ver.endswith("'")):
                                                ver = ver[1:-1]
                                            finalized['version'] = ver
                                        # name -> project_name
                                        m = re.search(r'^\s*name:\s*(.+)$', manifest_text, flags=re.MULTILINE)
                                        if m:
                                            finalized['project_name'] = m.group(1).strip().strip('"\'')
                                        # description
                                        m = re.search(r'^\s*description:\s*(.+)$', manifest_text, flags=re.MULTILINE)
                                        if m:
                                            finalized['description'] = m.group(1).strip().strip('"\'')
                                except Exception:
                                    pass

                                try:
                                    build_path = repo_root / "apps" / finalized["slug"] / "lzc-build.yml"
                                    if build_path.exists():
                                        build_text = build_path.read_text(encoding='utf-8')
                                        if 'lzc-sdk-version' in build_text:
                                            finalized['include_lzc_sdk_version'] = True
                                except Exception:
                                    pass
                    except Exception:
                        pass
                # Detect lzc-sdk-version in existing build.yml (always, not just verify mode)
                try:
                    _build_path = repo_root / "apps" / finalized["slug"] / "lzc-build.yml"
                    if _build_path.exists():
                        _build_text = _build_path.read_text(encoding='utf-8')
                        if 'lzc-sdk-version' in _build_text:
                            finalized['include_lzc_sdk_version'] = True
                except Exception:
                    pass
                refresh_icon_path(finalized, source_dir)
                written = bm.write_files(repo_root, finalized, effective_force)
            except FileExistsError:
                if args.force:
                    raise
                # In verify mode, prefer existing managed files rather than overwriting them.
                # This avoids noisy diffs when we are only checking reproducibility.
                if getattr(args, 'verify', False):
                    written = []
                    app_dir = repo_root / "apps" / finalized["slug"]
                    registry_dir = repo_root / "registry" / "repos"
                    config_path = registry_dir / f"{finalized['slug']}.json"
                    candidates = [
                        app_dir / "README.md",
                        app_dir / "lzc-manifest.yml",
                        app_dir / "lzc-build.yml",
                        app_dir / "UPSTREAM_DEPLOYMENT_CHECKLIST.md",
                        app_dir / "icon.png",
                        config_path,
                    ]
                    for p in candidates:
                        if p.exists():
                            written.append(p)
                    # If none of the managed files were present (unexpected), fall back to overwrite
                    if not written:
                        effective_force = True
                        finalized.setdefault("_risks", []).append("目标 app 已存在，但未找到托管文件，将覆盖生成文件")
                        written = bm.write_files(repo_root, finalized, effective_force)
                else:
                    effective_force = True
                    finalized.setdefault("_risks", []).append("目标 app 已存在，自动覆盖当前托管文件后继续")
                    refresh_icon_path(finalized, source_dir)
                    written = bm.write_files(repo_root, finalized, effective_force)
            post_written = apply_post_write(repo_root, finalized["slug"], analysis.spec.get("_post_write", {}))
            post_written.extend(apply_app_post_process(repo_root, finalized, analysis))
            step_report(
                4,
                "建立项目骨架",
                conclusion="已在 monorepo 中创建 app 目录和 registry 配置。",
                outputs=[str(path) for path in written[:6]],
                scripts=["scripts/full_migrate.py", "scripts/bootstrap_migration.py"],
                risks=[],
                next_step="进入 [5/10] 编写 lzc-manifest.yml",
            )
            ms.mark_step_completed(state, 4, conclusion="骨架文件已生成",
                files_written=[str(p) for p in written[:6]])
            ms.save_state(app_dir, state)
        elif start_step <= 4:
            print(f"  [4/10] ⏭ Skipped (already completed)")

        step_state.current_step = 5
        if not ms.should_skip_step(state, 5) and start_step <= 5:
            step_report(
                5,
                "编写 lzc-manifest.yml",
                conclusion="manifest 已按自动推断的服务拓扑、入口端口、环境变量和持久化目录生成初稿；构建后的真实镜像地址将由 .lazycat-images.json 管理。",
                outputs=[str(app_dir / "lzc-manifest.yml")],
                scripts=["scripts/full_migrate.py", "scripts/bootstrap_migration.py"],
                risks=analysis.risks,
                next_step="进入 [6/10] 补齐剩余文件",
            )
            ms.mark_step_completed(state, 5, conclusion="manifest 初稿已生成")
            ms.save_state(app_dir, state)
        elif start_step <= 5:
            print(f"  [5/10] ⏭ Skipped (already completed)")

        step_state.current_step = 6
        if not ms.should_skip_step(state, 6) and start_step <= 6:
            step6_outputs = [str(app_dir / "README.md"), str(app_dir / "lzc-build.yml"), str(app_dir / "UPSTREAM_DEPLOYMENT_CHECKLIST.md")]
            if 'post_written' in dir():
                step6_outputs.extend(post_written)
            step_report(
                6,
                "补齐剩余文件",
                conclusion="README、build 配置、checklist 以及需要的模板文件已补齐。",
                outputs=step6_outputs,
                scripts=["scripts/full_migrate.py", "scripts/bootstrap_migration.py"],
                risks=[],
                next_step="进入 [7/10] 运行预检",
            )
            ms.mark_step_completed(state, 6, conclusion="剩余文件已补齐")
            ms.save_state(app_dir, state)
        elif start_step <= 6:
            print(f"  [6/10] ⏭ Skipped (already completed)")

        step_state.current_step = 7
        ok, issues = preflight_check(repo_root, finalized["slug"])
        if not ok:
            step_report(
                7,
                "运行预检",
                conclusion="预检未通过，当前自动流程停在文件层修复前。",
                outputs=[str(app_dir)],
                scripts=["scripts/full_migrate.py"],
                risks=issues,
                next_step="停止，先修复预检问题",
            )
            ms.add_problem(state, 7, "; ".join(issues), "preflight")
            ms.save_state(app_dir, state)
            return 1

        if args.no_commit:
            print("[git] auto commit disabled (--no-commit)")
        else:
            auto_git_commit(repo_root, finalized["slug"])
        step_report(
            7,
            "运行预检",
            conclusion="预检通过，骨架和 registry 注册已满足进入构建阶段的最低条件。",
            outputs=[str(app_dir / "lzc-manifest.yml"), str(config_path)],
            scripts=["scripts/full_migrate.py"],
            risks=[],
            next_step="进入 [8/10] 触发并监听构建",
        )
        ms.mark_step_completed(state, 7, conclusion="预检通过", all_passed=True)
        ms.save_state(app_dir, state)

        step_state.current_step = 8
        if requested_build_mode == "validate-only":
            step_report(
                8,
                "触发并监听构建",
                conclusion="按 validate-only 模式要求，自动流程在预检后停止。",
                outputs=[str(app_dir)],
                scripts=["scripts/full_migrate.py"],
                risks=[],
                next_step="停止",
            )
            ms.mark_step_completed(state, 8, conclusion="validate-only 模式停止")
            ms.save_state(app_dir, state)
            return 0

        if not runtime_name:
            step_report(
                8,
                "触发并监听构建",
                conclusion="当前机器缺少可用的容器引擎，无法进入本地构建阶段。",
                outputs=[str(app_dir)],
                scripts=["scripts/full_migrate.py", "scripts/local_build.sh"],
                risks=["既没有 docker，也没有 podman 可供兼容桥接"],
                next_step="停止，补齐容器引擎后重跑同一命令即可继续",
            )
            ms.add_problem(state, 8, "no container runtime available", "build")
            ms.save_state(app_dir, state)
            return 1

        auto_install_capable = bool(runtime_env.get("LZC_CLI_TOKEN")) and command_exists("lzc-cli")
        if requested_build_mode == "auto":
            effective_build_mode = "reinstall" if auto_install_capable else "build"
        else:
            effective_build_mode = requested_build_mode
        if effective_build_mode in {"install", "reinstall"} and not auto_install_capable:
            step_report(
                8,
                "触发并监听构建",
                conclusion=f"当前模式 `{effective_build_mode}` 需要 lzc-cli 与有效 token，但本机条件不足。",
                outputs=[str(app_dir)],
                scripts=["scripts/full_migrate.py", "scripts/run_build.py"],
                risks=["缺少 lzc-cli 或 LZC_CLI_TOKEN，无法执行安装链路"],
                next_step="停止，补齐 lzc-cli/token 或改用 --build-mode build",
            )
            ms.add_problem(state, 8, "missing lzc-cli or LZC_CLI_TOKEN", "build")
            ms.save_state(app_dir, state)
            return 1
        build_result = run_local_build(repo_root, finalized["slug"], build_mode=effective_build_mode, env=runtime_env)
        if build_result.returncode != 0:
            failure_excerpt = tail_text(build_result.stderr or build_result.stdout)
            # Attempt fallback strategies when possible
            orig_strategy = str(finalized.get("build_strategy", "")).strip()
            fallback_candidates: list[str] = []
            if orig_strategy in SOURCE_BUILD_STRATEGIES:
                # prefer official_image if available
                if str(finalized.get("official_image_registry", "")).strip() or (
                    analysis and isinstance(analysis.spec, dict) and str(analysis.spec.get("official_image_registry", "")).strip()
                ):
                    fallback_candidates.append("official_image")
                # try upstream_with_target_template if dockerfile present
                if finalized.get("dockerfile_path") or analysis and analysis.dockerfile:
                    fallback_candidates.append("upstream_with_target_template")
                # lastly upstream_dockerfile
                fallback_candidates.append("upstream_dockerfile")
            elif orig_strategy == "official_image":
                if analysis and analysis.dockerfile:
                    fallback_candidates.append("upstream_dockerfile")

            fallback_succeeded = False
            for candidate in fallback_candidates:
                try:
                    print(f"[build-fallback] 尝试回退构建策略 -> {candidate}")
                    fb_result = attempt_build_with_strategy(repo_root, finalized["slug"], effective_build_mode, runtime_env, candidate)
                    if fb_result.returncode == 0:
                        step_report(
                            8,
                            "触发并监听构建",
                            conclusion=f"本地构建失败后使用回退策略 `{candidate}` 重试并成功。",
                            outputs=[
                                str(repo_root / "dist" / f"{finalized['slug']}.lpk"),
                                str(app_dir / ".lazycat-images.json"),
                            ],
                            scripts=["scripts/full_migrate.py", "scripts/run_build.py"],
                            risks=[f"fallback={candidate}"],
                            next_step="进入 [9/10] 下载并核对 .lpk",
                        )
                        ms.mark_step_completed(state, 8, conclusion=f"构建成功 (fallback={candidate})", build_mode=effective_build_mode)
                        ms.save_state(app_dir, state)
                        build_result = fb_result
                        fallback_succeeded = True
                        break
                except Exception as exc:
                    print(f"[build-fallback] 回退策略 {candidate} 失败: {exc}")
            if not fallback_succeeded:
                step_report(
                    8,
                    "触发并监听构建",
                    conclusion="本地构建失败，自动流程停在构建阶段。",
                    outputs=[str(app_dir), str(repo_root / "dist" / f"{finalized['slug']}.lpk")],
                    scripts=["scripts/full_migrate.py", "scripts/run_build.py"],
                    risks=[failure_excerpt or "run_build 返回非零退出码"],
                    next_step="停止，修复构建错误后重跑同一命令即可继续",
                )
                ms.add_problem(state, 8, failure_excerpt or "build failed", "build")
                ms.save_state(app_dir, state)
                return 1

        step_report(
            8,
            "触发并监听构建",
            conclusion="本地构建命令执行成功。",
            outputs=[
                str(repo_root / "dist" / f"{finalized['slug']}.lpk"),
                str(app_dir / ".lazycat-images.json"),
            ],
            scripts=["scripts/full_migrate.py", "scripts/run_build.py"],
            risks=[] if effective_build_mode in {"install", "reinstall"} else [f"当前使用 `{runtime_name}` 执行 `{effective_build_mode}`，未覆盖远端 copy-image / install"],
            next_step="进入 [9/10] 下载并核对 .lpk",
        )
        ms.mark_step_completed(state, 8, conclusion="构建成功", build_mode=effective_build_mode)
        ms.save_state(app_dir, state)

        step_state.current_step = 9
        lpk_path = repo_root / "dist" / f"{finalized['slug']}.lpk"
        if not lpk_path.exists():
            step_report(
                9,
                "下载并核对 .lpk",
                conclusion="构建阶段未产出本地 .lpk，流程停在产物阶段。",
                outputs=[str(lpk_path)],
                scripts=["scripts/full_migrate.py", "scripts/run_build.py"],
                risks=["dist 目录中未发现期望的 lpk 文件"],
                next_step="停止",
            )
            ms.add_problem(state, 9, f"lpk not found: {lpk_path}", "artifact")
            ms.save_state(app_dir, state)
            return 1

        step_report(
            9,
            "下载并核对 .lpk",
            conclusion="已拿到本地构建产物并完成基本核对。",
            outputs=[f"{lpk_path} (sha256={file_sha256(lpk_path)})"],
            scripts=["scripts/full_migrate.py", "scripts/run_build.py"],
            risks=[] if effective_build_mode in {"install", "reinstall"} else [f"当前产物来自 `{effective_build_mode}`，未覆盖真实 release/download 链路"],
            next_step="进入 [10/10] 安装验收并复盘",
        )
        ms.mark_step_completed(state, 9, conclusion="lpk 已验证",
            lpk_sha256=file_sha256(lpk_path), lpk_size_bytes=lpk_path.stat().st_size)
        ms.save_state(app_dir, state)

        if effective_build_mode == "build":
            step_state.current_step = 10
            step_report(
                10,
                "安装验收并复盘",
                conclusion="当前环境没有进入自动安装验收链路，流程停在本地产物阶段。",
                outputs=[str(lpk_path)],
                scripts=["scripts/full_migrate.py"],
                risks=["缺少 LZC_CLI_TOKEN，未执行 `lzc-cli app install` 和后续状态验证"],
                next_step="停止，补齐 LZC_CLI_TOKEN 后重跑即可继续安装验收",
            )
            pending = ms.get_pending_backports(state)
            if pending:
                print(f"\n⚠ {len(pending)} resolved problems not yet backported:")
                for p in pending:
                    print(f"  - [{p['id']}] {p['description']}")
            ms.mark_step_completed(state, 10, conclusion="验收完成",
                pending_backports=[p["id"] for p in pending] if pending else [])
            ms.save_state(app_dir, state)
            return 0

        step_state.current_step = 10
        package_id = manifest_package_id(repo_root, finalized["slug"])
        status_output = sh(["lzc-cli", "app", "status", package_id], check=False)
        step_report(
            10,
            "安装验收并复盘",
            conclusion="已执行安装命令，并完成一次基础状态查询。",
            outputs=[str(lpk_path), f"package={package_id}", f"status={status_output or '无输出'}"],
            scripts=["scripts/full_migrate.py", "scripts/run_build.py", "lzc-cli app status"],
            risks=[],
            next_step="完成",
        )
        pending = ms.get_pending_backports(state)
        if pending:
            print(f"\n⚠ {len(pending)} resolved problems not yet backported:")
            for p in pending:
                print(f"  - [{p['id']}] {p['description']}")
        ms.mark_step_completed(state, 10, conclusion="验收完成",
            pending_backports=[p["id"] for p in pending] if pending else [])
        ms.save_state(app_dir, state)
        return 0
    except ms.MigrationProblem as exc:
        traceback.print_exc()
        ms.add_problem(state, exc.step, str(exc), exc.category)
        if app_dir:
            ms.save_state(app_dir, state)
        step_report(exc.step, "自动迁移失败",
            conclusion=f"[{exc.category}] {exc}",
            outputs=[str(exc)], scripts=["scripts/full_migrate.py"], risks=[str(exc)])
        return 1
    except Exception as exc:
        traceback.print_exc()
        if app_dir:
            ms.add_problem(state, step_state.current_step, str(exc), "unknown")
            try:
                ms.save_state(app_dir, state)
            except Exception:
                pass
        step_report(
            step_state.current_step,
            "自动迁移失败",
            conclusion="自动流程在当前步骤抛出异常。",
            outputs=[str(exc)],
            scripts=["scripts/full_migrate.py"],
            risks=[str(exc)],
            next_step="停止",
        )
        return 1
    finally:
        cleanup()
        cleanup_runtime()


if __name__ == "__main__":
    raise SystemExit(main())
