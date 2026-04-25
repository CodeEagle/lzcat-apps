#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml


def normalize_box_domain(box_domain: str) -> str:
    domain = box_domain.strip().removeprefix("https://").removeprefix("http://").strip("/")
    if not domain:
        raise ValueError("box_domain is required")
    return domain


def load_manifest(repo_root: Path, slug: str) -> dict[str, Any]:
    manifest_path = repo_root / "apps" / slug / "lzc-manifest.yml"
    payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid manifest: {manifest_path}")
    return payload


def manifest_subdomain(manifest: dict[str, Any], fallback: str) -> str:
    application = manifest.get("application")
    if isinstance(application, dict):
        subdomain = application.get("subdomain")
        if subdomain:
            return str(subdomain).strip()
    return fallback


def build_acceptance_plan(repo_root: Path, slug: str, *, box_domain: str) -> dict[str, Any]:
    manifest = load_manifest(repo_root, slug)
    domain = normalize_box_domain(box_domain)
    package = str(manifest.get("package", "")).strip()
    subdomain = manifest_subdomain(manifest, slug)
    entry_url = f"https://{subdomain}.{domain}"
    evidence_dir = f"apps/{slug}/acceptance"

    return {
        "schema_version": 1,
        "slug": slug,
        "package": package,
        "entry_url": entry_url,
        "box_domain": domain,
        "manifest_path": f"apps/{slug}/lzc-manifest.yml",
        "evidence_dir": evidence_dir,
        "result_path": f"{evidence_dir}/browser-use-result.json",
        "checks": [
            {
                "name": "open_home",
                "kind": "browser_use",
                "url": entry_url,
                "instruction": (
                    "Open the entry URL and verify that real app content renders, "
                    "not a platform error, blank page, redirect loop, or server error."
                ),
            },
            {
                "name": "console_and_network",
                "kind": "browser_use",
                "instruction": (
                    "Inspect visible UI, console logs, and network failures for blocking errors "
                    "that would cause LazyCat review rejection."
                ),
            },
            {
                "name": "primary_workflow_smoke",
                "kind": "browser_use",
                "instruction": (
                    "Exercise the app's obvious first workflow enough to confirm routing, "
                    "static assets, and backend connectivity are functional."
                ),
            },
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a Codex Browser Use acceptance plan.")
    parser.add_argument("slug")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--box-domain", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    output_path = repo_root / "apps" / args.slug / ".browser-acceptance-plan.json"
    output_path.write_text(
        json.dumps(
            build_acceptance_plan(repo_root, args.slug, box_domain=args.box_domain),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
