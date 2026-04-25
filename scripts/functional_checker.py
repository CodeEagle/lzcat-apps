#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from .browser_acceptance_plan import build_acceptance_plan
except ImportError:  # pragma: no cover - direct script execution
    from browser_acceptance_plan import build_acceptance_plan


def classify_acceptance(result: dict[str, Any] | None) -> str:
    if not result:
        return "browser_pending"
    if result.get("status") != "pass":
        return "browser_failed"
    if result.get("blocking_issues"):
        return "browser_failed"

    browser_use = result.get("browser_use")
    if not isinstance(browser_use, dict):
        return "browser_failed"
    if browser_use.get("dom_rendered") is not True:
        return "browser_failed"
    if browser_use.get("console_errors") or browser_use.get("network_failures"):
        return "browser_failed"
    return "browser_pass"


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def acceptance_result_path(repo_root: Path, plan: dict[str, Any]) -> Path:
    result_path = str(plan.get("result_path", "")).strip()
    if result_path:
        return repo_root / result_path
    return repo_root / "apps" / str(plan["slug"]) / ".browser-acceptance.json"


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_functional_check(repo_root: Path, slug: str, *, box_domain: str) -> dict[str, Any]:
    app_dir = repo_root / "apps" / slug
    plan = build_acceptance_plan(repo_root, slug, box_domain=box_domain)
    plan_path = app_dir / ".browser-acceptance-plan.json"
    write_json(plan_path, plan)

    result_path = acceptance_result_path(repo_root, plan)
    acceptance = read_json(result_path)
    browser_status = classify_acceptance(acceptance)

    return {
        "schema_version": 1,
        "slug": slug,
        "package": plan.get("package", ""),
        "entry_url": plan.get("entry_url", ""),
        "status": "pass" if browser_status == "browser_pass" else browser_status,
        "browser_acceptance_status": browser_status,
        "browser_acceptance_plan_path": str(plan_path.relative_to(repo_root)),
        "browser_acceptance_plan": plan,
        "browser_acceptance_result_path": str(result_path.relative_to(repo_root)),
        "browser_acceptance": acceptance,
    }


def write_functional_check(repo_root: Path, slug: str, payload: dict[str, Any]) -> Path:
    output_path = repo_root / "apps" / slug / ".functional-check.json"
    write_json(output_path, payload)
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Require Codex Browser Use functional acceptance for a LazyCat app.")
    parser.add_argument("slug")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--box-domain", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    output = build_functional_check(repo_root, args.slug, box_domain=args.box_domain)
    output_path = write_functional_check(repo_root, args.slug, output)
    print(output_path)
    return 0 if output["browser_acceptance_status"] == "browser_pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
