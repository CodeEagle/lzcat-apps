#!/usr/bin/env python3

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path


BUILD_MODES = ("auto", "build", "install", "reinstall", "validate-only")
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run AI-assisted LazyCat migration flow.")
    parser.add_argument("source")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--build-mode", choices=BUILD_MODES, default="reinstall")
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
    guard_reason = existing_app_guard_reason(
        repo_root,
        args.source,
        resume=args.resume,
        allow_existing=args.allow_existing,
    )
    if guard_reason:
        print(guard_reason)
        return 2

    migrate_result = subprocess.run(
        build_full_migrate_command(
            args.source,
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
