#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from .publication_status import load_publication_index
    from .scout_core import DiscoveryRunLogger, check_candidate, parse_repo_input, scan_remote_candidates
except ImportError:  # pragma: no cover - direct script execution
    from publication_status import load_publication_index
    from scout_core import DiscoveryRunLogger, check_candidate, parse_repo_input, scan_remote_candidates


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_payload(candidates: list[dict[str, Any]], *, generated_at: str) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for candidate in candidates:
        status = str(candidate.get("status", "unknown"))
        counts[status] = counts.get(status, 0) + 1

    return {
        "meta": {
            "generated_at": generated_at,
            "candidate_count": len(candidates),
            "portable_count": counts.get("portable", 0),
            "already_migrated_count": counts.get("already_migrated", 0),
            "needs_review_count": counts.get("needs_review", 0),
            "excluded_count": counts.get("excluded", 0),
            "counts_by_status": counts,
        },
        "candidates": candidates,
    }


def write_candidate_files(repo_root: Path, payload: dict[str, Any]) -> dict[str, Path]:
    generated_at = str(payload.get("meta", {}).get("generated_at", ""))
    date_part = generated_at[:10] if generated_at else datetime.now(timezone.utc).date().isoformat()
    output_dir = repo_root / "registry" / "candidates"
    output_dir.mkdir(parents=True, exist_ok=True)

    latest_path = output_dir / "latest.json"
    dated_path = output_dir / f"{date_part}.json"
    content = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    latest_path.write_text(content, encoding="utf-8")
    dated_path.write_text(content, encoding="utf-8")
    return {"latest": latest_path, "dated": dated_path}


def default_discovery_log_path(repo_root: Path, generated_at: str) -> Path:
    run_id = generated_at.replace(":", "").replace("-", "")
    return repo_root / "registry" / "auto-migration" / "logs" / "discovery-runs" / f"{run_id}.jsonl"


def check_repository(
    repo_ref: str,
    *,
    checked_at: str,
    publication_index: dict[str, dict[str, Any]] | None = None,
    logger: DiscoveryRunLogger | None = None,
) -> dict[str, Any]:
    parsed = parse_repo_input(repo_ref)
    if not parsed:
        raise ValueError(f"Invalid GitHub repository reference: {repo_ref}")
    owner, repo = parsed
    full_name = f"{owner}/{repo}"
    return check_candidate(
        {
            "source_name": "manual_check",
            "source_label": "Manual Check",
            "source_labels": ["Manual Check"],
            "owner": owner,
            "repo": repo,
            "full_name": full_name,
            "repo_url": f"https://github.com/{full_name}",
            "description": "",
            "language": "",
            "total_stars": 0,
            "stars_today": 0,
            "sources": ["manual_check"],
        },
        checked_at=checked_at,
        publication_index=publication_index,
        logger=logger,
    )


def scan_candidates(
    *,
    limit: int,
    checked_at: str,
    include_github_search: bool,
    include_awesome: bool,
    publication_index: dict[str, dict[str, Any]] | None = None,
    logger: DiscoveryRunLogger | None = None,
) -> list[dict[str, Any]]:
    repos = scan_remote_candidates(include_github_search=include_github_search, include_awesome=include_awesome)
    if logger:
        logger.event(
            stage="scan_sources",
            inputs={
                "limit": limit,
                "include_github_search": include_github_search,
                "include_awesome": include_awesome,
            },
            outputs={"repo_count": len(repos), "selected_count": len(repos[:limit])},
            decision={"status": "selected_for_candidate_check"},
            evidence=[f"repos={len(repos)}", f"limit={limit}"],
            source="scripts.scout.scan_candidates",
        )
    candidates: list[dict[str, Any]] = []
    for repo in repos[:limit]:
        candidates.append(check_candidate(repo, checked_at=checked_at, publication_index=publication_index, logger=logger))
    return candidates


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Discover and classify LazyCat migration candidates.")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))

    subparsers = parser.add_subparsers(dest="command", required=True)
    scan_parser = subparsers.add_parser("scan", help="Scan remote sources and write candidate snapshots.")
    scan_parser.add_argument("--limit", type=int, default=50)
    scan_parser.add_argument("--skip-github-search", action="store_true")
    scan_parser.add_argument("--skip-awesome-selfhosted", action="store_true")
    scan_parser.add_argument("--log-path", default="", help="Write structured discovery JSONL events to this path.")

    check_parser = subparsers.add_parser("check", help="Classify one GitHub repository.")
    check_parser.add_argument("repo")
    check_parser.add_argument("--log-path", default="", help="Write structured discovery JSONL events to this path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    checked_at = utc_now_iso()
    publication_index = load_publication_index(repo_root)
    log_path_arg = str(getattr(args, "log_path", "") or "").strip()
    log_path = Path(log_path_arg).expanduser() if log_path_arg else default_discovery_log_path(repo_root, checked_at)
    if log_path_arg and not log_path.is_absolute():
        log_path = repo_root / log_path
    logger = DiscoveryRunLogger(log_path)

    if args.command == "check":
        candidate = check_repository(args.repo, checked_at=checked_at, publication_index=publication_index, logger=logger)
        print(json.dumps(candidate, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.limit < 1:
        raise SystemExit("--limit must be >= 1")

    candidates = scan_candidates(
        limit=args.limit,
        checked_at=checked_at,
        include_github_search=not args.skip_github_search,
        include_awesome=not args.skip_awesome_selfhosted,
        publication_index=publication_index,
        logger=logger,
    )
    payload = build_payload(candidates, generated_at=checked_at)
    paths = write_candidate_files(repo_root, payload)
    print(paths["latest"])
    print(logger.path)
    print(json.dumps(payload["meta"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
