#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = REPO_ROOT / "registry" / "repos" / "index.json"
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "trigger-build.yml"
START_MARKER = "          # BEGIN AUTO-GENERATED APP OPTIONS"
END_MARKER = "          # END AUTO-GENERATED APP OPTIONS"
ALL_OPTION = "all-enabled-apps"


def load_apps(index_path: Path) -> list[str]:
    payload = json.loads(index_path.read_text(encoding="utf-8"))
    apps: list[str] = []
    for entry in payload.get("repos", []):
        app_name = Path(str(entry)).stem.strip()
        if app_name:
            apps.append(app_name)
    return apps


def render_options(apps: list[str]) -> str:
    lines = [START_MARKER, f'          - "{ALL_OPTION}"']
    lines.extend(f'          - "{app}"' for app in apps)
    lines.append(END_MARKER)
    return "\n".join(lines)


def sync_workflow(index_path: Path = INDEX_PATH, workflow_path: Path = WORKFLOW_PATH) -> bool:
    workflow_text = workflow_path.read_text(encoding="utf-8")
    start = workflow_text.find(START_MARKER)
    end = workflow_text.find(END_MARKER)
    if start == -1 or end == -1 or end < start:
        raise RuntimeError(f"Failed to find workflow markers in {workflow_path}")
    end += len(END_MARKER)
    replacement = render_options(load_apps(index_path))
    updated = workflow_text[:start] + replacement + workflow_text[end:]
    if updated == workflow_text:
        return False
    workflow_path.write_text(updated, encoding="utf-8")
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync trigger-build workflow options from registry/repos/index.json")
    parser.add_argument("--check", action="store_true", help="Exit non-zero if workflow options are out of sync")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    changed = sync_workflow()
    if args.check:
        if changed:
            print("out-of-sync")
            return 1
        print("in-sync")
        return 0

    print("updated" if changed else "unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
