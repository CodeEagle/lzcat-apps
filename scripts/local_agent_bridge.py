#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def github_full_name_from_url(url: str) -> str:
    value = url.strip().rstrip("/").removesuffix(".git")
    if "github.com/" not in value:
        return ""
    return value.rsplit("github.com/", 1)[-1].strip("/")


def normalize_local_agent_candidate(project: dict[str, Any], *, origin: str) -> dict[str, Any] | None:
    full_name = str(project.get("full_name", "")).strip()
    repo_url = str(project.get("repo_url", "")).strip()
    if not full_name and repo_url:
        full_name = github_full_name_from_url(repo_url)
    if not full_name:
        owner = str(project.get("owner", "")).strip()
        repo = str(project.get("repo", "")).strip()
        if owner and repo:
            full_name = f"{owner}/{repo}"
    if "/" not in full_name:
        return None

    owner, repo = full_name.split("/", 1)
    if not repo_url:
        repo_url = f"https://github.com/{full_name}"

    status = str(project.get("status", "")).strip().lower()
    if not status:
        status = "needs_review" if origin == "external_sources" else "portable"

    candidate = {
        "full_name": full_name,
        "owner": str(project.get("owner") or owner).strip(),
        "repo": str(project.get("repo") or repo).strip(),
        "repo_url": repo_url,
        "description": str(project.get("description", "")).strip(),
        "language": str(project.get("language", "")).strip(),
        "stars_today": int(project.get("stars_today") or 0),
        "total_stars": int(project.get("total_stars") or 0),
        "status": status,
        "status_reason": str(project.get("status_reason", "")).strip(),
        "sources": project.get("sources") if isinstance(project.get("sources"), list) else [],
        "source_labels": project.get("source_labels") if isinstance(project.get("source_labels"), list) else [],
        "external_signal": str(project.get("external_signal", "")).strip(),
        "external_url": str(project.get("external_url", "")).strip(),
        "discovery_source": "local_agent",
        "local_agent": {
            "origin": origin,
            "first_seen_at": str(project.get("first_seen_at", "")).strip(),
            "last_seen_at": str(project.get("last_seen_at", "")).strip(),
            "last_checked_at": str(project.get("last_checked_at", "")).strip(),
            "manual_decision": str(project.get("manual_decision", "")).strip(),
        },
    }
    return candidate


def build_local_agent_snapshot(local_agent_root: Path, *, now: str | None = None) -> dict[str, Any]:
    now = now or utc_now_iso()
    data_dir = local_agent_root / "data"
    state = read_json(data_dir / "state.json", {"projects": {}})
    external = read_json(data_dir / "external_sources.json", {"candidates": []})

    candidates_by_name: dict[str, dict[str, Any]] = {}
    projects = state.get("projects") if isinstance(state.get("projects"), dict) else {}
    for project in projects.values():
        if not isinstance(project, dict):
            continue
        candidate = normalize_local_agent_candidate(project, origin="state.projects")
        if candidate:
            candidates_by_name[candidate["full_name"].lower()] = candidate

    external_candidates = external.get("candidates") if isinstance(external.get("candidates"), list) else []
    for project in external_candidates:
        if not isinstance(project, dict):
            continue
        candidate = normalize_local_agent_candidate(project, origin="external_sources")
        if candidate:
            candidates_by_name.setdefault(candidate["full_name"].lower(), candidate)

    candidates = sorted(
        candidates_by_name.values(),
        key=lambda item: (-int(item.get("stars_today") or 0), -int(item.get("total_stars") or 0), item["full_name"].lower()),
    )
    return {
        "meta": {
            "schema_version": 1,
            "source": "local_agent",
            "generated_at": now,
            "local_agent_root": str(local_agent_root),
            "candidate_count": len(candidates),
        },
        "candidates": candidates,
    }


def write_local_agent_snapshot(local_agent_root: Path, output_path: Path, *, now: str | None = None) -> dict[str, Any]:
    snapshot = build_local_agent_snapshot(local_agent_root, now=now)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    temp_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp_path.replace(output_path)
    return snapshot


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import LocalAgent candidates into lzcat-apps candidate snapshot format.")
    parser.add_argument("--local-agent-root", required=True)
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    snapshot = write_local_agent_snapshot(Path(args.local_agent_root).expanduser().resolve(), Path(args.output).expanduser())
    print(json.dumps(snapshot["meta"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
