#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml


STATUS_FILE = "local-publication-status.json"


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def clean_string(value: Any) -> str:
    return " ".join(str(value or "").split())


def normalize_repo(value: str) -> str:
    return clean_string(value).strip("/").lower()


def load_developer_apps(repo_root: Path) -> dict[str, str]:
    payload = read_json(repo_root / "registry" / "status" / "developer-apps.json")
    apps = payload.get("apps")
    if not isinstance(apps, dict):
        return {}
    return {clean_string(package): clean_string(label) for package, label in apps.items() if clean_string(package)}


def load_manifest(manifest_path: Path) -> dict[str, Any]:
    if not manifest_path.exists():
        return {}
    payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def load_registry_entry(repo_root: Path, slug: str) -> dict[str, Any]:
    return read_json(repo_root / "registry" / "repos" / f"{slug}.json")


def classify_publication_status(package: str, migration_status: str, developer_apps: dict[str, str]) -> str:
    if package and package in developer_apps:
        return "published"
    if migration_status:
        return migration_status
    return "local_only"


def build_app_record(repo_root: Path, slug: str, developer_apps: dict[str, str]) -> dict[str, Any] | None:
    manifest = load_manifest(repo_root / "apps" / slug / "lzc-manifest.yml")
    package = clean_string(manifest.get("package"))
    if not package:
        return None

    registry_entry = load_registry_entry(repo_root, slug)
    migration_status = clean_string(registry_entry.get("migration_status"))
    upstream_repo = clean_string(registry_entry.get("upstream_repo"))
    store_label = developer_apps.get(package, "")
    publication_status = classify_publication_status(package, migration_status, developer_apps)

    return {
        "slug": slug,
        "package": package,
        "name": clean_string(manifest.get("name")) or slug,
        "homepage": clean_string(manifest.get("homepage")),
        "upstream_repo": upstream_repo,
        "migration_status": migration_status or "unknown",
        "publication_status": publication_status,
        "store_label": store_label,
    }


def build_status_snapshot(repo_root: Path, *, generated_at: str | None = None) -> dict[str, Any]:
    developer_apps = load_developer_apps(repo_root)
    apps: dict[str, dict[str, Any]] = {}
    apps_root = repo_root / "apps"
    if apps_root.exists():
        for manifest_path in sorted(apps_root.glob("*/lzc-manifest.yml")):
            slug = manifest_path.parent.name
            record = build_app_record(repo_root, slug, developer_apps)
            if record:
                apps[slug] = record

    counts: dict[str, int] = {}
    for record in apps.values():
        status = record["publication_status"]
        counts[status] = counts.get(status, 0) + 1

    return {
        "schema_version": 1,
        "source": "local_apps_plus_developer_page",
        "meta": {
            "generated_at": generated_at or utc_now_iso(),
            "local_app_count": len(apps),
            "published_count": counts.get("published", 0),
            "counts_by_publication_status": counts,
        },
        "apps": apps,
    }


def build_publication_index(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    apps = snapshot.get("apps")
    if not isinstance(apps, dict):
        apps = {}

    by_slug: dict[str, dict[str, Any]] = {}
    by_package: dict[str, dict[str, Any]] = {}
    by_upstream_repo: dict[str, dict[str, Any]] = {}
    for slug, record in apps.items():
        if not isinstance(record, dict):
            continue
        normalized_slug = clean_string(record.get("slug")) or clean_string(slug)
        normalized_package = clean_string(record.get("package"))
        normalized_upstream = normalize_repo(clean_string(record.get("upstream_repo")))
        if normalized_slug:
            by_slug[normalized_slug] = record
        if normalized_package:
            by_package[normalized_package] = record
        if normalized_upstream:
            by_upstream_repo[normalized_upstream] = record

    return {
        "by_slug": by_slug,
        "by_package": by_package,
        "by_upstream_repo": by_upstream_repo,
    }


def load_status_snapshot(repo_root: Path) -> dict[str, Any]:
    status_path = repo_root / "registry" / "status" / STATUS_FILE
    snapshot = read_json(status_path)
    if snapshot:
        return snapshot
    return build_status_snapshot(repo_root)


def load_publication_index(repo_root: Path) -> dict[str, dict[str, Any]]:
    return build_publication_index(load_status_snapshot(repo_root))


def write_status_snapshot(repo_root: Path, *, generated_at: str | None = None) -> Path:
    output_dir = repo_root / "registry" / "status"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / STATUS_FILE
    content = json.dumps(
        build_status_snapshot(repo_root, generated_at=generated_at),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    output_path.write_text(
        content + "\n",
        encoding="utf-8",
    )
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build local LazyCat publication status from developer app status.")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_path = write_status_snapshot(Path(args.repo_root).resolve())
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
