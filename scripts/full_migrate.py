#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
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


def prepare_source(normalized: dict[str, Any]) -> tuple[Path | None, list[str], callable]:
    if normalized["kind"] == "local_repo":
        return normalized["path"], [str(normalized["path"])], lambda: None

    temp_root = Path(tempfile.mkdtemp(prefix="lzcat-full-migrate-"))
    outputs: list[str] = []

    if normalized["kind"] == "github_repo":
        repo_dir = temp_root / normalized["upstream_repo"].split("/", 1)[1]
        sh([
            "git",
            "clone",
            "--depth",
            "1",
            "--recurse-submodules",
            "--shallow-submodules",
            normalized["homepage"] + ".git",
            str(repo_dir),
        ])
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
        if any(token in name for token in ("linux", "amd64", "x86_64")) and name.endswith((".tar.gz", ".tgz", ".zip")):
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
                  interval: 30s
                  timeout: 5s
                  retries: 10

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
        outputs.append(str(path))
    return outputs


def apply_app_post_process(repo_root: Path, finalized: dict[str, Any], analysis: dict[str, Any]) -> list[str]:
    upstream_repo = str(finalized.get("upstream_repo") or analysis["spec"].get("upstream_repo") or "").strip()
    if finalized["slug"] == "signoz" and upstream_repo == "SigNoz/signoz":
        return post_process_signoz(repo_root)
    return []


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
    token = env.get("GH_TOKEN") or env.get("GITHUB_TOKEN")
    if token:
        return token
    if command_exists("gh"):
        token = sh(["gh", "auth", "token"], check=False)
        if token:
            return token
    return ""


def run_local_build(
    repo_root: Path,
    slug: str,
    full_install: bool,
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    cmd = ["bash", "./scripts/local_build.sh", slug, "--force-build"]
    if full_install:
        cmd.extend(["--install", "--with-docker", "--no-dry-run"])
    result = subprocess.run(
        cmd,
        cwd=str(repo_root),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    return result


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

        finalized = bm.finalize_spec(analysis["spec"], detect_gh_token(runtime_env), fetch_upstream=False)
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
                scripts=["scripts/full-migrate.sh", "scripts/local_build.sh"],
                risks=[build_result.stderr.strip() or "local_build 返回非零退出码"],
                next_step="停止，修复构建错误后重跑同一命令即可继续",
            )
            return 1

        step_report(
            8,
            "触发并监听构建",
            conclusion="本地构建命令执行成功。",
            outputs=[str(repo_root / "dist" / f"{finalized['slug']}.lpk")],
            scripts=["scripts/full-migrate.sh", "scripts/local_build.sh"],
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
                scripts=["scripts/full-migrate.sh", "scripts/local_build.sh"],
                risks=["dist 目录中未发现期望的 lpk 文件"],
                next_step="停止",
            )
            return 1

        step_report(
            9,
            "下载并核对 .lpk",
            conclusion="已拿到本地构建产物并完成基本核对。",
            outputs=[f"{lpk_path} (sha256={file_sha256(lpk_path)})"],
            scripts=["scripts/full-migrate.sh", "scripts/local_build.sh"],
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
            scripts=["scripts/full-migrate.sh", "scripts/local_build.sh", "lzc-cli app status"],
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
