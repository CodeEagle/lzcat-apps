#!/usr/bin/env python3

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib import error, request

DEFAULT_ICON_PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jXWQAAAAASUVORK5CYII="
)

SUPPORTED_BUILD_STRATEGIES = {
    "official_image",
    "precompiled_binary",
    "target_repo_dockerfile",
    "upstream_with_target_template",
    "upstream_dockerfile",
}

SUPPORTED_CHECK_STRATEGIES = {
    "github_release",
    "github_tag",
    "commit_sha",
}


def fatal(message: str) -> int:
    print(f"ERROR: {message}", file=sys.stderr)
    return 1


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def ensure_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if (
            isinstance(value, dict)
            and isinstance(merged.get(key), dict)
        ):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def normalize_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug


def normalize_semver(value: str) -> str:
    text = value.strip().lstrip("v")
    match = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", text)
    if not match:
        return "0.1.0"
    major, minor, patch = match.groups()
    return f"{major}.{minor}.{patch or '0'}"


def titleize_slug(slug: str) -> str:
    return " ".join(part.capitalize() for part in slug.split("-") if part)


def yaml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if not text:
        return '""'
    if "{{" in text or "}}" in text:
        return "'" + text.replace("'", "''") + "'"
    if text in {"null", "Null", "NULL", "~", "true", "false", "yes", "no", "on", "off"}:
        return json.dumps(text, ensure_ascii=False)
    if text.startswith(("-", "?", ":", "@", "`", "!", "*", "&", "%", "{", "}", "[", "]", ",")):
        return json.dumps(text, ensure_ascii=False)
    if text.strip() != text:
        return json.dumps(text, ensure_ascii=False)
    if ": " in text or "\t" in text or "#" in text:
        return json.dumps(text, ensure_ascii=False)
    return text


def render_yaml_value(value: Any, indent: int = 0) -> list[str]:
    if isinstance(value, dict):
        return render_yaml_mapping(value, indent)
    if isinstance(value, list):
        return render_yaml_sequence(value, indent)
    if isinstance(value, str) and "\n" in value:
        lines = [" " * indent + "|"]
        for line in value.splitlines():
            lines.append(" " * (indent + 2) + line)
        if value.endswith("\n"):
            lines.append(" " * (indent + 2))
        return lines
    return [" " * indent + yaml_scalar(value)]


def render_yaml_mapping(mapping: dict[str, Any], indent: int = 0) -> list[str]:
    lines: list[str] = []
    prefix = " " * indent
    for key, value in mapping.items():
        if isinstance(value, dict):
            if not value:
                lines.append(f"{prefix}{key}: {{}}")
                continue
            lines.append(f"{prefix}{key}:")
            lines.extend(render_yaml_mapping(value, indent + 2))
            continue
        if isinstance(value, list):
            if not value:
                lines.append(f"{prefix}{key}: []")
                continue
            lines.append(f"{prefix}{key}:")
            lines.extend(render_yaml_sequence(value, indent + 2))
            continue
        if isinstance(value, str) and "\n" in value:
            lines.append(f"{prefix}{key}: |")
            for line in value.splitlines():
                lines.append(" " * (indent + 2) + line)
            if value.endswith("\n"):
                lines.append(" " * (indent + 2))
            continue
        lines.append(f"{prefix}{key}: {yaml_scalar(value)}")
    return lines


def render_yaml_sequence(values: list[Any], indent: int = 0) -> list[str]:
    lines: list[str] = []
    prefix = " " * indent
    for item in values:
        if isinstance(item, dict):
            if not item:
                lines.append(f"{prefix}- {{}}")
                continue
            lines.append(f"{prefix}-")
            lines.extend(render_yaml_mapping(item, indent + 2))
            continue
        if isinstance(item, list):
            if not item:
                lines.append(f"{prefix}- []")
                continue
            lines.append(f"{prefix}-")
            lines.extend(render_yaml_sequence(item, indent + 2))
            continue
        if isinstance(item, str) and "\n" in item:
            lines.append(f"{prefix}- |")
            for line in item.splitlines():
                lines.append(" " * (indent + 2) + line)
            if item.endswith("\n"):
                lines.append(" " * (indent + 2))
            continue
        lines.append(f"{prefix}- {yaml_scalar(item)}")
    return lines


