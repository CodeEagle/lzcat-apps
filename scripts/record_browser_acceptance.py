#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_acceptance_payload(
    *,
    slug: str,
    status: str,
    entry_url: str,
    evidence: str,
    blocking_issues: list[str],
    console_errors: list[str],
    network_failures: list[str],
    screenshots: list[str],
    accepted_at: str,
) -> dict[str, Any]:
    issues = [{"category": "browser_use", "summary": item} for item in blocking_issues]
    return {
        "schema_version": 1,
        "slug": slug,
        "status": status,
        "accepted_at": accepted_at,
        "entry_url": entry_url,
        "browser_use": {
            "dom_rendered": status == "pass" and not issues,
            "console_errors": console_errors,
            "network_failures": network_failures,
            "screenshots": screenshots,
        },
        "checks": [
            {
                "name": "open_home",
                "status": status,
                "evidence": evidence,
            }
        ],
        "blocking_issues": issues,
    }


def acceptance_output_path(repo_root: Path, slug: str) -> Path:
    return repo_root / "apps" / slug / "acceptance" / "browser-use-result.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Record Codex Browser Use acceptance result.")
    parser.add_argument("slug")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--status", choices=["pass", "fail"], required=True)
    parser.add_argument("--entry-url", required=True)
    parser.add_argument("--evidence", default="")
    parser.add_argument("--blocking-issue", action="append", default=[])
    parser.add_argument("--console-error", action="append", default=[])
    parser.add_argument("--network-failure", action="append", default=[])
    parser.add_argument("--screenshot", action="append", default=[])
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    payload = build_acceptance_payload(
        slug=args.slug,
        status=args.status,
        entry_url=args.entry_url,
        evidence=args.evidence,
        blocking_issues=args.blocking_issue,
        console_errors=args.console_error,
        network_failures=args.network_failure,
        screenshots=args.screenshot,
        accepted_at=utc_now_iso(),
    )
    output_path = acceptance_output_path(repo_root, args.slug)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(output_path)
    return 0 if args.status == "pass" and not payload["blocking_issues"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
