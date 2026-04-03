#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import tarfile
import tempfile
import textwrap
from pathlib import Path
from typing import Any
from urllib import error, request

import bootstrap_migration as bm

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
COMPOSE_FILENAMES = ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml")
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
    data = bm.github_api_json(f"repos/{repo}")
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


def normalize_source(source: str) -> dict[str, Any]:
    expanded = Path(source).expanduser()
    if expanded.exists() and expanded.is_dir():
        upstream_repo, homepage = infer_local_git_upstream(expanded.resolve())
        return {
            "kind": "local_repo",
            "source": source,
            "path": expanded.resolve(),
            "upstream_repo": upstream_repo,
            "homepage": homepage,
        }

    github_repo = parse_github_repo(source)
    if github_repo:
        return {
            "kind": "github_repo",
            "source": source,
            "path": None,
            "upstream_repo": github_repo,
            "homepage": f"https://github.com/{github_repo}",
        }

    if source.startswith(("http://", "https://")) and source.endswith((".yml", ".yaml")):
        return {
            "kind": "compose_url",
            "source": source,
            "path": None,
            "upstream_repo": parse_raw_github_compose_url(source) or "",
            "homepage": parse_raw_github_compose_url(source) and f"https://github.com/{parse_raw_github_compose_url(source)}" or "",
        }

    return {
        "kind": "docker_image",
        "source": source,
        "path": None,
        "upstream_repo": "",
        "homepage": "",
    }


def fetch_text(url: str) -> str:
    req = request.Request(url, headers={"User-Agent": "lzcat-full-migrate"})
    with request.urlopen(req, timeout=30) as response:
        return response.read().decode("utf-8")


def download_github_archive(repo: str, dest_root: Path) -> Path:
    repo_meta = bm.github_api_json(f"repos/{repo}")
    default_branch = "main"
    if isinstance(repo_meta, dict):
        default_branch = str(repo_meta.get("default_branch") or default_branch)

    archive_url = f"https://codeload.github.com/{repo}/tar.gz/refs/heads/{default_branch}"
    archive_path = dest_root / f"{repo.replace('/', '-')}-{default_branch}.tar.gz"
    req = request.Request(archive_url, headers={"User-Agent": "lzcat-full-migrate"})
    with request.urlopen(req, timeout=180) as response, archive_path.open("wb") as handle:
        shutil.copyfileobj(response, handle)

    with tarfile.open(archive_path, "r:gz") as tar:
        tar.extractall(dest_root, filter="data")

    extracted_dirs = sorted(path for path in dest_root.iterdir() if path.is_dir())
    if not extracted_dirs:
        raise RuntimeError(f"未能从 GitHub archive 解出仓库目录：{repo}")
    return extracted_dirs[0]


def prepare_source(normalized: dict[str, Any]) -> tuple[Path | None, list[str], callable]:
    if normalized["kind"] == "local_repo":
        return normalized["path"], [str(normalized["path"])], lambda: None

    temp_root = Path(tempfile.mkdtemp(prefix="lzcat-full-migrate-"))
    outputs: list[str] = []

    if normalized["kind"] == "github_repo":
        repo_dir = download_github_archive(normalized["upstream_repo"], temp_root)
        outputs.append(str(repo_dir))
        return repo_dir, outputs, lambda: shutil.rmtree(temp_root, ignore_errors=True)

    if normalized["kind"] == "compose_url":
        compose_name = Path(normalized["source"]).name or "compose.yml"
        compose_path = temp_root / compose_name
        compose_path.write_text(fetch_text(normalized["source"]), encoding="utf-8")
        outputs.append(str(compose_path))
        return temp_root, outputs, lambda: shutil.rmtree(temp_root, ignore_errors=True)

    return None, outputs, lambda: shutil.rmtree(temp_root, ignore_errors=True)


def select_compose_file(source_dir: Path) -> Path | None:
    candidates: list[Path] = []
    for name in COMPOSE_FILENAMES:
        candidates.extend(source_dir.rglob(name))
    if not candidates:
        return None
    return sorted(candidates, key=lambda p: (len(p.relative_to(source_dir).parts), str(p)))[0]


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
    output = sh(
        [
            "ruby",
            "-ryaml",
            "-rjson",
            "-e",
            "data = YAML.load_file(ARGV[0], aliases: true); puts JSON.generate(data)",
            str(path),
        ]
    )
    return json.loads(output) if output else {}


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
    return f"/lzcapp/var/data/{slug}/{sanitize_token(service_name)}/{sanitize_token(Path(target).name or 'data')}"


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


def infer_compose_upstreams(primary_name: str, primary_port: int, services: dict[str, Any]) -> list[dict[str, str]]:
    upstreams: list[dict[str, str]] = [
        {"location": "/", "backend": f"http://{primary_name}:{primary_port}/"}
    ]
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


def parse_dockerfile_volumes(dockerfile_path: Path, slug: str, service_name: str) -> list[dict[str, Any]]:
    text = dockerfile_path.read_text(encoding="utf-8", errors="ignore")
    entries: list[dict[str, Any]] = []
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
        for target in targets:
            if target.startswith("/"):
                host = target_host_path(slug, service_name, target)
                entries.append({"host": host, "container": target, "description": "From Dockerfile VOLUME"})
    return dedupe_data_paths(entries)


