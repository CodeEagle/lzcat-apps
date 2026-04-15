#!/usr/bin/env python3
"""
generate_profiles.py — Generate .app-profile.json from actual configs for migrated apps.

For apps where full_migrate.py auto-analysis diverges from actual hand-tuned configs,
this captures the human decisions as profiles so future runs reproduce them.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

REPO_ROOT = Path(__file__).resolve().parents[2]

# Fields that .app-profile.json fixes can override
PROFILE_FIELDS = {
    "project_name", "description", "license", "homepage", "author",
    "build_strategy", "official_image_registry", "docker_platform",
    "service_port", "image_targets", "dependencies", "service_builds",
    "application", "services", "env_vars", "data_paths",
    "include_content", "startup_notes", "usage",
}


def load_registry(slug: str) -> dict | None:
    path = REPO_ROOT / "registry" / "repos" / f"{slug}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def load_manifest(slug: str) -> dict | None:
    path = REPO_ROOT / "apps" / slug / "lzc-manifest.yml"
    if not path.exists():
        return None
    if yaml is None:
        return None
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_existing_profile(slug: str) -> dict | None:
    path = REPO_ROOT / "apps" / slug / ".app-profile.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def extract_profile_fixes(slug: str) -> dict:
    """Extract profile fixes from actual registry + manifest configs."""
    fixes: dict = {}
    reg = load_registry(slug)
    manifest = load_manifest(slug)

    if reg:
        # Registry fields that influence generation — capture all meaningful ones
        for key in ("build_strategy", "check_strategy", "official_image_registry",
                     "docker_platform", "dockerfile_path", "dockerfile_type",
                     "build_context", "overlay_paths", "image_name",
                     "service_port", "service_cmd", "image_targets",
                     "dependencies", "service_builds", "build_args",
                     "precompiled_binary_url", "upstream_submodules",
                     "deploy_param_sync", "image_owner",
                     "official_image_fallback_tag", "repo"):
            if key in reg:
                fixes[key] = reg[key]
        # Explicitly set absent fields to empty to suppress auto-generation
        for key in ("service_builds", "build_args", "docker_platform"):
            if key not in reg:
                if key == "docker_platform":
                    fixes[key] = ""
                elif key == "build_args":
                    fixes[key] = {}
                else:
                    fixes[key] = []

    if manifest:
        # Manifest fields
        if manifest.get("name"):
            fixes["project_name"] = manifest["name"]
        if manifest.get("description"):
            fixes["description"] = manifest["description"]
        if manifest.get("license"):
            fixes["license"] = manifest["license"]
        if manifest.get("homepage"):
            fixes["homepage"] = manifest["homepage"]
        if manifest.get("author"):
            fixes["author"] = manifest["author"]
        # Preserve custom package name if it differs from the default pattern
        if manifest.get("package"):
            pkg = manifest["package"]
            default_pkg = f"fun.selfstudio.app.migration.{slug}"
            if pkg != default_pkg:
                fixes["package"] = pkg
        # Extract Chinese description from locales
        locales = manifest.get("locales", {})
        zh_locale = locales.get("zh", {})
        if zh_locale.get("description"):
            fixes["description_zh"] = zh_locale["description"]
        if manifest.get("application"):
            fixes["application"] = manifest["application"]
        if manifest.get("services"):
            fixes["services"] = manifest["services"]

    # Check if app has content directory (implies include_content)
    content_dir = REPO_ROOT / "apps" / slug / "content"
    if content_dir.is_dir() and any(content_dir.rglob("*")):
        fixes["include_content"] = True
    else:
        fixes["include_content"] = False

    return fixes


def generate_profile(slug: str) -> dict:
    """Generate a full .app-profile.json for an app."""
    reg = load_registry(slug)
    upstream = reg.get("upstream_repo", "") if reg else ""

    fixes = extract_profile_fixes(slug)

    return {
        "managed_by": "optimize_migration",
        "generated_from_upstream": upstream,
        "pinned": True,
        "fixes": fixes,
    }


def main() -> int:
    slugs = sys.argv[1:] if len(sys.argv) > 1 else []

    if not slugs:
        # Auto-discover migrated apps without profiles
        registry_dir = REPO_ROOT / "registry" / "repos"
        for f in sorted(registry_dir.glob("*.json")):
            if f.name == "index.json":
                continue
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if data.get("migration_status") == "migrated":
                    slug = f.stem
                    profile_path = REPO_ROOT / "apps" / slug / ".app-profile.json"
                    if not profile_path.exists():
                        slugs.append(slug)
            except Exception:
                continue

    if not slugs:
        print("No apps need profiles.")
        return 0

    print(f"Generating profiles for {len(slugs)} apps: {slugs}")

    for slug in slugs:
        profile = generate_profile(slug)
        if not profile["fixes"]:
            print(f"  {slug}: no fixes extracted, skipping")
            continue

        out_path = REPO_ROOT / "apps" / slug / ".app-profile.json"
        out_path.write_text(
            json.dumps(profile, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"  {slug}: wrote {out_path} ({len(profile['fixes'])} fixes)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