def prune_empty(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, inner in value.items():
            candidate = prune_empty(inner)
            if candidate in (None, "", [], {}) and candidate is not False and candidate != 0:
                continue
            cleaned[key] = candidate
        return cleaned
    if isinstance(value, list):
        cleaned_list = []
        for item in value:
            candidate = prune_empty(item)
            if candidate in (None, "", [], {}) and candidate is not False and candidate != 0:
                continue
            cleaned_list.append(candidate)
        return cleaned_list
    return value


def parse_env_arg(value: str) -> dict[str, Any]:
    if "=" in value:
        name, default = value.split("=", 1)
        return {"name": name.strip(), "value": default}
    return {"name": value.strip()}


def parse_data_path_arg(value: str) -> dict[str, Any]:
    host, container = value.split(":", 1)
    return {
        "host": host.strip(),
        "container": container.strip(),
    }


def env_items_to_manifest(entries: list[Any]) -> list[str]:
    rendered: list[str] = []
    for raw in entries:
        if isinstance(raw, str):
            item = parse_env_arg(raw)
        else:
            item = dict(raw)
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        if "value" in item and item["value"] is not None:
            rendered.append(f"{name}={item['value']}")
        else:
            rendered.append(name)
    return rendered


def data_paths_to_binds(entries: list[Any]) -> list[str]:
    binds: list[str] = []
    for raw in entries:
        if isinstance(raw, str):
            binds.append(raw)
            continue
        host = str(raw.get("host", "")).strip()
        container = str(raw.get("container", "")).strip()
        if host and container:
            binds.append(f"{host}:{container}")
    return binds


def repo_basename(upstream_repo: str) -> str:
    if "/" in upstream_repo:
        return upstream_repo.split("/", 1)[1]
    return upstream_repo


def github_api_json(path: str, token: str = "") -> Any:
    url = f"https://api.github.com/{path.lstrip('/')}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "lzcat-bootstrap-migration",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = request.Request(url, headers=headers)
    try:
        with request.urlopen(req, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except (error.URLError, error.HTTPError, json.JSONDecodeError):
        return None


def fetch_upstream_metadata(upstream_repo: str, check_strategy: str, token: str = "") -> dict[str, Any]:
    if not upstream_repo:
        return {}

    repo_meta = github_api_json(f"repos/{upstream_repo}", token)
    if not isinstance(repo_meta, dict):
        return {}

    source_version = ""
    build_version = ""
    default_branch = str(repo_meta.get("default_branch", "main")).strip() or "main"

    if check_strategy == "github_release":
        release = github_api_json(f"repos/{upstream_repo}/releases/latest", token)
        if isinstance(release, dict):
            source_version = str(release.get("tag_name", "")).strip()
            if source_version:
                build_version = normalize_semver(source_version)

    if not build_version and check_strategy in {"github_release", "github_tag"}:
        tags = github_api_json(f"repos/{upstream_repo}/tags?per_page=20", token)
        if isinstance(tags, list):
            for tag in tags:
                name = str(tag.get("name", "")).strip()
                if not name:
                    continue
                source_version = name
                build_version = normalize_semver(name)
                break

    if check_strategy == "commit_sha":
        commit = github_api_json(f"repos/{upstream_repo}/commits/{default_branch}", token)
        if isinstance(commit, dict):
            sha = str(commit.get("sha", "")).strip()
            source_version = sha[:7] if sha else ""

    license_info = repo_meta.get("license") if isinstance(repo_meta.get("license"), dict) else {}
    owner = repo_meta.get("owner") if isinstance(repo_meta.get("owner"), dict) else {}

    return {
        "project_name": str(repo_meta.get("name", "")).strip(),
        "description": str(repo_meta.get("description", "") or "").strip(),
        "homepage": str(repo_meta.get("homepage", "") or "").strip() or f"https://github.com/{upstream_repo}",
        "license": str(license_info.get("spdx_id", "") or license_info.get("name", "") or "").strip(),
        "author": str(owner.get("login", "") or "").strip(),
        "source_version": source_version,
        "version": build_version,
        "default_branch": default_branch,
    }


def default_placeholder_image(slug: str) -> str:
    return f"registry.lazycat.cloud/placeholder/{slug}:bootstrap"


def infer_port_from_backend(backend: str) -> int | None:
    match = re.search(r":(\d+)(?:/|$)", backend)
    if not match:
        return None
    return int(match.group(1))


def infer_primary_service(application: dict[str, Any]) -> str:
    for upstream in ensure_list(application.get("upstreams")):
        if not isinstance(upstream, dict):
            continue
        backend = str(upstream.get("backend", "")).strip()
        match = re.search(r"https?://([A-Za-z0-9_.-]+):\d+", backend)
        if match:
            return match.group(1)
    return ""


def infer_service_port(raw: dict[str, Any], application: dict[str, Any]) -> int:
    if raw.get("service_port"):
        return int(raw["service_port"])
    for upstream in ensure_list(application.get("upstreams")):
        if not isinstance(upstream, dict):
            continue
        port = infer_port_from_backend(str(upstream.get("backend", "")))
        if port:
            return port
    return 3000


def build_cli_spec(args: argparse.Namespace) -> dict[str, Any]:
    spec: dict[str, Any] = {}
    for key in (
        "slug",
        "project_name",
        "upstream_repo",
        "description",
        "description_zh",
        "homepage",
        "license",
        "author",
        "version",
        "package",
        "min_os_version",
        "check_strategy",
        "build_strategy",
        "official_image_registry",
        "precompiled_binary_url",
        "dockerfile_type",
        "dockerfile_path",
        "build_context",
        "docker_platform",
        "image_owner",
        "icon_path",
    ):
        value = getattr(args, key)
        if value not in (None, ""):
            spec[key] = value

    if args.service_name:
        spec["service_name"] = args.service_name
    if args.service_port:
        spec["service_port"] = args.service_port
    if args.backend:
        spec["backend"] = args.backend
    if args.command:
        spec["command"] = args.command
    if args.setup_script:
        spec["setup_script"] = args.setup_script
    if args.include_content:
        spec["include_content"] = True
    if args.ai_pod_service:
        spec["ai_pod_service"] = args.ai_pod_service
    if args.ai_pod_service_name:
        spec["ai_pod_service_name"] = args.ai_pod_service_name
    if args.ai_pod_service_port:
        spec["ai_pod_service_port"] = args.ai_pod_service_port
    if args.ai_pod_image:
        spec["ai_pod_image"] = args.ai_pod_image
    if args.aipod_shortcut_disable:
        spec["aipod"] = {"shortcut": {"disable": True}}
    if args.usage:
        spec["usage"] = args.usage
    if args.public_path:
        spec["public_path"] = args.public_path
    if args.image_target:
        spec["image_targets"] = args.image_target
    if args.overlay_path:
        spec["overlay_paths"] = args.overlay_path
    if args.depends_on:
        spec["depends_on"] = args.depends_on
    if args.env:
        spec["env_vars"] = [parse_env_arg(item) for item in args.env]
    if args.data_path:
        spec["data_paths"] = [parse_data_path_arg(item) for item in args.data_path]
    if args.startup_note:
        spec["startup_notes"] = args.startup_note
    if args.healthcheck_url:
        spec["healthcheck"] = {
            "test": [
                "CMD-SHELL",
                f"curl -f {args.healthcheck_url} >/dev/null || exit 1",
            ],
            "interval": "30s",
            "timeout": "10s",
            "retries": 5,
        }
    return spec


def coerce_services(raw: dict[str, Any], slug: str) -> dict[str, Any]:
    if raw.get("services"):
        services: dict[str, Any] = {}
        for name, payload in dict(raw["services"]).items():
            service_payload = dict(payload)
            service_payload.setdefault("image", default_placeholder_image(slug))
            if "environment" in service_payload:
                service_payload["environment"] = env_items_to_manifest(ensure_list(service_payload["environment"]))
            if "binds" in service_payload:
                service_payload["binds"] = data_paths_to_binds(ensure_list(service_payload["binds"]))
            if "depends_on" in service_payload:
                service_payload["depends_on"] = [str(item) for item in ensure_list(service_payload["depends_on"]) if str(item).strip()]
            if "command" in service_payload and "setup_script" in service_payload:
                raise ValueError(f"service {name} cannot define both command and setup_script")
            services[name] = prune_empty(service_payload)
        return services

    service_name = str(raw.get("service_name") or slug).strip()
    service_payload: dict[str, Any] = {
        "image": default_placeholder_image(slug),
        "environment": env_items_to_manifest(ensure_list(raw.get("env_vars"))),
        "binds": data_paths_to_binds(ensure_list(raw.get("data_paths"))),
        "depends_on": [str(item) for item in ensure_list(raw.get("depends_on")) if str(item).strip()],
    }
    if raw.get("setup_script") and raw.get("command"):
        raise ValueError(f"service {service_name} cannot define both command and setup_script")
    if raw.get("setup_script"):
        service_payload["setup_script"] = raw["setup_script"]
    if raw.get("command"):
        service_payload["command"] = raw["command"]
    if raw.get("healthcheck"):
        service_payload["healthcheck"] = raw["healthcheck"]
    return {service_name: prune_empty(service_payload)}


def coerce_application(raw: dict[str, Any], slug: str, primary_service: str, service_port: int) -> dict[str, Any]:
    application = dict(raw.get("application") or {})
    application.setdefault("subdomain", slug)
    application.setdefault("public_path", raw.get("public_path") or ["/"])
    if not application.get("upstreams"):
        backend = str(raw.get("backend") or f"http://{primary_service}:{service_port}/").strip()
        application["upstreams"] = [
            {
                "location": "/",
                "backend": backend,
            }
        ]
    if raw.get("routes") and not application.get("routes"):
        application["routes"] = ensure_list(raw["routes"])
    if raw.get("application_environment") and not application.get("environment"):
        application["environment"] = env_items_to_manifest(ensure_list(raw["application_environment"]))
    if raw.get("health_check") and not application.get("health_check"):
        application["health_check"] = raw["health_check"]
    return prune_empty(application)


def finalize_spec(raw: dict[str, Any], token: str, fetch_upstream: bool) -> dict[str, Any]:
    upstream_repo = str(raw.get("upstream_repo", "")).strip()
    slug_source = str(raw.get("slug") or repo_basename(upstream_repo) or raw.get("project_name") or "").strip()
    slug = normalize_slug(slug_source)
    if not slug:
        raise ValueError("slug is required")

    check_strategy = str(raw.get("check_strategy", "github_release")).strip() or "github_release"
    if check_strategy not in SUPPORTED_CHECK_STRATEGIES:
        raise ValueError(f"unsupported check_strategy: {check_strategy}")

    build_strategy = str(raw.get("build_strategy", "official_image")).strip() or "official_image"
    if build_strategy not in SUPPORTED_BUILD_STRATEGIES:
        raise ValueError(f"unsupported build_strategy: {build_strategy}")

    upstream_meta = fetch_upstream_metadata(upstream_repo, check_strategy, token) if fetch_upstream and upstream_repo else {}
    project_name = str(raw.get("project_name") or upstream_meta.get("project_name") or titleize_slug(slug)).strip()
    version = normalize_semver(str(raw.get("version") or upstream_meta.get("version") or "0.1.0"))
    description = str(raw.get("description") or upstream_meta.get("description") or f"{project_name} on LazyCat").strip()
    description_zh = str(raw.get("description_zh") or f"（迁移初稿）{project_name} 的懒猫微服打包版本").strip()
    homepage = str(raw.get("homepage") or upstream_meta.get("homepage") or (f"https://github.com/{upstream_repo}" if upstream_repo else "")).strip()
    license_name = str(raw.get("license") or upstream_meta.get("license") or "TODO").strip()
    author = str(raw.get("author") or upstream_meta.get("author") or "TODO").strip()
    package_name = str(raw.get("package") or f"fun.selfstudio.app.migration.{slug}").strip()
    min_os_version = str(raw.get("min_os_version") or "1.3.8").strip()

    services = coerce_services(raw, slug)
    primary_service = infer_primary_service(raw.get("application") or {})
    if not primary_service:
        primary_service = str(raw.get("service_name") or next(iter(services.keys()))).strip()
    service_port = infer_service_port(raw, raw.get("application") or {})
    application = coerce_application(raw, slug, primary_service, service_port)
    if not primary_service:
        primary_service = infer_primary_service(application) or next(iter(services.keys()))
    if not raw.get("service_port"):
        service_port = infer_service_port(raw, application)

    if build_strategy == "official_image" and not str(raw.get("official_image_registry", "")).strip():
        raise ValueError("official_image_registry is required for build_strategy=official_image")
    if build_strategy == "precompiled_binary" and not str(raw.get("precompiled_binary_url", "")).strip():
        raise ValueError("precompiled_binary_url is required for build_strategy=precompiled_binary")

    image_targets = [str(item).strip() for item in ensure_list(raw.get("image_targets")) if str(item).strip()]
    if not image_targets:
        image_targets = [primary_service]

    dependencies = ensure_list(raw.get("dependencies"))
    service_builds = ensure_list(raw.get("service_builds"))
    env_vars = ensure_list(raw.get("env_vars"))
    data_paths = ensure_list(raw.get("data_paths"))
    startup_notes = [str(item).strip() for item in ensure_list(raw.get("startup_notes")) if str(item).strip()]
    overlay_paths = [str(item).strip() for item in ensure_list(raw.get("overlay_paths")) if str(item).strip()]

    dockerfile_type = str(raw.get("dockerfile_type") or "custom").strip()
    dockerfile_path = str(raw.get("dockerfile_path") or "").strip()
    build_context = str(raw.get("build_context") or ".").strip()
    if not dockerfile_path:
        if build_strategy == "upstream_with_target_template":
            dockerfile_path = "Dockerfile.template"
        elif build_strategy == "target_repo_dockerfile":
            dockerfile_path = "Dockerfile"
        elif build_strategy == "precompiled_binary" and dockerfile_type == "custom":
            dockerfile_path = "Dockerfile.template"

    include_content = bool(raw.get("include_content"))
    if ensure_list(application.get("routes")):
        include_content = True

    ai_pod_service = str(raw.get("ai_pod_service") or "").strip()
    ai_pod_service_name = normalize_slug(str(raw.get("ai_pod_service_name") or slug).strip()) or slug
    ai_pod_service_port = int(raw.get("ai_pod_service_port") or raw.get("service_port") or 8000)
    ai_pod_image = str(raw.get("ai_pod_image") or default_placeholder_image(f"{slug}-ai")).strip()
    aipod = prune_empty(dict(raw.get("aipod") or {}))
    usage = str(raw.get("usage") or "").strip()

    return {
        "slug": slug,
        "project_name": project_name,
        "description": description,
        "description_zh": description_zh,
        "upstream_repo": upstream_repo,
        "homepage": homepage,
        "license": license_name,
        "author": author,
        "version": version,
        "package": package_name,
        "min_os_version": min_os_version,
        "check_strategy": check_strategy,
        "build_strategy": build_strategy,
        "official_image_registry": str(raw.get("official_image_registry", "")).strip(),
        "precompiled_binary_url": str(raw.get("precompiled_binary_url", "")).strip(),
        "dockerfile_type": dockerfile_type,
        "dockerfile_path": dockerfile_path,
        "build_context": build_context,
        "docker_platform": str(raw.get("docker_platform", "")).strip(),
        "image_owner": str(raw.get("image_owner", "")).strip(),
        "overlay_paths": overlay_paths,
        "image_targets": image_targets,
        "dependencies": dependencies,
        "service_builds": service_builds,
        "build_args": dict(raw.get("build_args") or {}),
        "service_cmd": [str(item) for item in ensure_list(raw.get("service_cmd")) if str(item).strip()],
        "service_port": service_port,
        "services": services,
        "application": application,
        "env_vars": env_vars,
        "data_paths": data_paths,
        "startup_notes": startup_notes,
        "include_content": include_content,
        "ai_pod_service": ai_pod_service,
        "ai_pod_service_name": ai_pod_service_name,
        "ai_pod_service_port": ai_pod_service_port,
        "ai_pod_image": ai_pod_image,
        "aipod": aipod,
        "usage": usage,
        "icon_path": str(raw.get("icon_path", "")).strip(),
        "source_version": str(upstream_meta.get("source_version", "")).strip(),
        "default_branch": str(upstream_meta.get("default_branch", "")).strip(),
    }


def build_registry_config(spec: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "enabled": True,
        "upstream_repo": spec["upstream_repo"],
        "check_strategy": spec["check_strategy"],
        "build_strategy": spec["build_strategy"],
        "publish_to_store": False,
        "official_image_registry": spec["official_image_registry"],
        "precompiled_binary_url": spec["precompiled_binary_url"],
        "dockerfile_type": spec["dockerfile_type"],
        "service_port": spec["service_port"],
        "service_cmd": spec["service_cmd"],
        "image_targets": spec["image_targets"],
        "dependencies": spec["dependencies"],
    }
    if spec["service_builds"]:
        payload["service_builds"] = spec["service_builds"]

    if spec["dockerfile_path"]:
        payload["dockerfile_path"] = spec["dockerfile_path"]
    if spec["build_strategy"] in {"target_repo_dockerfile", "upstream_with_target_template"}:
        payload["build_context"] = spec["build_context"]
    if spec["overlay_paths"]:
        payload["overlay_paths"] = spec["overlay_paths"]
    if spec["docker_platform"]:
        payload["docker_platform"] = spec["docker_platform"]
    if spec["image_owner"]:
        payload["image_owner"] = spec["image_owner"]
    if spec["build_args"]:
        payload["build_args"] = spec["build_args"]
    return payload


def build_manifest(spec: dict[str, Any]) -> dict[str, Any]:
    services: dict[str, Any] = {}
    for service_name, payload in spec["services"].items():
        ordered: dict[str, Any] = {"image": payload["image"]}
        if payload.get("depends_on"):
            ordered["depends_on"] = payload["depends_on"]
        if payload.get("setup_script"):
            ordered["setup_script"] = payload["setup_script"]
        if payload.get("command"):
            ordered["command"] = payload["command"]
        if payload.get("environment"):
            ordered["environment"] = payload["environment"]
        if payload.get("binds"):
            ordered["binds"] = payload["binds"]
        if payload.get("healthcheck"):
            ordered["healthcheck"] = payload["healthcheck"]
        services[service_name] = ordered

    manifest = {
        "lzc-sdk-version": "0.1",
        "package": spec["package"],
        "version": spec["version"],
        "min_os_version": spec["min_os_version"],
        "name": spec["project_name"],
        "description": spec["description"],
        "license": spec["license"],
        "homepage": spec["homepage"],
        "author": spec["author"],
        "usage": spec["usage"],
        "aipod": spec["aipod"],
        "application": spec["application"],
        "services": services,
        "locales": {
            "en": {
                "name": spec["project_name"],
                "description": spec["description"],
                "usage": spec["usage"],
            },
            "zh": {
                "name": spec["project_name"],
                "description": spec["description_zh"],
                "usage": spec["usage"],
            },
        },
    }
    return prune_empty(manifest)


def render_manifest(spec: dict[str, Any]) -> str:
    lines = render_yaml_mapping(build_manifest(spec))
    rendered = "\n".join(lines) + "\n"
    return rendered.replace('lzc-sdk-version: 0.1\n', "lzc-sdk-version: '0.1'\n", 1)


def render_build_yml(spec: dict[str, Any]) -> str:
    payload: dict[str, Any] = {
        "lzc-sdk-version": "0.1",
        "manifest": "./lzc-manifest.yml",
        "pkgout": "./",
        "icon": "./icon.png",
    }
    if spec["include_content"]:
        payload["contentdir"] = "./content"
    if spec["ai_pod_service"]:
        payload["ai-pod-service"] = spec["ai_pod_service"]
    rendered = "\n".join(render_yaml_mapping(payload)) + "\n"
    return rendered.replace('lzc-sdk-version: 0.1\n', "lzc-sdk-version: '0.1'\n", 1)


def markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def render_readme(spec: dict[str, Any]) -> str:
    env_rows: list[list[str]] = []
    for entry in spec["env_vars"]:
        item = entry if isinstance(entry, dict) else parse_env_arg(str(entry))
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        required = "Yes" if bool(item.get("required")) else "No"
        default = str(item.get("value", "") or "-")
        description = str(item.get("description", "") or "TODO").strip()
        env_rows.append([name, required, default, description])

    data_rows: list[list[str]] = []
    for entry in spec["data_paths"]:
        if isinstance(entry, str):
            host, container = entry.split(":", 1)
            description = "TODO"
        else:
            host = str(entry.get("host", "")).strip()
            container = str(entry.get("container", "")).strip()
            description = str(entry.get("description", "") or "TODO").strip()
        if host and container:
            data_rows.append([host, container, description])

    service_lines = []
    for name, payload in spec["services"].items():
        service_lines.append(f"- `{name}` -> `{payload['image']}`")

    next_steps = [
        "1. 补完 `UPSTREAM_DEPLOYMENT_CHECKLIST.md`，把真实入口、环境变量、写路径和初始化动作全部核实清楚。",
        "2. 按真实部署拓扑修正 `lzc-manifest.yml`，不要直接沿用占位镜像、端口或命令。",
        "3. 如果是源码构建，补齐 `Dockerfile` / `Dockerfile.template`、`content/`、`overlay_paths` 等资产。",
        f"4. 初稿补全后执行 `./scripts/local_build.sh {spec['slug']} --check-only`，再进入实际构建与验收。",
    ]
    if spec["ai_pod_service"]:
        next_steps.insert(3, "4. 补齐 `ai-pod-service/docker-compose.yml` 中的真实 GPU 服务镜像、启动命令、卷挂载与 `-ai` 路由标签。")
        next_steps[-1] = f"5. 初稿补全后执行 `./scripts/local_build.sh {spec['slug']} --check-only`，再进入实际构建与验收。"

    parts = [
        f"# {spec['project_name']}",
        "",
        f"本目录由 `scripts/bootstrap_migration.py` 生成，用于把上游 `{spec['upstream_repo'] or 'TODO'}` 初始化为懒猫微服迁移项目。",
        "",
        "## 上游项目",
        f"- Upstream Repo: {spec['upstream_repo'] or 'TODO'}",
        f"- Homepage: {spec['homepage'] or 'TODO'}",
        f"- License: {spec['license']}",
        f"- Author: {spec['author']}",
        f"- Version Strategy: `{spec['check_strategy']}` -> 当前初稿版本 `{spec['version']}`",
        "",
        "## 当前迁移骨架",
        f"- Build Strategy: `{spec['build_strategy']}`",
        f"- Primary Subdomain: `{spec['application']['subdomain']}`",
        f"- Image Targets: `{', '.join(spec['image_targets'])}`",
        f"- Service Port: `{spec['service_port']}`",
        "",
        "### Services",
        *service_lines,
        "",
        "## AIPod",
    ]

    if spec["ai_pod_service"]:
        parts.extend(
            [
                "",
                f"- AI Pod Service Dir: `{spec['ai_pod_service']}`",
                f"- AI Service Name: `{spec['ai_pod_service_name']}`",
                f"- AI Service Port: `{spec['ai_pod_service_port']}`",
                f"- AI Service Host: `https://{spec['ai_pod_service_name']}-ai.{{{{ .S.BoxDomain }}}}`",
                "- 当前骨架已包含算力舱目录，但仍需把真实 GPU 服务镜像、命令、路由与前端代理补齐。",
                "",
            ]
        )
    else:
        parts.extend(["", "当前未启用 AIPod / AI 服务。", ""])

    parts.extend([
        "## 环境变量",
    ])

    if env_rows:
        parts.extend(["", markdown_table(["变量名", "必填", "默认值", "说明"], env_rows)])
    else:
        parts.extend(["", "当前未预填环境变量，待补充。"])

    parts.extend(["", "## 数据目录"])
    if data_rows:
        parts.extend(["", markdown_table(["宿主路径", "容器路径", "说明"], data_rows)])
    else:
        parts.extend(["", "当前未声明持久化目录，待从上游部署清单补充。"])

    parts.extend(["", "## 首次启动/验收提醒"])
    if spec["startup_notes"]:
        parts.extend(["", *[f"- {note}" for note in spec["startup_notes"]]])
    else:
        parts.extend(["", "- 首次启动、初始化命令和健康检查还未确认，待补充。"])

    parts.extend(["", "## 下一步", "", *next_steps, ""])
    return "\n".join(parts)


def render_checklist(spec: dict[str, Any]) -> str:
    env_lines = []
    for entry in spec["env_vars"]:
        item = entry if isinstance(entry, dict) else parse_env_arg(str(entry))
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        env_lines.append(
            f"- `{name}`: {str(item.get('description', '') or 'TODO').strip()} "
            f"(required={bool(item.get('required', False))})"
        )
    if not env_lines:
        env_lines = ["- 待补充"]

    path_lines = []
    for entry in spec["data_paths"]:
        if isinstance(entry, str):
            host, container = entry.split(":", 1)
            description = "TODO"
        else:
            host = str(entry.get("host", "")).strip()
            container = str(entry.get("container", "")).strip()
            description = str(entry.get("description", "") or "TODO").strip()
        if host and container:
            path_lines.append(f"- `{container}` <= `{host}` ({description})")
    if not path_lines:
        path_lines = ["- 待补充"]

    startup_lines = [f"- {note}" for note in spec["startup_notes"]] or ["- 待补充"]

    parts = [
        f"# {spec['project_name']} Upstream Deployment Checklist",
        "",
        "## 已确认字段",
        f"- PROJECT_NAME: {spec['project_name']}",
        f"- PROJECT_SLUG: {spec['slug']}",
        f"- UPSTREAM_REPO: {spec['upstream_repo'] or 'TODO'}",
        f"- UPSTREAM_URL: {f'https://github.com/{spec['upstream_repo']}' if spec['upstream_repo'] else 'TODO'}",
        f"- HOMEPAGE: {spec['homepage'] or 'TODO'}",
        f"- LICENSE: {spec['license']}",
        f"- AUTHOR: {spec['author']}",
        f"- VERSION: {spec['version']}",
        f"- IMAGE: {spec['official_image_registry'] or 'TODO'}",
        f"- PORT: {spec['service_port']}",
        f"- AI_POD_SERVICE: {spec['ai_pod_service'] or '无'}",
        f"- AI_POD_SERVICE_NAME: {spec['ai_pod_service_name'] if spec['ai_pod_service'] else '无'}",
        f"- AI_POD_SERVICE_PORT: {spec['ai_pod_service_port'] if spec['ai_pod_service'] else '无'}",
        f"- CHECK_STRATEGY: {spec['check_strategy']}",
        f"- BUILD_STRATEGY: {spec['build_strategy']}",
        "",
        "## 预填环境变量",
        *env_lines,
        "",
        "## 预填数据路径",
        *path_lines,
        "",
        "## 预填启动说明",
        *startup_lines,
        "",
        "## 必扫清单",
        "- [ ] Dockerfile / Containerfile / compose / helm / entrypoint / startup script 的真实启动入口",
        "- [ ] README / 部署文档 / `.env.example` / sample config 中声明的环境变量",
        "- [ ] 数据目录、配置目录、缓存目录、上传目录、日志目录、临时目录的真实读写路径",
        "- [ ] 若启用 AIPod，确认 `ai-pod-service/docker-compose.yml` 中的真实镜像、服务端口、`-ai` Host 规则与 `traefik-shared-network` 配置",
        "- [ ] 首次启动初始化命令、迁移命令、建库建表命令、管理员初始化命令",
        "- [ ] 数据库、Redis、对象存储、auth / OAuth / JWT / callback / secret 等外部依赖配置",
        "- [ ] 每个真实目录是否需要预创建、由谁创建、以什么 owner/group/mode 创建",
        "",
        "## 当前服务拓扑初稿",
    ]

    for name, payload in spec["services"].items():
        parts.append(f"- `{name}`")
        parts.append(f"  image: `{payload.get('image', '')}`")
        if payload.get("depends_on"):
            parts.append(f"  depends_on: `{', '.join(payload['depends_on'])}`")
        if payload.get("binds"):
            parts.append(f"  binds: `{', '.join(payload['binds'])}`")
        if payload.get("environment"):
            parts.append(f"  environment: `{', '.join(payload['environment'])}`")

    parts.extend(
        [
            "",
            "## 退出条件",
            "- [ ] 入口、端口、环境变量、真实写路径、初始化命令、数据库/auth 配置全部确认完毕",
            "- [ ] `lzc-manifest.yml` 中的镜像地址已替换为真实的 `registry.lazycat.cloud/...`",
            "- [ ] 构建策略相关文件（Dockerfile / template / content / overlay）已补齐",
            "- [ ] 可以进入预检、构建、下载 `.lpk`、安装验收阶段",
            "",
        ]
    )
    return "\n".join(parts)


def render_placeholder_dockerfile(spec: dict[str, Any], template_mode: bool) -> str:
    expose_value = "{{SERVICE_PORT}}" if template_mode else str(spec["service_port"])
    return "\n".join(
        [
            "FROM alpine:3.20",
            "",
            "# TODO: replace this placeholder with the real build steps for the upstream project.",
            "RUN apk add --no-cache bash curl",
            "WORKDIR /app",
            "COPY . /app",
            f"EXPOSE {expose_value}",
            'CMD ["sh", "-c", "echo \\"Replace this placeholder Dockerfile before running a real build.\\" >&2; sleep infinity"]',
            "",
        ]
    )


def write_placeholder_icon(path: Path) -> None:
    path.write_bytes(base64.b64decode(DEFAULT_ICON_PNG))


def update_index(index_path: Path, config_filename: str) -> None:
    if index_path.exists():
        index = load_json(index_path)
    else:
        index = {"repos": []}
    repos = list(index.get("repos", []))
    if config_filename not in repos:
        repos.append(config_filename)
    index["repos"] = repos
    dump_json(index_path, index)


def sync_trigger_build_options(repo_root: Path) -> Path | None:
    script_path = repo_root / "scripts" / "sync_trigger_build_options.py"
    workflow_path = repo_root / ".github" / "workflows" / "trigger-build.yml"
    if not script_path.exists() or not workflow_path.exists():
        return None
    subprocess.run(
        ["python3", str(script_path)],
        cwd=repo_root,
        check=True,
        text=True,
        capture_output=True,
    )
    return workflow_path


def create_content_dir(app_dir: Path) -> None:
    content_dir = app_dir / "content"
    content_dir.mkdir(parents=True, exist_ok=True)
    readme_path = content_dir / "README.md"
    if not readme_path.exists():
        readme_path.write_text(
            "# content\n\nStatic assets and bootstrap files for LazyCat packaging.\n",
            encoding="utf-8",
        )


def create_aipod_content(app_dir: Path, spec: dict[str, Any]) -> list[Path]:
    written: list[Path] = []
    ui_dir = app_dir / "content" / "ui"
    ui_dir.mkdir(parents=True, exist_ok=True)
    index_path = ui_dir / "index.html"
    index_html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{spec["project_name"]}</title>
  <style>
    body {{ font-family: sans-serif; background: #0f172a; color: #e2e8f0; margin: 0; }}
    main {{ max-width: 720px; margin: 0 auto; padding: 48px 20px; }}
    code {{ background: rgba(255,255,255,0.08); padding: 2px 6px; border-radius: 6px; }}
  </style>
</head>
<body>
  <main>
    <h1>{spec["project_name"]}</h1>
    <p>此页为 AIPod 骨架占位页。当前应用已启用算力舱服务目录，但仍需补齐真实 GPU 服务镜像、命令与前端转发。</p>
    <p>预期 AI 服务入口：<code>https://{spec["ai_pod_service_name"]}-ai.{{{{ .S.BoxDomain }}}}</code></p>
    <p>请继续检查 <code>ai-pod-service/docker-compose.yml</code> 与 <code>lzc-manifest.yml</code>，再进入构建与验收。</p>
  </main>
</body>
</html>
"""
    if not index_path.exists():
        index_path.write_text(index_html, encoding="utf-8")
        written.append(index_path)
    return written


def render_aipod_compose(spec: dict[str, Any]) -> str:
    service_name = spec["ai_pod_service_name"]
    host_name = f"{service_name}-ai"
    port = spec["ai_pod_service_port"]
    image = spec["ai_pod_image"]
    return "\n".join(
        [
            "services:",
            f"  {service_name}:",
            f"    image: {image}",
            "    restart: unless-stopped",
            "    environment:",
            f"      SERVICE_PORT: \"{port}\"",
            "    volumes:",
            "      - ${LZC_AGENT_DATA_DIR}/data:/data",
            "      - ${LZC_AGENT_CACHE_DIR}/cache:/cache",
            "    labels:",
            "      - \"traefik.enable=true\"",
            f"      - \"traefik.http.routers.${{LZC_SERVICE_ID}}-{service_name}.rule=Host(`{host_name}`)\"",
            f"      - \"traefik.http.services.${{LZC_SERVICE_ID}}-{service_name}.loadbalancer.server.port={port}\"",
            "    networks:",
            "      - traefik-shared-network",
            "",
            "networks:",
            "  traefik-shared-network:",
            "    external: true",
            "    name: traefik-shared-network",
            "",
        ]
    )


def create_ai_pod_service_dir(app_dir: Path, spec: dict[str, Any], force: bool) -> list[Path]:
    written: list[Path] = []
    service_dir = app_dir / spec["ai_pod_service"]
    service_dir.mkdir(parents=True, exist_ok=True)
    readme_path = service_dir / "README.md"
    compose_path = service_dir / "docker-compose.yml"
    readme_content = (
        f"# ai-pod-service\n\n"
        f"算力舱 GPU 服务骨架目录，当前服务名为 `{spec['ai_pod_service_name']}`，"
        f"预期对外主机名为 `{spec['ai_pod_service_name']}-ai`。\n"
        "请把占位镜像替换为真实 GPU 服务镜像，并补齐命令、卷、健康检查与依赖。\n"
    )
    if force or not readme_path.exists():
        readme_path.write_text(readme_content, encoding="utf-8")
        written.append(readme_path)
    if force or not compose_path.exists():
        compose_path.write_text(render_aipod_compose(spec), encoding="utf-8")
        written.append(compose_path)
    return written


def write_files(repo_root: Path, spec: dict[str, Any], force: bool) -> list[Path]:
    app_dir = repo_root / "apps" / spec["slug"]
    registry_dir = repo_root / "registry" / "repos"
    registry_dir.mkdir(parents=True, exist_ok=True)
    app_dir.mkdir(parents=True, exist_ok=True)

    config_path = registry_dir / f"{spec['slug']}.json"
    managed_paths = [
        app_dir / "README.md",
        app_dir / "lzc-manifest.yml",
        app_dir / "lzc-build.yml",
        app_dir / "UPSTREAM_DEPLOYMENT_CHECKLIST.md",
        app_dir / "icon.png",
        config_path,
    ]

    if not force:
        for path in managed_paths:
            if path.exists():
                raise FileExistsError(f"{path} already exists; rerun with --force to overwrite managed files")

    written: list[Path] = []

    (repo_root / "apps").mkdir(parents=True, exist_ok=True)
    manifest_path = app_dir / "lzc-manifest.yml"
    manifest_path.write_text(render_manifest(spec), encoding="utf-8")
    written.append(manifest_path)

    build_path = app_dir / "lzc-build.yml"
    build_path.write_text(render_build_yml(spec), encoding="utf-8")
    written.append(build_path)

    readme_path = app_dir / "README.md"
    readme_path.write_text(render_readme(spec), encoding="utf-8")
    written.append(readme_path)

    checklist_path = app_dir / "UPSTREAM_DEPLOYMENT_CHECKLIST.md"
    checklist_path.write_text(render_checklist(spec), encoding="utf-8")
    written.append(checklist_path)

    icon_path = app_dir / "icon.png"
    icon_source = spec["icon_path"]
    if icon_source:
        icon_path.write_bytes(Path(icon_source).read_bytes())
    else:
        write_placeholder_icon(icon_path)
    written.append(icon_path)

    config_path.write_text(
        json.dumps(build_registry_config(spec), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    written.append(config_path)

    if spec["include_content"]:
        create_content_dir(app_dir)
        written.append(app_dir / "content" / "README.md")
        if spec["ai_pod_service"]:
            written.extend(create_aipod_content(app_dir, spec))

    if spec["ai_pod_service"]:
        written.extend(create_ai_pod_service_dir(app_dir, spec, force))

    if spec["dockerfile_path"]:
        dockerfile_path = app_dir / spec["dockerfile_path"]
        dockerfile_path.parent.mkdir(parents=True, exist_ok=True)
        template_mode = spec["dockerfile_path"].endswith(".template")
        if force or not dockerfile_path.exists():
            dockerfile_path.write_text(render_placeholder_dockerfile(spec, template_mode), encoding="utf-8")
            written.append(dockerfile_path)

    for overlay_path in spec["overlay_paths"]:
        overlay_dir = app_dir / overlay_path
        overlay_dir.mkdir(parents=True, exist_ok=True)
        note_path = overlay_dir / "README.md"
        if force or not note_path.exists():
            note_path.write_text(
                f"# {overlay_path}\n\nOverlay assets for `{spec['slug']}`.\n",
                encoding="utf-8",
            )
            written.append(note_path)

    update_index(registry_dir / "index.json", f"{spec['slug']}.json")
    written.append(registry_dir / "index.json")
    workflow_path = sync_trigger_build_options(repo_root)
    if workflow_path is not None:
        written.append(workflow_path)

    return written


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bootstrap a new LazyCat migration app inside lzcat-apps.",
    )
    parser.add_argument("--repo-root", default="", help="Path to the lzcat-apps repository root")
    parser.add_argument("--spec", default="", help="Path to a JSON spec file for advanced/multi-service scaffolds")
    parser.add_argument("--slug", default="", help="App slug, e.g. paperclip")
    parser.add_argument("--project-name", default="", help="Display name")
    parser.add_argument("--upstream-repo", default="", help="GitHub repo in owner/name form")
    parser.add_argument("--description", default="", help="English description for manifest/README")
    parser.add_argument("--description-zh", default="", help="Chinese description for locales.zh")
    parser.add_argument("--homepage", default="", help="Homepage URL")
    parser.add_argument("--license", default="", help="License name")
    parser.add_argument("--author", default="", help="Author or organization")
    parser.add_argument("--version", default="", help="Initial semver")
    parser.add_argument("--package", default="", help="LazyCat package id")
    parser.add_argument("--min-os-version", default="", help="Minimum LazyCat OS version")
    parser.add_argument("--check-strategy", default="github_release", choices=sorted(SUPPORTED_CHECK_STRATEGIES))
    parser.add_argument("--build-strategy", default="", choices=sorted(SUPPORTED_BUILD_STRATEGIES))
    parser.add_argument("--official-image-registry", default="", help="Registry/image for official_image strategy")
    parser.add_argument("--precompiled-binary-url", default="", help="Binary URL template for precompiled_binary")
    parser.add_argument("--dockerfile-type", default="", help="Dockerfile mode, typically custom or simple")
    parser.add_argument("--dockerfile-path", default="", help="Dockerfile or template path under apps/<slug>/")
    parser.add_argument("--build-context", default="", help="Docker build context")
    parser.add_argument("--docker-platform", default="", help="Optional docker platform override")
    parser.add_argument("--image-owner", default="", help="Optional GHCR owner override for source-built images")
    parser.add_argument("--service-name", default="", help="Primary service name for simple single-service scaffolds")
    parser.add_argument("--service-port", type=int, default=0, help="Primary container port")
    parser.add_argument("--backend", default="", help="Primary backend URL, e.g. http://web:3000/")
    parser.add_argument("--public-path", action="append", default=[], help="Repeatable public path, defaults to /")
    parser.add_argument("--image-target", action="append", default=[], help="Repeatable service names to update")
    parser.add_argument("--overlay-path", action="append", default=[], help="Repeatable overlay path under app dir")
    parser.add_argument("--depends-on", action="append", default=[], help="Repeatable depends_on entry for single-service scaffolds")
    parser.add_argument("--env", action="append", default=[], help="Repeatable env var, e.g. OPENAI_API_KEY or PORT=3000")
    parser.add_argument("--data-path", action="append", default=[], help="Repeatable bind mount as /host:/container")
    parser.add_argument("--startup-note", action="append", default=[], help="Repeatable startup/acceptance note")
    parser.add_argument("--command", default="", help="Single-service command")
    parser.add_argument("--setup-script", default="", help="Single-service setup_script")
    parser.add_argument("--healthcheck-url", default="", help="Simple HTTP healthcheck URL")
    parser.add_argument("--icon-path", default="", help="Optional icon.png source path")
    parser.add_argument("--include-content", action="store_true", help="Create content/ and set contentdir in lzc-build.yml")
    parser.add_argument("--ai-pod-service", default="", help="AI Pod service directory, e.g. ./ai-pod-service")
    parser.add_argument("--ai-pod-service-name", default="", help="AI service name used for <name>-ai routing")
    parser.add_argument("--ai-pod-service-port", type=int, default=0, help="Primary AI Pod container port")
    parser.add_argument("--ai-pod-image", default="", help="AI Pod service image")
    parser.add_argument("--aipod-shortcut-disable", action="store_true", help="Disable AI browser shortcut")
    parser.add_argument("--usage", default="", help="Optional usage/help text for manifest")
    parser.add_argument("--no-fetch-upstream", action="store_true", help="Do not call GitHub API for missing metadata")
    parser.add_argument("--force", action="store_true", help="Overwrite managed files if they already exist")
    parser.add_argument("--dry-run", action="store_true", help="Resolve inputs and print the scaffold plan without writing files")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve() if args.repo_root else Path(__file__).resolve().parents[1]

    raw_spec: dict[str, Any] = {}
    if args.spec:
        raw_spec = load_json(Path(args.spec).resolve())
    raw_spec = deep_merge(raw_spec, build_cli_spec(args))

    token = os.environ.get("GH_PAT") or os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""

    try:
        spec = finalize_spec(raw_spec, token, fetch_upstream=not args.no_fetch_upstream)
    except (ValueError, KeyError) as exc:
        return fatal(str(exc))

    if args.dry_run:
        print(json.dumps(spec, ensure_ascii=False, indent=2))
        return 0

    try:
        written = write_files(repo_root, spec, args.force)
    except FileExistsError as exc:
        return fatal(str(exc))
    except OSError as exc:
        return fatal(str(exc))

    print(f"Scaffolded app: {spec['slug']}")
    for path in written:
        try:
            rel = path.relative_to(repo_root)
        except ValueError:
            rel = path
        print(f"  - {rel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
