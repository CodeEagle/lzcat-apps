#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any


BUILD_MODES = ("auto", "build", "install", "reinstall", "validate-only")
DEFAULT_CANDIDATE_SNAPSHOT = "registry/candidates/latest.json"
DEFAULT_CANDIDATE_STATUSES = ("portable",)
GITHUB_SOURCE_RE = re.compile(
    r"^(?:https?://github\.com/)?(?P<owner>[^/\s]+)/(?P<repo>[^/\s#?]+?)(?:\.git)?/?$",
    re.IGNORECASE,
)


def infer_slug_from_source(source: str) -> str:
    text = source.strip()
    match = GITHUB_SOURCE_RE.match(text)
    if match:
        return re.sub(r"[^0-9a-zA-Z_.-]+", "-", match.group("repo")).strip("-").lower()
    tail = text.rsplit("/", 1)[-1].split(":", 1)[0]
    return re.sub(r"[^0-9a-zA-Z_.-]+", "-", tail).strip("-").lower()


def existing_app_guard_reason(
    repo_root: Path,
    source: str,
    *,
    app_exists: bool | None = None,
    resume: bool = False,
    allow_existing: bool = False,
) -> str:
    slug = infer_slug_from_source(source)
    exists = (repo_root / "apps" / slug).exists() if app_exists is None else app_exists
    if not exists or resume or allow_existing:
        return ""
    return (
        f"apps/{slug} already exists; use --resume to continue it, "
        "--allow-existing to intentionally rewrite it, or local_build.sh for build-only validation"
    )


def build_full_migrate_command(
    source: str,
    *,
    build_mode: str,
    resume: bool = False,
    commit_scaffold: bool = False,
) -> list[str]:
    command = ["python3", "scripts/full_migrate.py", source, "--build-mode", build_mode]
    if not commit_scaffold:
        command.append("--no-commit")
    if resume:
        command.append("--resume")
    return command


def build_functional_check_command(slug: str, *, box_domain: str) -> list[str]:
    return ["python3", "scripts/functional_checker.py", slug, "--box-domain", box_domain]


def next_stage_after_functional_check(status: str) -> str:
    if status == "browser_pass":
        return "functional_passed"
    if status == "browser_failed":
        return "functional_failed"
    return "functional_pending"


def load_candidate_snapshot(repo_root: Path, snapshot_path: str) -> dict[str, Any]:
    path = Path(snapshot_path)
    if not path.is_absolute():
        path = repo_root / path
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Candidate snapshot must be a JSON object: {path}")
    return payload


def select_next_candidate(
    snapshot: dict[str, Any],
    *,
    allowed_statuses: tuple[str, ...] = DEFAULT_CANDIDATE_STATUSES,
) -> dict[str, Any] | None:
    candidates = snapshot.get("candidates")
    if not isinstance(candidates, list):
        return None

    allowed = {status.lower() for status in allowed_statuses}
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        status = str(candidate.get("status", "")).strip().lower()
        if status in allowed:
            return candidate
    return None


def candidate_source(candidate: dict[str, Any]) -> str:
    full_name = str(candidate.get("full_name", "")).strip()
    if full_name:
        return full_name
    repo_url = str(candidate.get("repo_url", "")).strip()
    if repo_url:
        return repo_url
    raise ValueError("Selected candidate has no full_name or repo_url")


def resolve_migration_source(
    repo_root: Path,
    source: str | None,
    *,
    candidates_path: str | None = None,
    candidate_statuses: tuple[str, ...] = DEFAULT_CANDIDATE_STATUSES,
) -> str:
    if not candidates_path:
        if not source:
            raise ValueError("source is required unless --from-candidates is used")
        return source

    if source:
        raise ValueError("--from-candidates cannot be used with an explicit source")

    snapshot = load_candidate_snapshot(repo_root, candidates_path)
    candidate = select_next_candidate(snapshot, allowed_statuses=candidate_statuses)
    if not candidate:
        statuses = ", ".join(candidate_statuses)
        raise ValueError(f"No candidate found with status: {statuses}")
    return candidate_source(candidate)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run AI-assisted LazyCat migration flow.")
    parser.add_argument("source", nargs="?")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--build-mode", choices=BUILD_MODES, default="reinstall")
    parser.add_argument(
        "--from-candidates",
        nargs="?",
        const=DEFAULT_CANDIDATE_SNAPSHOT,
        help="Select the next migration source from a scout candidate snapshot.",
    )
    parser.add_argument(
        "--candidate-status",
        action="append",
        dest="candidate_statuses",
        help="Candidate status allowed when selecting from a snapshot. Defaults to portable.",
    )
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--allow-existing",
        action="store_true",
        help="Allow rewriting an existing apps/<slug> during migration scaffolding.",
    )
    parser.add_argument(
        "--commit-scaffold",
        action="store_true",
        help="Allow full_migrate.py to create its scaffold commit before Browser Use acceptance.",
    )
    parser.add_argument("--functional-check", action="store_true")
    parser.add_argument("--slug", help="App slug for the optional functional check.")
    parser.add_argument("--box-domain", help="LazyCat box domain for Browser Use acceptance.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    try:
        source = resolve_migration_source(
            repo_root,
            args.source,
            candidates_path=args.from_candidates,
            candidate_statuses=tuple(args.candidate_statuses or DEFAULT_CANDIDATE_STATUSES),
        )
    except ValueError as exc:
        print(exc)
        return 2

    guard_reason = existing_app_guard_reason(
        repo_root,
        source,
        resume=args.resume,
        allow_existing=args.allow_existing,
    )
    if guard_reason:
        print(guard_reason)
        return 2

    migrate_result = subprocess.run(
        build_full_migrate_command(
            source,
            build_mode=args.build_mode,
            resume=args.resume,
            commit_scaffold=args.commit_scaffold,
        ),
        cwd=repo_root,
        text=True,
        check=False,
    )
    if migrate_result.returncode != 0:
        return migrate_result.returncode

    if args.functional_check:
        if not args.slug or not args.box_domain:
            raise SystemExit("--functional-check requires --slug and --box-domain")
        check_result = subprocess.run(
            build_functional_check_command(args.slug, box_domain=args.box_domain),
            cwd=repo_root,
            text=True,
            check=False,
        )
        return check_result.returncode

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