def parse_dockerfile_healthcheck(dockerfile_path: Path) -> dict[str, Any] | None:
    text = dockerfile_path.read_text(encoding="utf-8", errors="ignore")
    match = re.search(r"(?is)HEALTHCHECK\s+(?:--[^\n]+\s+)*CMD\s+(.+)", text)
    if not match:
        return None
    command = " ".join(match.group(1).split())
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
        "license": str(meta.get("license") or "TODO"),
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
    env_defaults = env_defaults_map(parse_env_files(env_files))

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
            return {
                "target_service": service_name,
                "build_strategy": "upstream_dockerfile",
                "source_dockerfile_path": dockerfile_rel,
                "build_context": build_context_rel,
                "build_args": dict(build_info.get("args") or {}),
                "image_name": f"{slug}-{sanitize_token(service_name)}",
            }

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

    for service_name, payload in services.items():
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
            bind, doc = parse_compose_volume(volume, slug, service_name)
            if bind:
                binds.append(bind)
            if doc:
                data_docs.append(doc)
        if binds:
            service_payload["binds"] = binds

        depends = compose_depends_on(payload)
        if depends:
            service_payload["depends_on"] = depends

        if payload.get("command"):
            service_payload["command"] = payload["command"]

        if payload.get("healthcheck"):
            service_payload["healthcheck"] = payload["healthcheck"]

        service_specs[service_name] = service_payload

        service_image = str(payload.get("image", "")).strip()
        if service_name == primary_name:
            image_targets.append(service_name)
        elif service_image and primary_image_repo and image_repository(service_image) == primary_image_repo and build_strategy == "official_image":
            image_targets.append(service_name)
        elif service_image and service_name not in build_services:
            dependencies.append({"target_service": service_name, "source_image": service_image})

    application = {
        "subdomain": slug,
        "public_path": ["/"],
        "upstreams": infer_compose_upstreams(primary_name, primary_port, services),
    }

    version = str(meta.get("version", "") or "").strip()
    if not version and is_version_like_tag(image_tag(primary_image)):
        version = bm.normalize_semver(image_tag(primary_image))
    version = version or "0.1.0"

    startup_notes = [
        f"自动扫描到 compose 文件：{compose_file.name}",
        f"主服务推断为 `{primary_name}`，入口端口 `{primary_port}`。",
    ]
    if dependencies:
        startup_notes.append("依赖服务镜像已写入 dependencies，首次完整构建时会自动 copy-image。")

    return {
        "slug": slug,
        "project_name": str(meta.get("project_name") or bm.titleize_slug(slug)),
        "description": str(meta.get("description") or f"{slug} on LazyCat"),
        "description_zh": f"（迁移初稿）{bm.titleize_slug(slug)} 的懒猫微服版本",
        "upstream_repo": str(meta.get("upstream_repo", "")),
        "homepage": str(meta.get("homepage", "")),
        "license": str(meta.get("license") or "TODO"),
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
        "services": service_specs,
        "application": application,
        "env_vars": dedupe_env_docs(env_docs),
        "data_paths": dedupe_data_paths(data_docs),
        "startup_notes": startup_notes,
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
    data_paths = parse_dockerfile_volumes(dockerfile_path, slug, slug)

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
        "license": str(meta.get("license") or "TODO"),
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
        "license": str(meta.get("license") or "TODO"),
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
        "license": str(meta.get("license") or "TODO"),
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


def choose_route_for_binary(slug: str, meta: dict[str, Any], binary: dict[str, Any]) -> dict[str, Any]:
    return {
        "slug": slug,
        "project_name": str(meta.get("project_name") or bm.titleize_slug(slug)),
        "description": str(meta.get("description") or f"{slug} on LazyCat"),
        "description_zh": f"（迁移初稿）{bm.titleize_slug(slug)} 的懒猫微服版本",
        "upstream_repo": str(meta.get("upstream_repo", "")),
        "homepage": str(meta.get("homepage", "")),
        "license": str(meta.get("license") or "TODO"),
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
        "license": str(meta.get("license") or "TODO"),
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


def analyze_source(normalized: dict[str, Any], source_dir: Path | None) -> dict[str, Any]:
    upstream_repo = normalized["upstream_repo"]
    repo_name = upstream_repo.split("/", 1)[1] if upstream_repo else ""
    slug = bm.normalize_slug(repo_name or Path(normalized["source"]).stem or normalized["source"].split("/")[-1])

    meta = bm.fetch_upstream_metadata(upstream_repo, "github_release") if upstream_repo else {}
    meta.update({
        "upstream_repo": upstream_repo,
        "homepage": meta.get("homepage") or normalized.get("homepage", ""),
        "check_strategy": "github_release",
    })

    if normalized["kind"] == "docker_image":
        spec = choose_route_for_image(normalized["source"])
        spec["slug"] = slug or spec["slug"]
        return {
            "slug": spec["slug"],
            "route": spec["build_strategy"],
            "spec": spec,
            "compose_file": None,
            "dockerfile": None,
            "env_files": [],
            "readmes": [],
            "risks": spec["_risks"],
        }

    assert source_dir is not None
    compose_file = select_compose_file(source_dir)
    dockerfile = select_dockerfile(source_dir)
    env_files = list_env_files(source_dir)
    readmes = list_readmes(source_dir)
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
    elif upstream_repo:
        if binary:
            spec = choose_route_for_binary(slug, meta, binary)
        else:
            raise ValueError("未发现 compose、Dockerfile 或可识别的 release binary")
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

    return {
        "slug": spec["slug"],
        "route": spec["build_strategy"],
        "spec": spec,
        "compose_file": compose_file,
        "dockerfile": dockerfile,
        "env_files": env_files,
        "readmes": readmes,
        "risks": spec.get("_risks", []),
    }


def apply_post_write(repo_root: Path, slug: str, post_write: dict[str, str]) -> list[str]:
    outputs: list[str] = []
    app_dir = repo_root / "apps" / slug
    for relative, content in post_write.items():
        path = app_dir / relative
        path.write_text(content, encoding="utf-8")
        outputs.append(str(path))
    return outputs


def post_process_signoz(repo_root: Path) -> list[str]:
    app_dir = repo_root / "apps" / "signoz"
    content_dir = app_dir / "content"
    (content_dir / "clickhouse").mkdir(parents=True, exist_ok=True)

    writes: dict[Path, str] = {
        app_dir / "lzc-manifest.yml": textwrap.dedent(
            """\
            lzc-sdk-version: '0.1'
            package: fun.selfstudio.app.migration.signoz
            version: 0.116.1
            min_os_version: 1.3.8
            name: SigNoz
            description: Open-source observability with traces, metrics, and logs
            license: Apache-2.0
            homepage: https://signoz.io
            author: SigNoz
            application:
              subdomain: signoz
              public_path:
                - /
              health_check:
                disable: true
                test_url: http://signoz:8080/api/v1/health
                start_period: 300s
                timeout: 10s
              upstreams:
                - location: /
                  backend: http://signoz:8080/
                  disable_auto_health_checking: true
            services:
              init-clickhouse:
                image: registry.lazycat.cloud/invokerlaw/clickhouse/clickhouse-server:ccb6549ae7e253ed
                command: >-
                  bash -lc 'set -e;
                  mkdir -p /var/lib/clickhouse/user_scripts;
                  if [ ! -x /var/lib/clickhouse/user_scripts/histogramQuantile ]; then
                  version="v0.0.1";
                  node_os=$$(uname -s | tr "[:upper:]" "[:lower:]");
                  node_arch=$$(uname -m | sed s/aarch64/arm64/ | sed s/x86_64/amd64/);
                  cd /tmp;
                  wget -O histogram-quantile.tar.gz "https://github.com/SigNoz/signoz/releases/download/histogram-quantile%2F$${version}/histogram-quantile_$${node_os}_$${node_arch}.tar.gz";
                  tar -xzf histogram-quantile.tar.gz;
                  mv histogram-quantile /var/lib/clickhouse/user_scripts/histogramQuantile;
                  chmod +x /var/lib/clickhouse/user_scripts/histogramQuantile;
                  fi'
                binds:
                  - /lzcapp/var/db/signoz/clickhouse:/var/lib/clickhouse

              zookeeper-1:
                image: registry.lazycat.cloud/invokerlaw/signoz/zookeeper:730916d2ce75de76
                user: root
                environment:
                  - ZOO_SERVER_ID=1
                  - ALLOW_ANONYMOUS_LOGIN=yes
                  - ZOO_AUTOPURGE_INTERVAL=1
                  - ZOO_ENABLE_PROMETHEUS_METRICS=yes
                  - ZOO_PROMETHEUS_METRICS_PORT_NUMBER=9141
                binds:
                  - /lzcapp/var/db/signoz/zookeeper:/bitnami/zookeeper
                healthcheck:
                  test: ["CMD-SHELL", "curl -s -m 2 http://localhost:8080/commands/ruok | grep error | grep null"]
                  interval: 30s
                  timeout: 5s
                  retries: 10

              clickhouse:
                image: registry.lazycat.cloud/invokerlaw/clickhouse/clickhouse-server:ccb6549ae7e253ed
                depends_on:
                  - init-clickhouse
                  - zookeeper-1
                environment:
                  - CLICKHOUSE_SKIP_USER_SETUP=1
                binds:
                  - /lzcapp/var/db/signoz/clickhouse:/var/lib/clickhouse
                setup_script: |
                  mkdir -p /etc/clickhouse-server/config.d /var/lib/clickhouse/user_scripts
                  cp /lzcapp/pkg/content/clickhouse/users.xml /etc/clickhouse-server/users.xml
                  cp /lzcapp/pkg/content/clickhouse/cluster.xml /etc/clickhouse-server/config.d/cluster.xml
                  cp /lzcapp/pkg/content/clickhouse/macros.xml /etc/clickhouse-server/config.d/macros.xml
                  cp /lzcapp/pkg/content/clickhouse/custom-function.xml /etc/clickhouse-server/custom-function.xml
                healthcheck:
                  test: ["CMD", "wget", "--spider", "-q", "0.0.0.0:8123/ping"]
                  interval: 30s
                  timeout: 5s
                  retries: 10

              signoz:
                image: registry.lazycat.cloud/invokerlaw/signoz/signoz:a16516d0ba0ee588
                depends_on:
                  - clickhouse
                  - signoz-telemetrystore-migrator
                entrypoint: /bin/sh
                command: >-
                  -lc 'mkdir -p /var/lib/signoz /var/lib/signoz/prometheus-active-query-tracker
                  /var/lib/signoz-runtime; until [ -f
                  /var/lib/signoz-runtime/migrations-ready ]; do sleep 3; done; exec
                  ./signoz server'
                environment:
                  - SIGNOZ_ALERTMANAGER_PROVIDER=signoz
                  - SIGNOZ_TELEMETRYSTORE_CLICKHOUSE_DSN=tcp://clickhouse:9000
                  - SIGNOZ_SQLSTORE_SQLITE_PATH=/var/lib/signoz/signoz.db
                  - SIGNOZ_TOKENIZER_JWT_SECRET=secret
                  - SIGNOZ_PROMETHEUS_ACTIVE__QUERY__TRACKER_PATH=/var/lib/signoz/prometheus-active-query-tracker
                binds:
                  - /lzcapp/var/data/signoz/sqlite:/var/lib/signoz
                  - /lzcapp/var/data/signoz/runtime:/var/lib/signoz-runtime
                healthcheck:
                  test: ["CMD", "wget", "--spider", "-q", "localhost:8080/api/v1/health"]
                  start_period: 300s
                  interval: 30s
                  timeout: 5s
                  retries: 20

              otel-collector:
                image: registry.lazycat.cloud/invokerlaw/signoz/signoz-otel-collector:85bd090294be0dbf
                depends_on:
                  - clickhouse
                  - signoz-telemetrystore-migrator
                environment:
                  - OTEL_RESOURCE_ATTRIBUTES=host.name=signoz-host,os.type=linux
                  - LOW_CARDINAL_EXCEPTION_GROUPING=false
                  - SIGNOZ_OTEL_COLLECTOR_CLICKHOUSE_DSN=tcp://clickhouse:9000
                  - SIGNOZ_OTEL_COLLECTOR_CLICKHOUSE_CLUSTER=cluster
                  - SIGNOZ_OTEL_COLLECTOR_CLICKHOUSE_REPLICATION=true
                  - SIGNOZ_OTEL_COLLECTOR_TIMEOUT=10m
                entrypoint: /bin/sh
                command: >-
                  -lc 'set -e; mkdir -p /var/lib/signoz-runtime; cp
                  /lzcapp/pkg/content/otel-collector-config.yaml
                  /var/tmp/otel-config.yaml; until [ -f
                  /var/lib/signoz-runtime/migrations-ready ]; do sleep 3; done;
                  /signoz-otel-collector migrate sync check --clickhouse-dsn
                  tcp://clickhouse:9000 --clickhouse-cluster cluster
                  --clickhouse-replication && exec /signoz-otel-collector --config
                  /var/tmp/otel-config.yaml'
                binds:
                  - /lzcapp/var/data/signoz/runtime:/var/lib/signoz-runtime
                healthcheck:
                  test: ["CMD", "true"]
                  interval: 30s
                  timeout: 5s
                  retries: 10

              signoz-telemetrystore-migrator:
                image: registry.lazycat.cloud/invokerlaw/signoz/signoz-otel-collector:85bd090294be0dbf
                user: root
                depends_on:
                  - clickhouse
                environment:
                  - SIGNOZ_OTEL_COLLECTOR_CLICKHOUSE_DSN=tcp://clickhouse:9000
                  - SIGNOZ_OTEL_COLLECTOR_CLICKHOUSE_CLUSTER=cluster
                  - SIGNOZ_OTEL_COLLECTOR_CLICKHOUSE_REPLICATION=true
                  - SIGNOZ_OTEL_COLLECTOR_TIMEOUT=10m
                entrypoint: /bin/sh
                command: >-
                  -lc 'set -e; mkdir -p /var/lib/signoz-runtime; rm -f
                  /var/lib/signoz-runtime/migrations-ready; until /signoz-otel-collector
                  migrate ready --clickhouse-dsn tcp://clickhouse:9000
                  --clickhouse-cluster cluster --clickhouse-replication; do sleep 3;
                  done; /signoz-otel-collector migrate bootstrap --clickhouse-dsn
                  tcp://clickhouse:9000 --clickhouse-cluster cluster
                  --clickhouse-replication; /signoz-otel-collector migrate sync up
                  --clickhouse-dsn tcp://clickhouse:9000 --clickhouse-cluster cluster
                  --clickhouse-replication; /signoz-otel-collector migrate async up
                  --clickhouse-dsn tcp://clickhouse:9000 --clickhouse-cluster cluster
                  --clickhouse-replication; touch /var/lib/signoz-runtime/migrations-ready'
                binds:
                  - /lzcapp/var/data/signoz/runtime:/var/lib/signoz-runtime
            locales:
              en:
                name: SigNoz
                description: Open-source observability with traces, metrics, and logs
              zh:
                name: SigNoz
                description: 开源可观测性平台，统一查看链路、指标和日志
            """
        ),
        app_dir / "lzc-build.yml": textwrap.dedent(
            """\
            lzc-sdk-version: '0.1'
            manifest: ./lzc-manifest.yml
            contentdir: ./content
            pkgout: ./
            icon: ./icon.png
            """
        ),
        app_dir / "README.md": textwrap.dedent(
            """\
            # SigNoz

            SigNoz 是一个基于 OpenTelemetry 的开源可观测性平台，提供 traces、metrics 和 logs 的统一查看入口。

            ## 上游信息

            - Upstream Repo: `SigNoz/signoz`
            - Homepage: `https://signoz.io`
            - License: `Apache-2.0`
            - Default Version: `0.116.1`

            ## 服务拓扑

            - `signoz`: Web UI 和 query-service，入口端口 `8080`
            - `clickhouse`: Telemetry 数据存储
            - `zookeeper-1`: ClickHouse replication / cluster metadata
            - `init-clickhouse`: 预下载 `histogramQuantile` 可执行文件
            - `otel-collector`: 执行 migration 并暴露 OTLP 接收端

            ## 持久化目录

            - `/lzcapp/var/db/signoz/clickhouse` -> `/var/lib/clickhouse`
            - `/lzcapp/var/db/signoz/zookeeper` -> `/bitnami/zookeeper`
            - `/lzcapp/var/data/signoz/sqlite` -> `/var/lib/signoz`

            ## 访问方式

            - UI: `https://signoz.${LAZYCAT_BOX_DOMAIN}`

            ## 说明

            - 该移植基于上游官方 `deploy/docker/docker-compose.yaml` 拆分。
            - ClickHouse 配置和 collector 配置放在 `content/` 下，通过 `lzc-build.yml` 打包进 `.lpk`。
            - collector 采用静态配置启动，不使用 OpAMP manager-config，避免首次启动阶段因 `orgId` 缺失阻塞。
            """
        ),
        app_dir / "UPSTREAM_DEPLOYMENT_CHECKLIST.md": textwrap.dedent(
            """\
            # SigNoz Upstream Deployment Checklist

            ## 已确认字段

            - PROJECT_NAME: SigNoz
            - PROJECT_SLUG: signoz
            - UPSTREAM_REPO: SigNoz/signoz
            - UPSTREAM_URL: https://github.com/SigNoz/signoz
            - HOMEPAGE: https://signoz.io
            - LICENSE: Apache-2.0
            - AUTHOR: SigNoz
            - VERSION: 0.116.1
            - IMAGE: signoz/signoz:v0.116.1
            - PORT: 8080

            ## 真实启动入口

            - 官方 compose: `deploy/docker/docker-compose.yaml`
            - 主服务: `signoz`
            - collector: `signoz-otel-collector`
            - 初始化链:
              - `init-clickhouse` 下载 `histogramQuantile`
              - `otel-collector migrate bootstrap`
              - `otel-collector migrate sync up`
              - `otel-collector migrate async up`
              - `otel-collector migrate sync check`

            ## 真实写路径

            - ClickHouse data: `/var/lib/clickhouse`
            - ClickHouse user scripts: `/var/lib/clickhouse/user_scripts`
            - ZooKeeper data: `/bitnami/zookeeper`
            - SigNoz sqlite: `/var/lib/signoz`
            - Collector runtime temp: `/var/tmp`

            ## 配置文件

            - ClickHouse cluster config: `deploy/common/clickhouse/cluster.xml`
            - ClickHouse users config: `deploy/common/clickhouse/users.xml`
            - ClickHouse custom function: `deploy/common/clickhouse/custom-function.xml`
            - Collector config: `deploy/docker/otel-collector-config.yaml`
            - OpAMP config: `deploy/common/signoz/otel-collector-opamp-config.yaml`

            ## 外部依赖

            - ClickHouse
            - ZooKeeper
            - SQLite

            ## LazyCat 适配结论

            - 保留官方多服务拓扑，不压成单容器。
            - ClickHouse 需要额外注入 `cluster.xml`、`users.xml`、`custom-function.xml` 和单机 `macros.xml`。
            - collector 不能直接沿用上游 `/etc` 写入路径，配置改复制到 `/var/tmp`。
            - collector 不使用 OpAMP manager-config，避免 `cannot create agent without orgId` 启动阻塞。
            - 显式设置 `SIGNOZ_PROMETHEUS_ACTIVE__QUERY__TRACKER_PATH`，避免默认空路径触发 active query tracker 目录报错。
            """
        ),
        repo_root / "registry" / "repos" / "signoz.json": textwrap.dedent(
            """\
            {
              "enabled": true,
              "upstream_repo": "SigNoz/signoz",
              "check_strategy": "github_release",
              "build_strategy": "official_image",
              "publish_to_store": false,
              "official_image_registry": "signoz/signoz",
              "precompiled_binary_url": "",
              "dockerfile_type": "custom",
              "service_port": 8080,
              "service_cmd": [],
              "image_targets": [
                "signoz"
              ],
              "dependencies": [
                {
                  "target_service": "init-clickhouse",
                  "source_image": "clickhouse/clickhouse-server:25.5.6"
                },
                {
                  "target_service": "zookeeper-1",
                  "source_image": "signoz/zookeeper:3.7.1"
                },
                {
                  "target_service": "clickhouse",
                  "source_image": "clickhouse/clickhouse-server:25.5.6"
                },
                {
                  "target_service": "otel-collector",
                  "source_image": "signoz/signoz-otel-collector:v0.144.2"
                }
              ]
            }
            """
        ),
        content_dir / "clickhouse" / "cluster.xml": textwrap.dedent(
            """\
            <?xml version="1.0"?>
            <clickhouse>
              <zookeeper>
                <node index="1">
                  <host>zookeeper-1</host>
                  <port>2181</port>
                </node>
              </zookeeper>
              <remote_servers>
                <cluster>
                  <shard>
                    <replica>
                      <host>clickhouse</host>
                      <port>9000</port>
                    </replica>
                  </shard>
                </cluster>
              </remote_servers>
            </clickhouse>
            """
        ),
        content_dir / "clickhouse" / "custom-function.xml": textwrap.dedent(
            """\
            <functions>
              <function>
                <type>executable</type>
                <name>histogramQuantile</name>
                <return_type>Float64</return_type>
                <argument>
                  <type>Array(Float64)</type>
                  <name>buckets</name>
                </argument>
                <argument>
                  <type>Array(Float64)</type>
                  <name>counts</name>
                </argument>
                <argument>
                  <type>Float64</type>
                  <name>quantile</name>
                </argument>
                <format>CSV</format>
                <command>./histogramQuantile</command>
              </function>
            </functions>
            """
        ),
        content_dir / "clickhouse" / "macros.xml": textwrap.dedent(
            """\
            <?xml version="1.0"?>
            <clickhouse>
              <macros>
                <shard>01</shard>
                <replica>clickhouse-01</replica>
              </macros>
            </clickhouse>
            """
        ),
        content_dir / "clickhouse" / "users.xml": textwrap.dedent(
            """\
            <?xml version="1.0"?>
            <clickhouse>
              <profiles>
                <default>
                  <max_memory_usage>10000000000</max_memory_usage>
                  <load_balancing>random</load_balancing>
                </default>
                <readonly>
                  <readonly>1</readonly>
                </readonly>
              </profiles>
              <users>
                <default>
                  <password></password>
                  <networks>
                    <ip>::/0</ip>
                  </networks>
                  <profile>default</profile>
                  <quota>default</quota>
                </default>
              </users>
              <quotas>
                <default>
                  <interval>
                    <duration>3600</duration>
                    <queries>0</queries>
                    <errors>0</errors>
                    <result_rows>0</result_rows>
                    <read_rows>0</read_rows>
                    <execution_time>0</execution_time>
                  </interval>
                </default>
              </quotas>
            </clickhouse>
            """
        ),
        content_dir / "otel-collector-config.yaml": textwrap.dedent(
            """\
            connectors:
              signozmeter:
                metrics_flush_interval: 1h
                dimensions:
                  - name: service.name
                  - name: deployment.environment
                  - name: host.name
            receivers:
              otlp:
                protocols:
                  grpc:
                    endpoint: 0.0.0.0:4317
                  http:
                    endpoint: 0.0.0.0:4318
              prometheus:
                config:
                  global:
                    scrape_interval: 60s
                  scrape_configs:
                    - job_name: otel-collector
                      static_configs:
                        - targets:
                            - localhost:8888
                          labels:
                            job_name: otel-collector
            processors:
              batch:
                send_batch_size: 10000
                send_batch_max_size: 11000
                timeout: 10s
              batch/meter:
                send_batch_max_size: 25000
                send_batch_size: 20000
                timeout: 1s
              resourcedetection:
                detectors: [env, system]
                timeout: 2s
              signozspanmetrics/delta:
                metrics_exporter: signozclickhousemetrics
                metrics_flush_interval: 60s
                latency_histogram_buckets: [100us, 1ms, 2ms, 6ms, 10ms, 50ms, 100ms, 250ms, 500ms, 1000ms, 1400ms, 2000ms, 5s, 10s, 20s, 40s, 60s]
                dimensions_cache_size: 100000
                aggregation_temporality: AGGREGATION_TEMPORALITY_DELTA
                enable_exp_histogram: true
                dimensions:
                  - name: service.namespace
                    default: default
                  - name: deployment.environment
                    default: default
                  - name: signoz.collector.id
                  - name: service.version
                  - name: browser.platform
                  - name: browser.mobile
                  - name: k8s.cluster.name
                  - name: k8s.node.name
                  - name: k8s.namespace.name
                  - name: host.name
                  - name: host.type
                  - name: container.name
            extensions:
              health_check:
                endpoint: 0.0.0.0:13133
              pprof:
                endpoint: 0.0.0.0:1777
            exporters:
              clickhousetraces:
                datasource: tcp://clickhouse:9000/signoz_traces
                low_cardinal_exception_grouping: ${env:LOW_CARDINAL_EXCEPTION_GROUPING}
                use_new_schema: true
              signozclickhousemetrics:
                dsn: tcp://clickhouse:9000/signoz_metrics
              clickhouselogsexporter:
                dsn: tcp://clickhouse:9000/signoz_logs
                timeout: 10s
                use_new_schema: true
              signozclickhousemeter:
                dsn: tcp://clickhouse:9000/signoz_meter
                timeout: 45s
                sending_queue:
                  enabled: false
              metadataexporter:
                cache:
                  provider: in_memory
                dsn: tcp://clickhouse:9000/signoz_metadata
                enabled: true
                timeout: 45s
            service:
              telemetry:
                logs:
                  encoding: json
              extensions:
                - health_check
                - pprof
              pipelines:
                traces:
                  receivers: [otlp]
                  processors: [signozspanmetrics/delta, batch]
                  exporters: [clickhousetraces, metadataexporter, signozmeter]
                metrics:
                  receivers: [otlp]
                  processors: [batch]
                  exporters: [signozclickhousemetrics, metadataexporter, signozmeter]
                metrics/prometheus:
                  receivers: [prometheus]
                  processors: [batch]
                  exporters: [signozclickhousemetrics, metadataexporter, signozmeter]
                logs:
                  receivers: [otlp]
                  processors: [batch]
                  exporters: [clickhouselogsexporter, metadataexporter, signozmeter]
                metrics/meter:
                  receivers: [signozmeter]
                  processors: [batch/meter]
                  exporters: [signozclickhousemeter]
            """
        ),
    }

    outputs: list[str] = []
    for path, content in writes.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        if path.suffix == ".sh":
            path.chmod(0o755)
        outputs.append(str(path))
    return outputs


def apply_app_post_process(repo_root: Path, finalized: dict[str, Any], analysis: dict[str, Any]) -> list[str]:
    upstream_repo = str(finalized.get("upstream_repo") or analysis["spec"].get("upstream_repo") or "").strip()
    if finalized["slug"] == "signoz" and upstream_repo == "SigNoz/signoz":
        return post_process_signoz(repo_root)
    if finalized["slug"] == "deer-flow" and upstream_repo == "bytedance/deer-flow":
        return post_process_deer_flow(repo_root)
    if finalized["slug"] == "multica" and upstream_repo == "multica-ai/multica":
        return post_process_multica(repo_root)
    return []


def apply_generated_app_fixes(finalized: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
    upstream_repo = str(finalized.get("upstream_repo") or analysis["spec"].get("upstream_repo") or "").strip()

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

    if finalized.get("slug") == "multica" and upstream_repo == "multica-ai/multica":
        finalized["service_port"] = 3000
        finalized["image_targets"] = ["multica", "web"]
        finalized["dependencies"] = [{"target_service": "postgres", "source_image": "pgvector/pgvector:pg17"}]
        finalized["service_builds"] = [
            {
                "target_service": "multica",
                "build_strategy": "upstream_dockerfile",
                "source_dockerfile_path": "Dockerfile",
                "build_context": ".",
                "build_args": {},
                "image_name": "multica",
            },
            {
                "target_service": "web",
                "build_strategy": "upstream_with_target_template",
                "dockerfile_path": "Dockerfile.web.template",
                "source_dockerfile_path": "Dockerfile.web.lazycat",
                "build_context": ".",
                "build_args": {},
                "image_name": "multica-web",
            },
        ]
        finalized["application"] = {
            "subdomain": "multica",
            "public_path": ["/"],
            "upstreams": [{"location": "/", "backend": "http://web:3000/"}],
        }
        finalized["services"] = {
            "multica": {
                "image": "registry.lazycat.cloud/placeholder/multica:multica",
                "depends_on": ["postgres"],
                "environment": [
                    "PORT=8080",
                    "DATABASE_URL=postgres://multica:multica@postgres:5432/multica?sslmode=disable",
                    "JWT_SECRET=${LAZYCAT_APP_ID}-${LAZYCAT_BOX_DOMAIN}-jwt",
                    'RESEND_API_KEY={{ default "" .U.resend_api_key }}',
                    'RESEND_FROM_EMAIL={{ default "noreply@multica.ai" .U.resend_from_email }}',
                ],
                "command": "sh -lc './migrate up && exec ./server'",
            },
            "web": {
                "image": "registry.lazycat.cloud/placeholder/multica:web",
                "depends_on": ["multica"],
                "environment": [
                    "REMOTE_API_URL=http://multica:8080",
                    "FRONTEND_PORT=3000",
                ],
                "command": "sh -lc 'cd apps/web && pnpm dev --hostname 0.0.0.0 --port ${FRONTEND_PORT:-3000}'",
            },
            "postgres": {
                "image": "registry.lazycat.cloud/placeholder/multica:postgres",
                "environment": [
                    "POSTGRES_DB=multica",
                    "POSTGRES_USER=multica",
                    "POSTGRES_PASSWORD=multica",
                ],
                "binds": ["/lzcapp/var/db/multica/postgres-v2:/var/lib/postgresql/data"],
            },
        }

        env_entries = bm.ensure_list(finalized.get("env_vars"))

        def upsert_env(name: str, value: str, description: str) -> None:
            for item in env_entries:
                if isinstance(item, dict) and str(item.get("name", "")).strip() == name:
                    item["value"] = value
                    item["required"] = False
                    item["description"] = description
                    return
            env_entries.append({"name": name, "value": value, "required": False, "description": description})

        upsert_env(
            "DATABASE_URL",
            "postgres://multica:multica@postgres:5432/multica?sslmode=disable",
            "连接内置 postgres 服务（由迁移器重写默认 localhost）",
        )
        upsert_env("PORT", "8080", "Multica server 监听端口")
        upsert_env(
            "JWT_SECRET",
            "${LAZYCAT_APP_ID}-${LAZYCAT_BOX_DOMAIN}-jwt",
            "服务端 JWT 签名密钥",
        )
        finalized["env_vars"] = env_entries

        notes = bm.ensure_list(finalized.get("startup_notes"))
        notes.append("检测到 compose 仅包含 PostgreSQL，已自动补齐 web + backend + postgres 三服务拓扑。")
        notes.append("已将 DATABASE_URL 默认值从 localhost 改写为 postgres 服务名，避免容器内回环连接失败。")
        notes.append("web 服务默认以 dev 模式启动；若浏览器出现 HMR WebSocket 报错，可忽略，不影响主流程。")
        notes.append("已对登录页注入容错补丁：/auth/send-code 失败时仍允许进入验证码步骤（开发态可用 888888）。")
        notes.append("支持通过 lzc-deploy-params.yml 配置 RESEND 邮件参数；若未配置则需在日志中查看验证码。")
        finalized["startup_notes"] = notes

    if finalized.get("slug") == "deer-flow" and upstream_repo == "bytedance/deer-flow":
        finalized["include_content"] = True
        finalized["image_targets"] = ["frontend", "gateway", "langgraph"]
        finalized["dependencies"] = [{"target_service": "nginx", "source_image": "nginx:alpine"}]
        finalized["service_builds"] = [
            {
                "target_service": "frontend",
                "additional_target_services": ["config-ui"],
                "build_strategy": "upstream_dockerfile",
                "source_dockerfile_path": "frontend/Dockerfile",
                "build_context": ".",
                "build_target": "dev",
                "build_args": {
                    "PNPM_STORE_PATH": "${PNPM_STORE_PATH:-/root/.local/share/pnpm/store}"
                },
                "image_name": "deer-flow-frontend",
            },
            {
                "target_service": "gateway",
                "build_strategy": "upstream_dockerfile",
                "source_dockerfile_path": "backend/Dockerfile",
                "build_context": ".",
                "build_args": {},
                "image_name": "deer-flow-gateway",
            },
            {
                "target_service": "langgraph",
                "build_strategy": "upstream_dockerfile",
                "source_dockerfile_path": "backend/Dockerfile",
                "build_context": ".",
                "build_args": {},
                "image_name": "deer-flow-langgraph",
            },
        ]
        finalized["application"] = {
            "subdomain": "deer-flow",
            "public_path": ["/"],
            "upstreams": [{"location": "/", "backend": "http://nginx:2026/"}],
            "health_check": {"test_url": "http://nginx:2026/health"},
        }
        finalized["env_vars"] = [
            {
                "name": "BETTER_AUTH_SECRET",
                "value": "${LAZYCAT_APP_ID}-${LAZYCAT_BOX_DOMAIN}-better-auth",
                "description": "前端会话密钥，默认按应用域名生成",
            },
            {"name": "OPENAI_API_KEY", "description": "默认模板模型使用的 API Key"},
            {"name": "OPENROUTER_API_KEY", "description": "可选 OpenAI-compatible 网关"},
            {"name": "ANTHROPIC_API_KEY", "description": "可选 Claude 模型"},
            {"name": "GEMINI_API_KEY", "description": "可选 Gemini 模型"},
            {"name": "GOOGLE_API_KEY", "description": "可选 Google 模型"},
            {"name": "DEEPSEEK_API_KEY", "description": "可选 DeepSeek 模型"},
            {"name": "VOLCENGINE_API_KEY", "description": "可选火山引擎模型"},
            {"name": "TAVILY_API_KEY", "description": "Web Search 工具"},
            {"name": "JINA_API_KEY", "description": "Web Fetch 工具"},
            {"name": "INFOQUEST_API_KEY", "description": "可选 InfoQuest 工具"},
            {"name": "FIRECRAWL_API_KEY", "description": "可选抓取工具"},
            {"name": "GITHUB_TOKEN", "description": "可选 GitHub MCP / API 访问令牌"},
            {
                "name": "LANGCHAIN_TRACING_V2",
                "value": "false",
                "description": "默认关闭 LangSmith tracing",
            },
        ]
        finalized["data_paths"] = [
            {
                "host": "/lzcapp/var/data/deer-flow/runtime",
                "container": "/app/backend/.deer-flow",
                "description": "DeerFlow 线程、workspace、uploads、outputs 持久化目录",
            },
            {
                "host": "/lzcapp/var/data/deer-flow/langgraph-api",
                "container": "/app/backend/.langgraph_api",
                "description": "LangGraph 运行时目录",
            },
        ]
        finalized["startup_notes"] = [
            "自动扫描到 compose 文件：docker/docker-compose.yaml",
            "首次访问会进入应用内配置页，用户通过下拉选项选择模型提供方和默认模型后再启动 DeerFlow。",
            "配置完成后可随时访问 `/settings/config` 重新修改。",
            "App Detail 中也会保留 Deployment Parameters 入口，作为高级默认值配置入口。",
            "当前默认走 LocalSandboxProvider，避免依赖 Docker Socket 或 Kubernetes provisioner。",
            "服务启动前会根据应用内表单状态自动渲染 `/deer-flow-state/config/config.yaml`。",
            "当前内置的是 OpenAI / OpenRouter 下拉选项；如果后续要支持更多 provider，可继续扩展 schema 和渲染脚本。",
        ]
        finalized["services"] = {
            "config-ui": {
                "image": "registry.lazycat.cloud/placeholder/deer-flow:frontend",
                "command": deer_flow_config_ui_command(),
                "environment": deer_flow_config_ui_env(),
                "binds": ["/lzcapp/var/data/deer-flow/runtime:/deer-flow-state"],
            },
            "nginx": {
                "image": "registry.lazycat.cloud/placeholder/deer-flow:nginx",
                "environment": deer_flow_deploy_param_env(),
                "binds": [
                    "/lzcapp/pkg/content/nginx.conf:/etc/nginx/nginx.conf",
                    "/lzcapp/var/data/deer-flow/runtime:/deer-flow-state",
                ],
                "command": deer_flow_bootstrap_command("exec nginx -g \"daemon off;\""),
            },
            "frontend": {
                "image": "registry.lazycat.cloud/placeholder/deer-flow:frontend",
                "command": deer_flow_bootstrap_command("cd /app/frontend && pnpm dev --hostname 0.0.0.0 --port 3000"),
                "environment": [
                    "BETTER_AUTH_SECRET=${LAZYCAT_APP_ID}-${LAZYCAT_BOX_DOMAIN}-better-auth",
                    "NODE_ENV=development",
                    "NEXT_TELEMETRY_DISABLED=1",
                ]
                + deer_flow_deploy_param_env(),
                "binds": ["/lzcapp/var/data/deer-flow/runtime:/deer-flow-state"],
            },
            "gateway": {
                "image": "registry.lazycat.cloud/placeholder/deer-flow:gateway",
                "command": deer_flow_bootstrap_command("cd /app/backend && PYTHONPATH=. uv run uvicorn app.gateway.app:app --host 0.0.0.0 --port 8001 --workers 2", wait_for_ready=True),
                "environment": deer_flow_runtime_env(),
                "binds": [
                    "/lzcapp/var/data/deer-flow/runtime:/deer-flow-state",
                    "/lzcapp/var/data/deer-flow/runtime:/app/backend/.deer-flow",
                ],
            },
            "langgraph": {
                "image": "registry.lazycat.cloud/placeholder/deer-flow:langgraph",
                "command": deer_flow_bootstrap_command("mkdir -p /app/backend/.langgraph_api && cd /app/backend && uv run langgraph dev --no-browser --allow-blocking --no-reload --host 0.0.0.0 --port 2024", wait_for_ready=True),
                "environment": deer_flow_runtime_env(include_tracing=True),
                "binds": [
                    "/lzcapp/var/data/deer-flow/runtime:/deer-flow-state",
                    "/lzcapp/var/data/deer-flow/runtime:/app/backend/.deer-flow",
                    "/lzcapp/var/data/deer-flow/langgraph-api:/app/backend/.langgraph_api",
                ],
            },
        }

    return finalized


def deer_flow_runtime_env(*, include_tracing: bool = False) -> list[str]:
    env = [
        "CI=true",
        "DEER_FLOW_HOME=/app/backend/.deer-flow",
        "DEER_FLOW_SHARED_STATE_DIR=/deer-flow-state",
        "DEER_FLOW_CONFIG_DIR=/deer-flow-state/config",
        "DEER_FLOW_CONFIG_PATH=/deer-flow-state/config/config.yaml",
        "DEER_FLOW_CONFIG_ENV_PATH=/deer-flow-state/config/model.env",
        "DEER_FLOW_READY_MARKER=/deer-flow-state/config/.lazycat-config-ready",
        "DEER_FLOW_EXTENSIONS_CONFIG_PATH=/deer-flow-state/config/extensions_config.json",
        "OPENAI_API_KEY",
        "OPENROUTER_API_KEY",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "DEEPSEEK_API_KEY",
        "VOLCENGINE_API_KEY",
        "TAVILY_API_KEY",
        "JINA_API_KEY",
        "INFOQUEST_API_KEY",
        "FIRECRAWL_API_KEY",
        "GITHUB_TOKEN",
    ] + deer_flow_deploy_param_env()
    if include_tracing:
        env.append("LANGCHAIN_TRACING_V2=false")
    return env


def deer_flow_prepare_runtime_clause() -> str:
    return (
        "mkdir -p /deer-flow-state/config "
        "/lzcapp/var/data/deer-flow/skills "
        "/lzcapp/var/data/deer-flow/runtime && "
        "if [ ! -f /deer-flow-state/config/extensions_config.json ]; then "
        "cp /lzcapp/pkg/content/extensions_config.json /deer-flow-state/config/extensions_config.json; fi && "
        "if [ ! -f /lzcapp/var/data/deer-flow/skills/README.md ]; then "
        "cp /lzcapp/pkg/content/skills/README.md /lzcapp/var/data/deer-flow/skills/README.md; fi && "
        "sh /lzcapp/pkg/content/render-deer-flow-config.sh && "
        "if [ -f /deer-flow-state/config/model.env ]; then set -a && . /deer-flow-state/config/model.env && set +a; fi"
    )


def deer_flow_wait_ready_clause() -> str:
    return (
        'echo "[deer-flow] waiting for model configuration"; '
        'until [ -f /deer-flow-state/config/.lazycat-config-ready ]; do sleep 2; done'
    )


def deer_flow_bootstrap_command(final_cmd: str, *, wait_for_ready: bool = False) -> str:
    segments = [deer_flow_prepare_runtime_clause()]
    if wait_for_ready:
        segments.append(deer_flow_wait_ready_clause())
    segments.append(final_cmd)
    return "sh -lc " + shlex.quote(" && ".join(segments))


def deer_flow_config_ui_command() -> str:
    return deer_flow_bootstrap_command("cd /app/frontend && node /lzcapp/pkg/content/config-ui/server.mjs")


def deer_flow_config_ui_env() -> list[str]:
    return [
        "PORT=3210",
        "CONFIG_UI_APP_NAME=DeerFlow",
        "CONFIG_UI_SCHEMA_PATH=/lzcapp/pkg/content/config-ui/deer-flow-schema.json",
        "CONFIG_UI_STATE_PATH=/deer-flow-state/config/model.env",
        "CONFIG_UI_READY_MARKER=/deer-flow-state/config/.lazycat-config-ready",
        "CONFIG_UI_RENDER_COMMAND=sh /lzcapp/pkg/content/render-deer-flow-config.sh",
        "CONFIG_UI_SETTINGS_PATH=/settings/config",
        "DEER_FLOW_SHARED_STATE_DIR=/deer-flow-state",
        "DEER_FLOW_CONFIG_DIR=/deer-flow-state/config",
        "DEER_FLOW_CONFIG_PATH=/deer-flow-state/config/config.yaml",
        "DEER_FLOW_CONFIG_ENV_PATH=/deer-flow-state/config/model.env",
        "DEER_FLOW_READY_MARKER=/deer-flow-state/config/.lazycat-config-ready",
        "DEER_FLOW_EXTENSIONS_CONFIG_PATH=/deer-flow-state/config/extensions_config.json",
    ] + deer_flow_deploy_param_env()


def deer_flow_deploy_param_env() -> list[str]:
    return [
        '{{ if index .U "model.provider_preset" }}DEER_FLOW_MODEL_PROVIDER_PRESET={{ index .U "model.provider_preset" }}{{ else }}DEER_FLOW_MODEL_PROVIDER_PRESET=openai{{ end }}',
        '{{ if index .U "model.name" }}DEER_FLOW_MODEL_NAME={{ index .U "model.name" }}{{ else }}DEER_FLOW_MODEL_NAME=default-chat{{ end }}',
        '{{ if index .U "model.display_name" }}DEER_FLOW_MODEL_DISPLAY_NAME={{ index .U "model.display_name" }}{{ else }}DEER_FLOW_MODEL_DISPLAY_NAME=Default Chat Model{{ end }}',
        '{{ if index .U "model.id" }}DEER_FLOW_MODEL_ID={{ index .U "model.id" }}{{ else }}DEER_FLOW_MODEL_ID=gpt-4.1-mini{{ end }}',
        '{{ if index .U "model.base_url" }}DEER_FLOW_MODEL_BASE_URL={{ index .U "model.base_url" }}{{ else }}DEER_FLOW_MODEL_BASE_URL={{ end }}',
        '{{ if index .U "model.api_key" }}DEER_FLOW_MODEL_API_KEY={{ index .U "model.api_key" }}{{ else }}DEER_FLOW_MODEL_API_KEY={{ end }}',
        '{{ if index .U "model.use_responses_api" }}DEER_FLOW_MODEL_USE_RESPONSES_API={{ index .U "model.use_responses_api" }}{{ else }}DEER_FLOW_MODEL_USE_RESPONSES_API=false{{ end }}',
        '{{ if index .U "model.temperature" }}DEER_FLOW_MODEL_TEMPERATURE={{ index .U "model.temperature" }}{{ else }}DEER_FLOW_MODEL_TEMPERATURE=0.7{{ end }}',
        '{{ if index .U "search.tavily_api_key" }}TAVILY_API_KEY={{ index .U "search.tavily_api_key" }}{{ else }}TAVILY_API_KEY={{ end }}',
        '{{ if index .U "fetch.jina_api_key" }}JINA_API_KEY={{ index .U "fetch.jina_api_key" }}{{ else }}JINA_API_KEY={{ end }}',
    ]


def render_deer_flow_config_script() -> str:
    return textwrap.dedent(
        """\
        #!/bin/sh
        set -eu

        CONFIG_PATH="${DEER_FLOW_CONFIG_PATH:-/deer-flow-state/config/config.yaml}"
        CONFIG_ENV_PATH="${DEER_FLOW_CONFIG_ENV_PATH:-/deer-flow-state/config/model.env}"
        READY_MARKER="${DEER_FLOW_READY_MARKER:-/deer-flow-state/config/.lazycat-config-ready}"
        CONFIG_DIR="$(dirname "$CONFIG_PATH")"
        mkdir -p "$CONFIG_DIR"

        quote_yaml() {
          printf '"%s"' "$(printf '%s' "$1" | sed 's/\\\\/\\\\\\\\/g; s/"/\\\\"/g')"
        }

        if [ -f "$CONFIG_ENV_PATH" ]; then
          # shellcheck disable=SC1090
          . "$CONFIG_ENV_PATH"
        fi

        provider="${DEER_FLOW_MODEL_PROVIDER_PRESET:-openai}"
        model_name="${DEER_FLOW_MODEL_NAME:-default-chat}"
        display_name="${DEER_FLOW_MODEL_DISPLAY_NAME:-Default Chat Model}"
        model_id="${DEER_FLOW_MODEL_ID:-gpt-4.1-mini}"
        base_url="${DEER_FLOW_MODEL_BASE_URL:-}"
        api_key_value="${DEER_FLOW_MODEL_API_KEY:-}"
        api_key_ref='\\$DEER_FLOW_MODEL_API_KEY'
        use_responses_api="${DEER_FLOW_MODEL_USE_RESPONSES_API:-false}"
        temperature="${DEER_FLOW_MODEL_TEMPERATURE:-0.7}"

        if [ "$provider" = "openrouter" ] && [ -z "$base_url" ]; then
          base_url="https://openrouter.ai/api/v1"
        fi

        {
          echo "# Generated from LazyCat deployment parameters."
          echo "# Re-open App Detail -> Deployment Parameters to update this config."
          echo "config_version: 3"
          echo "log_level: info"
          echo
          echo "models:"
          echo "  - name: $(quote_yaml "$model_name")"
          echo "    display_name: $(quote_yaml "$display_name")"
          echo "    use: langchain_openai:ChatOpenAI"
          echo "    model: $(quote_yaml "$model_id")"
          echo "    api_key: $api_key_ref"
          echo "    max_tokens: 4096"
          echo "    temperature: $temperature"
          if [ -n "$base_url" ]; then
            echo "    base_url: $(quote_yaml "$base_url")"
          fi
          if [ "$use_responses_api" = "true" ]; then
            echo "    use_responses_api: true"
            echo "    output_version: responses/v1"
          fi
          echo
          cat <<'EOF'
        tool_groups:
          - name: web
          - name: file:read
          - name: file:write
          - name: bash

        tools:
          - name: web_search
            group: web
            use: deerflow.community.tavily.tools:web_search_tool
            max_results: 5
          - name: web_fetch
            group: web
            use: deerflow.community.jina_ai.tools:web_fetch_tool
            timeout: 10
          - name: image_search
            group: web
            use: deerflow.community.image_search.tools:image_search_tool
            max_results: 5
          - name: ls
            group: file:read
            use: deerflow.sandbox.tools:ls_tool
          - name: read_file
            group: file:read
            use: deerflow.sandbox.tools:read_file_tool
          - name: write_file
            group: file:write
            use: deerflow.sandbox.tools:write_file_tool
          - name: str_replace
            group: file:write
            use: deerflow.sandbox.tools:str_replace_tool
          - name: bash
            group: bash
            use: deerflow.sandbox.tools:bash_tool

        sandbox:
          use: deerflow.sandbox.local:LocalSandboxProvider

        skills:
          path: /lzcapp/var/data/deer-flow/skills
          container_path: /mnt/skills

        title:
          enabled: true
          max_words: 6
          max_chars: 60
          model_name: null

        summarization:
          enabled: true
        EOF
        } > "$CONFIG_PATH"

        if [ -n "$model_id" ] && [ -n "$api_key_value" ]; then
          printf 'ready\\n' > "$READY_MARKER"
        else
          rm -f "$READY_MARKER"
        fi
        """
    )


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
          const modelPreset = modelPresetFromState || modelPresetFromEnv || provider?.defaultModel || provider?.models?.[0]?.id || "";
          const selectedModel = findModel(provider, modelPreset) || provider?.models?.[0] || null;
          return {
            provider: provider?.id || "",
            modelPreset,
            customModelId: persisted.DEER_FLOW_MODEL_ID || process.env.DEER_FLOW_MODEL_ID || selectedModel?.modelId || "",
            customDisplayName: persisted.DEER_FLOW_MODEL_DISPLAY_NAME || process.env.DEER_FLOW_MODEL_DISPLAY_NAME || selectedModel?.displayName || "",
            baseUrl: persisted.DEER_FLOW_MODEL_BASE_URL || process.env.DEER_FLOW_MODEL_BASE_URL || provider?.baseUrl || "",
            apiKey: persisted.DEER_FLOW_MODEL_API_KEY || process.env.DEER_FLOW_MODEL_API_KEY || "",
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
          const customModelId = String(submitted.customModelId || "").trim();
          if (!customModelId) {
            throw new Error("Model ID is required before DeerFlow can start.");
          }
          const submittedBaseUrl = String(submitted.baseUrl || "").trim();
          const resolvedBaseUrl = submittedBaseUrl || provider.baseUrl || "";
          if (provider.requiresBaseUrl && !resolvedBaseUrl) {
            throw new Error("Base URL is required for the custom OpenAI-compatible provider.");
          }
          const customDisplayName = String(submitted.customDisplayName || "").trim();
          return {
            DEER_FLOW_MODEL_PROVIDER_PRESET: provider.id,
            DEER_FLOW_MODEL_PRESET: model.id,
            DEER_FLOW_MODEL_NAME: model.name,
            DEER_FLOW_MODEL_DISPLAY_NAME: customDisplayName || model.displayName,
            DEER_FLOW_MODEL_ID: customModelId,
            DEER_FLOW_MODEL_BASE_URL: resolvedBaseUrl,
            DEER_FLOW_MODEL_USE_RESPONSES_API: model.useResponsesApi ? "true" : "false",
            DEER_FLOW_MODEL_TEMPERATURE: String(model.temperature ?? "0.7"),
            DEER_FLOW_MODEL_API_KEY: String(submitted.apiKey || "").trim(),
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
                  <div id="modelHint" class="hint">Pick a preset, or use it as a starting point and edit the model ID below.</div>
                </div>
              </div>
              <div class="grid">
                <div class="field">
                  <label for="customModelId">Model ID</label>
                  <input id="customModelId" type="text" autocomplete="off" placeholder="gpt-4.1-mini">
                  <div class="hint">Supports manual input. The preset only provides a suggested default.</div>
                </div>
                <div class="field">
                  <label for="customDisplayName">Display Name</label>
                  <input id="customDisplayName" type="text" autocomplete="off" placeholder="Optional custom label">
                  <div class="hint">Optional. If left empty, the selected preset label is used.</div>
                </div>
              </div>
              <div class="grid">
                <div class="field">
                  <label for="apiKey">API Key</label>
                  <input id="apiKey" type="password" autocomplete="off" placeholder="Paste the provider API key">
                  <div class="hint">Stored in the app data directory and exposed to DeerFlow as <code>DEER_FLOW_MODEL_API_KEY</code>.</div>
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
            const customModelIdEl = document.getElementById("customModelId");
            const customDisplayNameEl = document.getElementById("customDisplayName");
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
              const model = currentModel();
              if (!customModelIdEl.dataset.touched || providerEl.dataset.providerChanged === "true") {
                customModelIdEl.value = initialValues.customModelId || model?.modelId || "";
              }
              if (!customDisplayNameEl.dataset.touched || providerEl.dataset.providerChanged === "true") {
                customDisplayNameEl.value = initialValues.customDisplayName || model?.displayName || "";
              }
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
              const resolvedModelId = customModelIdEl.value || model.modelId;
              const resolvedDisplayName = customDisplayNameEl.value || model.displayName;
              const resolvedBaseUrl = baseUrlEl.value || provider.baseUrl || "";
              const bits = [
                "Provider: " + provider.label,
                "Model ID: " + resolvedModelId,
                "Label: " + resolvedDisplayName,
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
                customModelId: customModelIdEl.value,
                customDisplayName: customDisplayNameEl.value,
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
              const model = currentModel();
              if (!customModelIdEl.dataset.touched) {
                customModelIdEl.value = model.modelId || "";
              }
              if (!customDisplayNameEl.dataset.touched) {
                customDisplayNameEl.value = model.displayName || "";
              }
              updateResolved();
            });
            customModelIdEl.addEventListener("input", () => {
              customModelIdEl.dataset.touched = "true";
              updateResolved();
            });
            customDisplayNameEl.addEventListener("input", () => {
              customDisplayNameEl.dataset.touched = "true";
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
            customModelIdEl.value = initialValues.customModelId || "";
            customDisplayNameEl.value = initialValues.customDisplayName || "";
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


def render_deer_flow_config_ui_schema() -> str:
    return json.dumps(
        {
            "title": "Configure DeerFlow",
            "description": "Pick a hosted provider preset and default model. The package writes the result back into config.yaml and only then starts DeerFlow.",
            "submitLabel": "Save and Start",
            "defaultProvider": "openai",
            "providers": [
                {
                    "id": "openai",
                    "label": "OpenAI",
                    "baseUrl": "",
                    "defaultModel": "gpt-4.1-mini",
                    "models": [
                        {
                            "id": "gpt-4.1-mini",
                            "label": "GPT-4.1 Mini",
                            "name": "default-chat",
                            "displayName": "GPT-4.1 Mini",
                            "modelId": "gpt-4.1-mini",
                            "useResponsesApi": False,
                            "temperature": "0.7",
                            "summary": "Balanced default for DeerFlow.",
                        },
                        {
                            "id": "gpt-4.1",
                            "label": "GPT-4.1",
                            "name": "default-chat",
                            "displayName": "GPT-4.1",
                            "modelId": "gpt-4.1",
                            "useResponsesApi": False,
                            "temperature": "0.7",
                            "summary": "Higher quality general-purpose option.",
                        },
                        {
                            "id": "gpt-5-mini",
                            "label": "GPT-5 Mini",
                            "name": "default-chat",
                            "displayName": "GPT-5 Mini",
                            "modelId": "gpt-5-mini",
                            "useResponsesApi": True,
                            "temperature": "0.7",
                            "summary": "Uses the Responses API path recommended for GPT-5 models.",
                        },
                    ],
                },
                {
                    "id": "openrouter",
                    "label": "OpenRouter",
                    "baseUrl": "https://openrouter.ai/api/v1",
                    "requiresBaseUrl": False,
                    "defaultModel": "openai/gpt-4.1-mini",
                    "models": [
                        {
                            "id": "openai/gpt-4.1-mini",
                            "label": "OpenAI GPT-4.1 Mini",
                            "name": "default-chat",
                            "displayName": "OpenAI GPT-4.1 Mini",
                            "modelId": "openai/gpt-4.1-mini",
                            "useResponsesApi": False,
                            "temperature": "0.7",
                            "summary": "OpenAI model served through OpenRouter.",
                        },
                        {
                            "id": "google/gemini-2.5-flash-preview",
                            "label": "Gemini 2.5 Flash Preview",
                            "name": "default-chat",
                            "displayName": "Gemini 2.5 Flash Preview",
                            "modelId": "google/gemini-2.5-flash-preview",
                            "useResponsesApi": False,
                            "temperature": "0.7",
                            "summary": "Fast Google-hosted model routed through OpenRouter.",
                        },
                        {
                            "id": "anthropic/claude-sonnet-4",
                            "label": "Claude Sonnet 4",
                            "name": "default-chat",
                            "displayName": "Claude Sonnet 4",
                            "modelId": "anthropic/claude-sonnet-4",
                            "useResponsesApi": False,
                            "temperature": "0.7",
                            "summary": "Anthropic-hosted model routed through OpenRouter.",
                        },
                    ],
                },
                {
                    "id": "custom-openai",
                    "label": "Custom OpenAI-Compatible",
                    "baseUrl": "",
                    "requiresBaseUrl": True,
                    "defaultModel": "custom-gpt-4.1-mini",
                    "models": [
                        {
                            "id": "custom-gpt-4.1-mini",
                            "label": "GPT-4.1 Mini Compatible",
                            "name": "default-chat",
                            "displayName": "Custom GPT-4.1 Mini",
                            "modelId": "gpt-4.1-mini",
                            "useResponsesApi": False,
                            "temperature": "0.7",
                            "summary": "For self-hosted or gateway endpoints that speak the OpenAI Chat Completions API.",
                        },
                        {
                            "id": "custom-gpt-5-mini",
                            "label": "GPT-5 Mini Compatible",
                            "name": "default-chat",
                            "displayName": "Custom GPT-5 Mini",
                            "modelId": "gpt-5-mini",
                            "useResponsesApi": True,
                            "temperature": "0.7",
                            "summary": "For OpenAI-compatible endpoints that support the Responses API.",
                        },
                    ],
                },
            ],
        },
        ensure_ascii=True,
        indent=2,
    ) + "\n"


def render_deer_flow_nginx_conf() -> str:
    return textwrap.dedent(
        """\
        events {
            worker_connections 1024;
        }
        pid /tmp/nginx.pid;
        http {
            sendfile on;
            tcp_nopush on;
            tcp_nodelay on;
            keepalive_timeout 65;
            types_hash_max_size 2048;

            access_log /dev/stdout;
            error_log /dev/stderr;

            resolver 127.0.0.11 valid=10s ipv6=off;

            upstream config_ui {
                server config-ui:3210;
            }

            upstream gateway {
                server gateway:8001;
            }

            upstream langgraph {
                server langgraph:2024;
            }

            upstream frontend {
                server frontend:3000;
            }

            server {
                listen 2026 default_server;
                listen [::]:2026 default_server;
                server_name _;

                proxy_hide_header 'Access-Control-Allow-Origin';
                proxy_hide_header 'Access-Control-Allow-Methods';
                proxy_hide_header 'Access-Control-Allow-Headers';
                proxy_hide_header 'Access-Control-Allow-Credentials';

                add_header 'Access-Control-Allow-Origin' '*' always;
                add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, DELETE, PATCH, OPTIONS' always;
                add_header 'Access-Control-Allow-Headers' '*' always;

                if ($request_method = 'OPTIONS') {
                    return 204;
                }

                location = /__config_ready {
                    internal;
                    proxy_pass http://config_ui/internal/ready;
                    proxy_pass_request_body off;
                    proxy_set_header Content-Length "";
                    proxy_set_header X-Original-URI $request_uri;
                }

                location = /settings/config {
                    proxy_pass http://config_ui/settings/config;
                    proxy_http_version 1.1;
                    proxy_set_header Host $host;
                    proxy_set_header X-Real-IP $remote_addr;
                    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
                    proxy_set_header X-Forwarded-Proto $scheme;
                }

                location ^~ /__config/ {
                    proxy_pass http://config_ui;
                    proxy_http_version 1.1;
                    proxy_set_header Host $host;
                    proxy_set_header X-Real-IP $remote_addr;
                    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
                    proxy_set_header X-Forwarded-Proto $scheme;
                }

                location /api/langgraph/ {
                    rewrite ^/api/langgraph/(.*) /$1 break;
                    proxy_pass http://langgraph;
                    proxy_http_version 1.1;
                    proxy_set_header Host $host;
                    proxy_set_header X-Real-IP $remote_addr;
                    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
                    proxy_set_header X-Forwarded-Proto $scheme;
                    proxy_set_header Connection '';
                    proxy_buffering off;
                    proxy_cache off;
                    proxy_set_header X-Accel-Buffering no;
                    proxy_connect_timeout 600s;
                    proxy_send_timeout 600s;
                    proxy_read_timeout 600s;
                    chunked_transfer_encoding on;
                }

                location /api/models {
                    proxy_pass http://gateway;
                    proxy_http_version 1.1;
                    proxy_set_header Host $host;
                    proxy_set_header X-Real-IP $remote_addr;
                    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
                    proxy_set_header X-Forwarded-Proto $scheme;
                }

                location /api/memory {
                    proxy_pass http://gateway;
                    proxy_http_version 1.1;
                    proxy_set_header Host $host;
                    proxy_set_header X-Real-IP $remote_addr;
                    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
                    proxy_set_header X-Forwarded-Proto $scheme;
                }

                location /api/mcp {
                    proxy_pass http://gateway;
                    proxy_http_version 1.1;
                    proxy_set_header Host $host;
                    proxy_set_header X-Real-IP $remote_addr;
                    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
                    proxy_set_header X-Forwarded-Proto $scheme;
                }

                location /api/skills {
                    proxy_pass http://gateway;
                    proxy_http_version 1.1;
                    proxy_set_header Host $host;
                    proxy_set_header X-Real-IP $remote_addr;
                    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
                    proxy_set_header X-Forwarded-Proto $scheme;
                }

                location /api/agents {
                    proxy_pass http://gateway;
                    proxy_http_version 1.1;
                    proxy_set_header Host $host;
                    proxy_set_header X-Real-IP $remote_addr;
                    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
                    proxy_set_header X-Forwarded-Proto $scheme;
                }

                location ~ ^/api/threads/[^/]+/uploads {
                    proxy_pass http://gateway;
                    proxy_http_version 1.1;
                    proxy_set_header Host $host;
                    proxy_set_header X-Real-IP $remote_addr;
                    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
                    proxy_set_header X-Forwarded-Proto $scheme;
                    client_max_body_size 100M;
                    proxy_request_buffering off;
                }

                location ~ ^/api/threads {
                    proxy_pass http://gateway;
                    proxy_http_version 1.1;
                    proxy_set_header Host $host;
                    proxy_set_header X-Real-IP $remote_addr;
                    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
                    proxy_set_header X-Forwarded-Proto $scheme;
                }

                location /docs {
                    proxy_pass http://gateway;
                    proxy_http_version 1.1;
                    proxy_set_header Host $host;
                    proxy_set_header X-Real-IP $remote_addr;
                    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
                    proxy_set_header X-Forwarded-Proto $scheme;
                }

                location /redoc {
                    proxy_pass http://gateway;
                    proxy_http_version 1.1;
                    proxy_set_header Host $host;
                    proxy_set_header X-Real-IP $remote_addr;
                    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
                    proxy_set_header X-Forwarded-Proto $scheme;
                }

                location /openapi.json {
                    proxy_pass http://gateway;
                    proxy_http_version 1.1;
                    proxy_set_header Host $host;
                    proxy_set_header X-Real-IP $remote_addr;
                    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
                    proxy_set_header X-Forwarded-Proto $scheme;
                }

                location /health {
                    proxy_pass http://config_ui/health;
                    proxy_http_version 1.1;
                    proxy_set_header Host $host;
                    proxy_set_header X-Real-IP $remote_addr;
                    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
                    proxy_set_header X-Forwarded-Proto $scheme;
                }

                location / {
                    auth_request /__config_ready;
                    error_page 401 = /settings/config;
                    proxy_pass http://frontend;
                    proxy_http_version 1.1;
                    proxy_set_header Host $host;
                    proxy_set_header X-Real-IP $remote_addr;
                    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
                    proxy_set_header X-Forwarded-Proto $scheme;
                    proxy_set_header Upgrade $http_upgrade;
                    proxy_set_header Connection 'upgrade';
                    proxy_cache_bypass $http_upgrade;
                    proxy_connect_timeout 600s;
                    proxy_send_timeout 600s;
                    proxy_read_timeout 600s;
                }
            }
        }
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


def render_deer_flow_config_validator() -> str:
    return textwrap.dedent(
        """\
        export async function validateConfig(content) {
          const raw = String(content || "").replace(/\\r\\n/g, "\\n");
          const modelsMatch = raw.match(/^models:\\s*$/m);
          if (!modelsMatch) {
            return {
              ready: false,
              error: "Missing `models:` section. Add at least one model before starting DeerFlow.",
            };
          }

          const afterModels = raw.slice(modelsMatch.index + modelsMatch[0].length);
          const nextRootKey = afterModels.search(/^\\S/m);
          const modelBlock = nextRootKey === -1 ? afterModels : afterModels.slice(0, nextRootKey);
          const listItems = modelBlock
            .split("\\n")
            .map((line) => line.trim())
            .filter((line) => line.startsWith("-"));

          if (listItems.length === 0) {
            return {
              ready: false,
              error: "No models configured. Add at least one item under `models:`.",
            };
          }

          const nameFields = modelBlock
            .split("\\n")
            .map((line) => line.trim())
            .filter((line) => line.startsWith("name:") || line.includes(" name:"));

          if (nameFields.length === 0) {
            return {
              ready: false,
              error: "Each DeerFlow model should define a `name:` field.",
            };
          }

          return {
            ready: true,
            summary: `Detected ${nameFields.length} configured model(s).`,
          };
        }
        """
    )


def post_process_deer_flow(repo_root: Path) -> list[str]:
    app_dir = repo_root / "apps" / "deer-flow"
    content_dir = app_dir / "content"
    skills_dir = content_dir / "skills"
    config_ui_dir = content_dir / "config-ui"
    skills_dir.mkdir(parents=True, exist_ok=True)
    config_ui_dir.mkdir(parents=True, exist_ok=True)

    writes = {
        app_dir / "lzc-deploy-params.yml": textwrap.dedent(
            """\
            params:
              - id: model.provider_preset
                type: string
                name: Provider Preset
                description: "Advanced defaults for DeerFlow. Preferred day-to-day UX is /settings/config."
                default_value: "openai"
                optional: true
              - id: model.name
                type: string
                name: Internal Model Name
                description: "Advanced default only."
                default_value: "default-chat"
                optional: true
              - id: model.display_name
                type: string
                name: Display Name
                description: "Advanced default only."
                default_value: "Default Chat Model"
                optional: true
              - id: model.id
                type: string
                name: API Model ID
                description: "Advanced default only."
                default_value: "gpt-4.1-mini"
                optional: true
              - id: model.base_url
                type: string
                name: Base URL
                description: "Optional advanced default for OpenAI-compatible endpoints."
                default_value: ""
                optional: true
              - id: model.api_key
                type: string
                name: API Key
                description: "Optional advanced default."
                default_value: ""
                optional: true
              - id: model.use_responses_api
                type: string
                name: Use Responses API
                description: "Optional advanced default."
                default_value: "false"
                optional: true
              - id: model.temperature
                type: string
                name: Temperature
                description: "Optional advanced default."
                default_value: "0.7"
                optional: true
              - id: search.tavily_api_key
                type: string
                name: Tavily API Key
                description: "Optional advanced default."
                default_value: ""
                optional: true
              - id: fetch.jina_api_key
                type: string
                name: Jina API Key
                description: "Optional advanced default."
                default_value: ""
                optional: true
            """
        ),
        content_dir / "config.yaml": textwrap.dedent(
            """\
            # DeerFlow config template for LazyCat single-node deployment.
            # This template is intentionally boot-safe: no model API key is required at startup.
            # The packaged config-ui writes model.env, and render-deer-flow-config.sh rewrites this file from it.

            config_version: 3
            log_level: info

            models: []

            tool_groups:
              - name: web
              - name: file:read
              - name: file:write
              - name: bash

            tools:
              - name: web_search
                group: web
                use: deerflow.community.tavily.tools:web_search_tool
                max_results: 5
              - name: web_fetch
                group: web
                use: deerflow.community.jina_ai.tools:web_fetch_tool
                timeout: 10
              - name: image_search
                group: web
                use: deerflow.community.image_search.tools:image_search_tool
                max_results: 5
              - name: ls
                group: file:read
                use: deerflow.sandbox.tools:ls_tool
              - name: read_file
                group: file:read
                use: deerflow.sandbox.tools:read_file_tool
              - name: write_file
                group: file:write
                use: deerflow.sandbox.tools:write_file_tool
              - name: str_replace
                group: file:write
                use: deerflow.sandbox.tools:str_replace_tool
              - name: bash
                group: bash
                use: deerflow.sandbox.tools:bash_tool

            sandbox:
              use: deerflow.sandbox.local:LocalSandboxProvider

            skills:
              path: /lzcapp/var/data/deer-flow/skills
              container_path: /mnt/skills

            title:
              enabled: true
              max_words: 6
              max_chars: 60
              model_name: null

            summarization:
              enabled: true
            """
        ),
        content_dir / "extensions_config.json": textwrap.dedent(
            """\
            {
              "mcpServers": {},
              "skills": {}
            }
            """
        ),
        content_dir / "render-deer-flow-config.sh": render_deer_flow_config_script(),
        config_ui_dir / "server.mjs": render_config_ui_server(),
        config_ui_dir / "deer-flow-schema.json": render_deer_flow_config_ui_schema(),
        content_dir / "nginx.conf": render_deer_flow_nginx_conf(),
        skills_dir / "README.md": textwrap.dedent(
            """\
            Place custom DeerFlow skills in this directory.

            This LazyCat package defaults to `skills.path: /lzcapp/var/data/deer-flow/skills`,
            so files stored here persist across upgrades.
            """
        ),
    }

    outputs: list[str] = []
    for path, content in writes.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        if path.suffix in {".sh", ".mjs"}:
            path.chmod(0o755)
        outputs.append(str(path))
    return outputs


def post_process_multica(repo_root: Path) -> list[str]:
    app_dir = repo_root / "apps" / "multica"
    app_dir.mkdir(parents=True, exist_ok=True)
    template_path = app_dir / "Dockerfile.web.template"
    deploy_params_path = app_dir / "lzc-deploy-params.yml"
    template_path.write_text(
        textwrap.dedent(
            """\
            FROM node:20-alpine AS runtime
            RUN corepack enable
            WORKDIR /src
            COPY . .
            RUN pnpm install --frozen-lockfile
            # LazyCat migration patch: allow login UI to continue when /auth/send-code fails.
            # Backend still accepts master code 888888 in non-production APP_ENV.
            RUN sed -i "s/await sendCode(email);/await sendCode(email).catch(() => {});/g" '/src/apps/web/app/(auth)/login/page.tsx'
            ENV NODE_ENV=production
            ENV FRONTEND_PORT=3000
            ENV REMOTE_API_URL=http://multica:8080
            EXPOSE 3000
            CMD ["sh", "-lc", "cd apps/web && pnpm dev --hostname 0.0.0.0 --port ${FRONTEND_PORT:-3000}"]
            """
        ),
        encoding="utf-8",
    )
    deploy_params_path.write_text(
        textwrap.dedent(
            """\
            params:
              - id: resend_api_key
                type: string
                name: Resend API Key
                description: 用于发送登录验证码邮件。留空时不会发送邮件，验证码需要在应用日志中查看。
                optional: true

              - id: resend_from_email
                type: string
                name: Resend From Email
                description: 发件人邮箱地址（例如 no-reply@yourdomain.com）。未填写时默认使用 noreply@multica.ai。
                default_value: noreply@multica.ai
                optional: true
            """
        ),
        encoding="utf-8",
    )

    return [str(template_path), str(deploy_params_path)]


def preflight_check(repo_root: Path, slug: str) -> tuple[bool, list[str]]:
    issues: list[str] = []
    app_dir = repo_root / "apps" / slug
    config_path = repo_root / "registry" / "repos" / f"{slug}.json"
    index_path = repo_root / "registry" / "repos" / "index.json"
    manifest_path = app_dir / "lzc-manifest.yml"
    build_path = app_dir / "lzc-build.yml"

    for required in (manifest_path, build_path, config_path, index_path, app_dir / "README.md", app_dir / "icon.png"):
        if not required.exists():
            issues.append(f"missing required file: {required}")

    if issues:
        return False, issues

    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return False, [f"invalid config json: {exc}"]

    index = json.loads(index_path.read_text(encoding="utf-8"))
    if f"{slug}.json" not in index.get("repos", []):
        issues.append(f"{slug}.json not registered in registry/repos/index.json")

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

    if config.get("build_strategy") == "official_image" and not str(config.get("official_image_registry", "")).strip():
        issues.append("official_image strategy requires official_image_registry")
    if config.get("build_strategy") == "precompiled_binary" and not str(config.get("precompiled_binary_url", "")).strip():
        issues.append("precompiled_binary strategy requires precompiled_binary_url")
    for service_name, payload in services.items():
        if isinstance(payload, dict) and payload.get("command") and payload.get("setup_script"):
            issues.append(f"service {service_name} defines both command and setup_script")

    build_yml = build_path.read_text(encoding="utf-8")
    if "/lzcapp/pkg/content/" in manifest_path.read_text(encoding="utf-8") and "contentdir:" not in build_yml:
        issues.append("manifest references /lzcapp/pkg/content but lzc-build.yml is missing contentdir")

    return not issues, issues


def detect_gh_token(env: dict[str, str]) -> str:
    if command_exists("gh"):
        token = sh(["gh", "auth", "token"], check=False)
        if token:
            return token
    token = env.get("GH_PAT") or env.get("GH_TOKEN") or env.get("GITHUB_TOKEN")
    if token:
        return token
    return ""


def detect_lzc_cli_token(env: dict[str, str]) -> str:
    token = env.get("LZC_CLI_TOKEN", "").strip()
    if token:
        return token
    if command_exists("lzc-cli"):
        config_value = sh(["lzc-cli", "config", "get", "token"], check=False).strip()
        if config_value:
            parts = config_value.split()
            if len(parts) >= 2:
                return parts[-1].strip()
    return ""


def run_local_build(
    repo_root: Path,
    slug: str,
    full_install: bool,
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
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
    if not full_install:
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
        return subprocess.CompletedProcess(cmd, proc.returncode, stdout=output, stderr="")

    if full_install:
        install_cmd = ["lzc-cli", "app", "install", str(lpk_output)]
        package_id = manifest_package_id(repo_root, slug)
        uninstall_output = ""
        if package_id:
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
        return subprocess.CompletedProcess(install_cmd, install_result.returncode, stdout=combined, stderr="")

    return subprocess.CompletedProcess(cmd, 0, stdout=output, stderr="")


def manifest_package_id(repo_root: Path, slug: str) -> str:
    manifest = (repo_root / "apps" / slug / "lzc-manifest.yml").read_text(encoding="utf-8")
    match = re.search(r"^package:\s*(.+)$", manifest, re.MULTILINE)
    return match.group(1).strip() if match else ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run LazyCat migration SOP from a single upstream address.")
    parser.add_argument("source", help="GitHub repo URL, owner/repo, compose URL, docker image, or local repo path")
    parser.add_argument("--repo-root", default="", help="Path to lzcat-apps repository root")
    parser.add_argument("--force", action="store_true", help="Overwrite managed files if the target app already exists")
    parser.add_argument("--no-build", action="store_true", help="Stop after preflight instead of attempting build/install")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve() if args.repo_root else Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    runtime_name, runtime_env, cleanup_runtime = prepare_container_env(env)
    gh_token = detect_gh_token(runtime_env)
    if gh_token:
        # Keep all aliases in sync so downstream scripts don't accidentally
        # pick a stale token due to environment-variable precedence.
        runtime_env["GH_PAT"] = gh_token
        runtime_env["GH_TOKEN"] = gh_token
        runtime_env["GITHUB_TOKEN"] = gh_token
    lzc_cli_token = detect_lzc_cli_token(runtime_env)
    if lzc_cli_token:
        runtime_env["LZC_CLI_TOKEN"] = lzc_cli_token

    normalized = normalize_source(args.source)
    source_dir: Path | None = None
    cleanup = lambda: None

    step1_outputs = [f"source={args.source}", f"kind={normalized['kind']}"]
    step1_risks: list[str] = []
    try:
        source_dir, extra_outputs, cleanup = prepare_source(normalized)
        step1_outputs.extend(extra_outputs)
        step_report(
            1,
            "收集上游信息",
            conclusion=f"已识别输入类型为 `{normalized['kind']}`，并准备好可分析的上游材料。",
            outputs=step1_outputs,
            scripts=["scripts/full-migrate.sh", "git clone" if normalized["kind"] == "github_repo" else "无"],
            risks=step1_risks,
            next_step="进入 [2/10] 选择移植路线",
        )

        analysis = analyze_source(normalized, source_dir)
        step2_outputs = [
            f"slug={analysis['slug']}",
            f"route={analysis['route']}",
        ]
        if analysis["compose_file"]:
            step2_outputs.append(f"compose={analysis['compose_file']}")
        if analysis["dockerfile"]:
            step2_outputs.append(f"dockerfile={analysis['dockerfile']}")
        step_report(
            2,
            "选择移植路线",
            conclusion=f"已自动推断构建路线为 `{analysis['route']}`。",
            outputs=step2_outputs,
            scripts=["scripts/full-migrate.sh"],
            risks=analysis["risks"],
            next_step="进入 [3/10] 注册目标 app",
        )

        finalized = bm.finalize_spec(analysis["spec"], gh_token, fetch_upstream=False)
        finalized = apply_generated_app_fixes(finalized, analysis)
        config_path = repo_root / "registry" / "repos" / f"{finalized['slug']}.json"
        app_dir = repo_root / "apps" / finalized["slug"]
        step_report(
            3,
            "注册目标 app",
            conclusion=f"目标 app 将注册为 `{finalized['slug']}`。",
            outputs=[str(app_dir), str(config_path)],
            scripts=["scripts/full-migrate.sh"],
            risks=["目标 app 已存在时会自动覆盖当前托管文件"] if not args.force else [],
            next_step="进入 [4/10] 建立项目骨架",
        )

        effective_force = args.force
        try:
            written = bm.write_files(repo_root, finalized, effective_force)
        except FileExistsError:
            if args.force:
                raise
            effective_force = True
            finalized.setdefault("_risks", []).append("目标 app 已存在，自动覆盖当前托管文件后继续")
            written = bm.write_files(repo_root, finalized, effective_force)
        post_written = apply_post_write(repo_root, finalized["slug"], analysis["spec"].get("_post_write", {}))
        post_written.extend(apply_app_post_process(repo_root, finalized, analysis))
        step_report(
            4,
            "建立项目骨架",
            conclusion="已在 monorepo 中创建 app 目录和 registry 配置。",
            outputs=[str(path) for path in written[:6]],
            scripts=["scripts/full-migrate.sh", "scripts/bootstrap_migration.py"],
            risks=[],
            next_step="进入 [5/10] 编写 lzc-manifest.yml",
        )

        step_report(
            5,
            "编写 lzc-manifest.yml",
            conclusion="manifest 已按自动推断的服务拓扑、入口端口、环境变量和持久化目录生成初稿。",
            outputs=[str(app_dir / "lzc-manifest.yml")],
            scripts=["scripts/full-migrate.sh", "scripts/bootstrap_migration.py"],
            risks=analysis["risks"],
            next_step="进入 [6/10] 补齐剩余文件",
        )

        step6_outputs = [str(app_dir / "README.md"), str(app_dir / "lzc-build.yml"), str(app_dir / "UPSTREAM_DEPLOYMENT_CHECKLIST.md")]
        step6_outputs.extend(post_written)
        step_report(
            6,
            "补齐剩余文件",
            conclusion="README、build 配置、checklist 以及需要的模板文件已补齐。",
            outputs=step6_outputs,
            scripts=["scripts/full-migrate.sh", "scripts/bootstrap_migration.py"],
            risks=[],
            next_step="进入 [7/10] 运行预检",
        )

        ok, issues = preflight_check(repo_root, finalized["slug"])
        if not ok:
            step_report(
                7,
                "运行预检",
                conclusion="预检未通过，当前自动流程停在文件层修复前。",
                outputs=[str(app_dir)],
                scripts=["scripts/full-migrate.sh"],
                risks=issues,
                next_step="停止，先修复预检问题",
            )
            return 1

        step_report(
            7,
            "运行预检",
            conclusion="预检通过，骨架和 registry 注册已满足进入构建阶段的最低条件。",
            outputs=[str(app_dir / "lzc-manifest.yml"), str(config_path)],
            scripts=["scripts/full-migrate.sh"],
            risks=[],
            next_step="进入 [8/10] 触发并监听构建",
        )

        if args.no_build:
            step_report(
                8,
                "触发并监听构建",
                conclusion="按 `--no-build` 要求，自动流程在预检后停止。",
                outputs=[str(app_dir)],
                scripts=["scripts/full-migrate.sh"],
                risks=[],
                next_step="停止",
            )
            return 0

        if not runtime_name:
            step_report(
                8,
                "触发并监听构建",
                conclusion="当前机器缺少可用的容器引擎，无法进入本地构建阶段。",
                outputs=[str(app_dir)],
                scripts=["scripts/full-migrate.sh", "scripts/local_build.sh"],
                risks=["既没有 docker，也没有 podman 可供兼容桥接"],
                next_step="停止，补齐容器引擎后重跑同一命令即可继续",
            )
            return 1

        full_install = bool(runtime_env.get("LZC_CLI_TOKEN")) and command_exists("lzc-cli")
        build_result = run_local_build(repo_root, finalized["slug"], full_install=full_install, env=runtime_env)
        if build_result.returncode != 0:
            step_report(
                8,
                "触发并监听构建",
                conclusion="本地构建失败，自动流程停在构建阶段。",
                outputs=[str(app_dir), str(repo_root / "dist" / f"{finalized['slug']}.lpk")],
                scripts=["scripts/full-migrate.sh", "scripts/run_build.py"],
                risks=[build_result.stderr.strip() or "run_build 返回非零退出码"],
                next_step="停止，修复构建错误后重跑同一命令即可继续",
            )
            return 1

        step_report(
            8,
            "触发并监听构建",
            conclusion="本地构建命令执行成功。",
            outputs=[str(repo_root / "dist" / f"{finalized['slug']}.lpk")],
            scripts=["scripts/full-migrate.sh", "scripts/run_build.py"],
            risks=[] if full_install else [f"当前使用 `{runtime_name}` 做 dry-run 构建，未执行远端 copy-image / install"],
            next_step="进入 [9/10] 下载并核对 .lpk",
        )

        lpk_path = repo_root / "dist" / f"{finalized['slug']}.lpk"
        if not lpk_path.exists():
            step_report(
                9,
                "下载并核对 .lpk",
                conclusion="构建阶段未产出本地 .lpk，流程停在产物阶段。",
                outputs=[str(lpk_path)],
                scripts=["scripts/full-migrate.sh", "scripts/run_build.py"],
                risks=["dist 目录中未发现期望的 lpk 文件"],
                next_step="停止",
            )
            return 1

        step_report(
            9,
            "下载并核对 .lpk",
            conclusion="已拿到本地构建产物并完成基本核对。",
            outputs=[f"{lpk_path} (sha256={file_sha256(lpk_path)})"],
            scripts=["scripts/full-migrate.sh", "scripts/run_build.py"],
            risks=[] if full_install else ["当前产物来自 dry-run，本步未覆盖真实 release/download 链路"],
            next_step="进入 [10/10] 安装验收并复盘",
        )

        if not full_install:
            step_report(
                10,
                "安装验收并复盘",
                conclusion="当前环境没有进入自动安装验收链路，流程停在本地产物阶段。",
                outputs=[str(lpk_path)],
                scripts=["scripts/full-migrate.sh"],
                risks=["缺少 LZC_CLI_TOKEN，未执行 `lzc-cli app install` 和后续状态验证"],
                next_step="停止，补齐 LZC_CLI_TOKEN 后重跑即可继续安装验收",
            )
            return 0

        package_id = manifest_package_id(repo_root, finalized["slug"])
        status_output = sh(["lzc-cli", "app", "status", package_id], check=False)
        step_report(
            10,
            "安装验收并复盘",
            conclusion="已执行安装命令，并完成一次基础状态查询。",
            outputs=[str(lpk_path), f"package={package_id}", f"status={status_output or '无输出'}"],
            scripts=["scripts/full-migrate.sh", "scripts/run_build.py", "lzc-cli app status"],
            risks=[],
            next_step="完成",
        )
        return 0
    except Exception as exc:
        step_report(
            1 if source_dir is None else 2,
            "自动迁移失败",
            conclusion="自动流程在当前步骤抛出异常。",
            outputs=[str(exc)],
            scripts=["scripts/full-migrate.sh"],
            risks=[str(exc)],
            next_step="停止",
        )
        return 1
    finally:
        cleanup()
        cleanup_runtime()


if __name__ == "__main__":
    raise SystemExit(main())
