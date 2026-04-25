#!/usr/bin/env python3

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


BUILD_MODES = ("auto", "build", "install", "reinstall", "validate-only")


def build_full_migrate_command(source: str, *, build_mode: str, resume: bool = False) -> list[str]:
    command = ["python3", "scripts/full_migrate.py", source, "--build-mode", build_mode]
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
    parser.add_argument("--functional-check", action="store_true")
    parser.add_argument("--slug", help="App slug for the optional functional check.")
    parser.add_argument("--box-domain", help="LazyCat box domain for Browser Use acceptance.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    migrate_result = subprocess.run(
        build_full_migrate_command(args.source, build_mode=args.build_mode, resume=args.resume),
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
