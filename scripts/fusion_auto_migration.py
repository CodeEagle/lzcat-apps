#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import plistlib
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


DEFAULT_BOX_DOMAIN = "rx79.heiyu.space"
DEFAULT_FUSION_URL = "https://fusion.rx79.heiyu.space"
DEFAULT_LABEL = "cloud.lazycat.auto-migration"


@dataclass(frozen=True)
class FusionAutoMigrationConfig:
    repo_root: Path
    box_domain: str = DEFAULT_BOX_DOMAIN
    fusion_url: str = DEFAULT_FUSION_URL
    interval_seconds: int = 3600
    limit: int = 50
    max_migrations_per_cycle: int = 1
    max_codex_attempts: int = 1
    workspace_root: Path = Path("")
    once: bool = False
    dry_run: bool = False
    disable_discord: bool = False
    disable_local_agent: bool = False


def default_workspace_root(repo_root: Path) -> Path:
    return repo_root.parent / "migration-workspaces"


def build_service_command(config: FusionAutoMigrationConfig) -> list[str]:
    workspace_root = (
        config.workspace_root
        if str(config.workspace_root).strip() not in {"", "."}
        else default_workspace_root(config.repo_root)
    )
    command = [
        "python3",
        "scripts/auto_migration_service.py",
        "--repo-root",
        str(config.repo_root),
        "--env-file",
        "scripts/.env.local",
        "--limit",
        str(config.limit),
        "--interval-seconds",
        str(config.interval_seconds),
        "--enable-build-install",
        "--functional-check",
        "--box-domain",
        config.box_domain,
        "--enable-codex-worker",
        "--max-codex-attempts",
        str(config.max_codex_attempts),
        "--max-migrations-per-cycle",
        str(config.max_migrations_per_cycle),
        "--resume",
        "--workspace-root",
        str(workspace_root),
    ]
    command.append("--once" if config.once else "--daemon")
    if config.dry_run:
        command.append("--dry-run")
    if config.disable_discord:
        command.append("--disable-discord")
    if config.disable_local_agent:
        command.append("--disable-local-agent")
    return command


def build_launchd_plist(
    *,
    label: str,
    repo_root: Path,
    command: list[str],
    stdout_path: Path,
    stderr_path: Path,
) -> dict[str, object]:
    return {
        "Label": label,
        "ProgramArguments": command,
        "WorkingDirectory": str(repo_root),
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": str(stdout_path),
        "StandardErrorPath": str(stderr_path),
        "EnvironmentVariables": {
            "PYTHONUNBUFFERED": "1",
        },
    }


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Start or render the Fusion-backed 7x24 lzcat auto-migration daemon.")
    parser.add_argument("--repo-root", default=str(repo_root))
    parser.add_argument("--box-domain", default=DEFAULT_BOX_DOMAIN)
    parser.add_argument("--fusion-url", default=DEFAULT_FUSION_URL)
    parser.add_argument("--interval-seconds", type=int, default=3600)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--max-migrations-per-cycle", type=int, default=1)
    parser.add_argument("--max-codex-attempts", type=int, default=1)
    parser.add_argument("--workspace-root", default="")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--disable-discord", action="store_true")
    parser.add_argument("--disable-local-agent", action="store_true")
    parser.add_argument("--print-command", action="store_true")
    parser.add_argument("--print-launchd-plist", action="store_true")
    parser.add_argument("--write-launchd-plist", action="store_true")
    parser.add_argument("--launchd-label", default=DEFAULT_LABEL)
    parser.add_argument("--launchd-path", default="")
    return parser.parse_args()


def config_from_args(args: argparse.Namespace) -> FusionAutoMigrationConfig:
    repo_root = Path(args.repo_root).expanduser().resolve()
    workspace_root = Path(args.workspace_root).expanduser() if args.workspace_root else Path("")
    return FusionAutoMigrationConfig(
        repo_root=repo_root,
        box_domain=args.box_domain,
        fusion_url=args.fusion_url,
        interval_seconds=max(60, args.interval_seconds),
        limit=max(1, args.limit),
        max_migrations_per_cycle=max(1, args.max_migrations_per_cycle),
        max_codex_attempts=max(1, args.max_codex_attempts),
        workspace_root=workspace_root,
        once=args.once,
        dry_run=args.dry_run,
        disable_discord=args.disable_discord,
        disable_local_agent=args.disable_local_agent,
    )


def main() -> int:
    args = parse_args()
    config = config_from_args(args)
    command = build_service_command(config)
    log_dir = config.repo_root / "registry" / "auto-migration" / "logs"
    launchd_path = Path(args.launchd_path).expanduser() if args.launchd_path else Path.home() / "Library" / "LaunchAgents" / f"{args.launchd_label}.plist"
    plist = build_launchd_plist(
        label=args.launchd_label,
        repo_root=config.repo_root,
        command=command,
        stdout_path=log_dir / "launchd.out.log",
        stderr_path=log_dir / "launchd.err.log",
    )

    if args.print_command:
        print(json.dumps({"fusion_url": config.fusion_url, "command": command}, ensure_ascii=False, indent=2))
        return 0
    if args.print_launchd_plist:
        sys.stdout.buffer.write(plistlib.dumps(plist, sort_keys=False))
        return 0
    if args.write_launchd_plist:
        launchd_path.parent.mkdir(parents=True, exist_ok=True)
        launchd_path.write_bytes(plistlib.dumps(plist, sort_keys=False))
        print(str(launchd_path))
        return 0

    return subprocess.call(command, cwd=config.repo_root)


if __name__ == "__main__":
    raise SystemExit(main())
