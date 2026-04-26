#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

try:
    from .auto_migrate import infer_slug_from_source
    from .project_config import load_project_config
except ImportError:  # pragma: no cover - direct script execution
    from auto_migrate import infer_slug_from_source
    from project_config import load_project_config


DEFAULT_CANDIDATE_SNAPSHOT = "registry/candidates/latest.json"
DEFAULT_QUEUE_PATH = "registry/auto-migration/queue.json"
FILTERED_CANDIDATE_STATUSES = {"already_migrated", "excluded", "in_progress", "needs_review"}
PROTECTED_STATES = {
    "scaffolded",
    "build_failed",
    "installed",
    "browser_pending",
    "browser_failed",
    "browser_passed",
    "copy_ready",
    "publish_ready",
    "published",
}


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


@dataclass(frozen=True)
class ServiceConfig:
    repo_root: Path
    queue_path: Path
    candidate_snapshot: str = DEFAULT_CANDIDATE_SNAPSHOT
    scan_limit: int = 50
    skip_status_sync: bool = False
    skip_scout: bool = False
    skip_github_search: bool = False
    skip_awesome_selfhosted: bool = False
    dry_run: bool = False
    enable_build_install: bool = False
    functional_check: bool = False
    box_domain: str = ""
    developer_url: str = ""
    max_migrations_per_cycle: int = 1
    commit_scaffold: bool = False
    resume: bool = False
    enable_codex_worker: bool = False
    max_codex_attempts: int = 1


CommandRunner = Callable[[list[str]], CommandResult]


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp_path.replace(path)


def candidate_source(candidate: dict[str, Any]) -> str:
    full_name = str(candidate.get("full_name", "")).strip()
    if full_name:
        return full_name
    repo_url = str(candidate.get("repo_url", "")).strip()
    if repo_url:
        return repo_url
    raise ValueError("candidate is missing full_name and repo_url")


def candidate_id(candidate: dict[str, Any]) -> str:
    source = candidate_source(candidate)
    if "github.com/" in source:
        source = source.rstrip("/").removesuffix(".git").rsplit("github.com/", 1)[-1]
    return f"github:{source.lower()}"


def candidate_slug(candidate: dict[str, Any]) -> str:
    repo = str(candidate.get("repo", "")).strip()
    if repo:
        return infer_slug_from_source(repo)
    return infer_slug_from_source(candidate_source(candidate))


def candidate_state(candidate: dict[str, Any]) -> str:
    status = str(candidate.get("status", "")).strip().lower()
    if status == "portable":
        return "ready"
    if status in FILTERED_CANDIDATE_STATUSES:
        return "filtered_out"
    return "filtered_out"


def empty_queue(now: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "meta": {"created_at": now, "updated_at": now},
        "items": [],
    }


def upsert_candidates(queue: dict[str, Any], candidates: list[dict[str, Any]], *, now: str) -> dict[str, Any]:
    items = queue.get("items")
    if not isinstance(items, list):
        items = []

    by_id: dict[str, dict[str, Any]] = {}
    ordered_ids: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id", "")).strip()
        if not item_id:
            continue
        by_id[item_id] = dict(item)
        ordered_ids.append(item_id)

    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        item_id = candidate_id(candidate)
        source = candidate_source(candidate)
        slug = candidate_slug(candidate)
        next_state = candidate_state(candidate)
        existing = by_id.get(item_id)
        if existing:
            state = str(existing.get("state", "")).strip()
            if state not in PROTECTED_STATES:
                existing["state"] = next_state
            existing.update(
                {
                    "source": source,
                    "slug": slug,
                    "candidate_status": str(candidate.get("status", "")).strip(),
                    "candidate": candidate,
                    "updated_at": now,
                }
            )
            by_id[item_id] = existing
            continue

        by_id[item_id] = {
            "id": item_id,
            "source": source,
            "slug": slug,
            "state": next_state,
            "candidate_status": str(candidate.get("status", "")).strip(),
            "candidate": candidate,
            "attempts": 0,
            "created_at": now,
            "updated_at": now,
        }
        ordered_ids.append(item_id)

    queue["schema_version"] = 1
    meta = queue.get("meta") if isinstance(queue.get("meta"), dict) else {}
    meta.setdefault("created_at", now)
    meta["updated_at"] = now
    queue["meta"] = meta
    queue["items"] = [by_id[item_id] for item_id in ordered_ids if item_id in by_id]
    return queue


def select_next_ready_item(queue: dict[str, Any]) -> dict[str, Any] | None:
    items = queue.get("items")
    if not isinstance(items, list):
        return None
    for item in items:
        if isinstance(item, dict) and item.get("state") == "ready":
            return item
    return None


def update_item_state(
    queue: dict[str, Any],
    item_id: str,
    *,
    state: str,
    now: str,
    last_error: str = "",
) -> None:
    items = queue.get("items")
    if not isinstance(items, list):
        return
    for item in items:
        if not isinstance(item, dict) or item.get("id") != item_id:
            continue
        item["state"] = state
        item["updated_at"] = now
        item["attempts"] = int(item.get("attempts") or 0) + 1
        if last_error:
            item["last_error"] = last_error
        else:
            item.pop("last_error", None)
        break


def build_status_sync_command(config: ServiceConfig) -> list[str]:
    return ["python3", "scripts/status_sync.py", "--repo-root", str(config.repo_root)]


def build_scout_scan_command(config: ServiceConfig) -> list[str]:
    command = [
        "python3",
        "scripts/scout.py",
        "--repo-root",
        str(config.repo_root),
        "scan",
        "--limit",
        str(config.scan_limit),
    ]
    if config.skip_github_search:
        command.append("--skip-github-search")
    if config.skip_awesome_selfhosted:
        command.append("--skip-awesome-selfhosted")
    return command


def build_auto_migrate_command(config: ServiceConfig, item: dict[str, Any]) -> list[str]:
    build_mode = "reinstall" if config.enable_build_install else "validate-only"
    command = [
        "python3",
        "scripts/auto_migrate.py",
        str(item["source"]),
        "--repo-root",
        str(config.repo_root),
        "--build-mode",
        build_mode,
    ]
    if config.resume:
        command.append("--resume")
    if config.commit_scaffold:
        command.append("--commit-scaffold")
    if config.enable_build_install and config.functional_check:
        command.extend(["--functional-check", "--slug", str(item["slug"]), "--box-domain", config.box_domain])
    return command


def build_functional_check_command(config: ServiceConfig, item: dict[str, Any]) -> list[str]:
    return [
        "python3",
        "scripts/functional_checker.py",
        str(item["slug"]),
        "--repo-root",
        str(config.repo_root),
        "--box-domain",
        config.box_domain,
    ]


def build_copywriter_command(config: ServiceConfig, item: dict[str, Any]) -> list[str]:
    return ["python3", "scripts/copywriter.py", str(item["slug"]), "--repo-root", str(config.repo_root)]


def build_prepare_submission_command(config: ServiceConfig, item: dict[str, Any]) -> list[str]:
    command = [
        "python3",
        "scripts/prepare_store_submission.py",
        str(item["slug"]),
        "--repo-root",
        str(config.repo_root),
    ]
    if config.developer_url:
        command.extend(["--developer-url", config.developer_url])
    return command


def build_codex_worker_command(config: ServiceConfig, item: dict[str, Any]) -> list[str]:
    command = [
        "python3",
        "scripts/codex_migration_worker.py",
        "--repo-root",
        str(config.repo_root),
        "--item-json",
        json.dumps(item, ensure_ascii=False, sort_keys=True),
    ]
    if config.box_domain:
        command.extend(["--box-domain", config.box_domain])
    return command


def run_subprocess(command: list[str], *, cwd: Path) -> CommandResult:
    result = subprocess.run(command, cwd=cwd, text=True, check=False)
    return CommandResult(returncode=result.returncode)


def load_candidate_snapshot(repo_root: Path, snapshot_path: str) -> dict[str, Any]:
    path = Path(snapshot_path)
    if not path.is_absolute():
        path = repo_root / path
    return read_json(path, {"candidates": []})


def migration_success_state(config: ServiceConfig) -> str:
    if config.enable_build_install:
        return "installed"
    return "scaffolded"


def functional_check_state(repo_root: Path, slug: str) -> str:
    path = repo_root / "apps" / slug / ".functional-check.json"
    if not path.exists():
        return ""
    payload = read_json(path, {})
    status = str(payload.get("browser_acceptance_status", "")).strip()
    if status == "browser_pass":
        return "browser_passed"
    if status == "browser_failed":
        return "browser_failed"
    if status == "browser_pending":
        return "browser_pending"
    return "browser_pending"


def advance_post_acceptance(
    config: ServiceConfig,
    queue: dict[str, Any],
    *,
    runner: CommandRunner,
    now: str,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    items = queue.get("items")
    if not isinstance(items, list):
        return results

    for item in items:
        if not isinstance(item, dict) or item.get("state") not in {"browser_passed", "copy_ready"}:
            continue
        item_id = str(item.get("id", ""))
        copy_result = CommandResult(returncode=0)
        if item.get("state") == "browser_passed":
            copy_command = build_copywriter_command(config, item)
            copy_result = runner(copy_command)
            if copy_result.returncode != 0:
                update_item_state(
                    queue,
                    item_id,
                    state="browser_passed",
                    now=now,
                    last_error=f"copywriter exited {copy_result.returncode}",
                )
                results.append({"id": item_id, "status": "copy_failed", "returncode": copy_result.returncode})
                continue
            update_item_state(queue, item_id, state="copy_ready", now=now)

        if not config.developer_url:
            results.append({"id": item_id, "status": "copy_ready", "reason": "developer_url_missing"})
            continue

        submission_command = build_prepare_submission_command(config, item)
        submission_result = runner(submission_command)
        if submission_result.returncode == 0:
            update_item_state(queue, item_id, state="publish_ready", now=now)
            results.append({"id": item_id, "status": "publish_ready", "returncode": 0})
        else:
            update_item_state(
                queue,
                item_id,
                state="copy_ready",
                now=now,
                last_error=f"prepare_store_submission exited {submission_result.returncode}",
            )
            results.append({"id": item_id, "status": "copy_ready", "returncode": submission_result.returncode})

    return results


def refresh_browser_pending(
    config: ServiceConfig,
    queue: dict[str, Any],
    *,
    runner: CommandRunner,
    now: str,
) -> list[dict[str, Any]]:
    if not config.functional_check or not config.box_domain:
        return []

    results: list[dict[str, Any]] = []
    items = queue.get("items")
    if not isinstance(items, list):
        return results

    for item in items:
        if not isinstance(item, dict) or item.get("state") != "browser_pending":
            continue
        item_id = str(item.get("id", ""))
        command = build_functional_check_command(config, item)
        result = runner(command)
        state = functional_check_state(config.repo_root, str(item["slug"])) or "browser_pending"
        if state in {"browser_pending", "browser_failed", "browser_passed"}:
            update_item_state(queue, item_id, state=state, now=now)
            results.append({"id": item_id, "status": state, "returncode": result.returncode})
        else:
            results.append({"id": item_id, "status": "browser_pending", "returncode": result.returncode})

    return results


def codex_attempts(item: dict[str, Any]) -> int:
    codex = item.get("codex")
    if not isinstance(codex, dict):
        return 0
    try:
        return int(codex.get("attempts") or 0)
    except (TypeError, ValueError):
        return 0


def select_next_codex_item(queue: dict[str, Any], *, max_attempts: int) -> dict[str, Any] | None:
    items = queue.get("items")
    if not isinstance(items, list):
        return None
    for item in items:
        if not isinstance(item, dict) or item.get("state") not in {"build_failed", "browser_failed"}:
            continue
        if codex_attempts(item) >= max_attempts:
            continue
        return item
    return None


def update_item_codex_result(
    queue: dict[str, Any],
    item_id: str,
    *,
    status: str,
    returncode: int,
    now: str,
) -> None:
    items = queue.get("items")
    if not isinstance(items, list):
        return
    for item in items:
        if not isinstance(item, dict) or item.get("id") != item_id:
            continue
        codex = item.get("codex") if isinstance(item.get("codex"), dict) else {}
        codex["attempts"] = int(codex.get("attempts") or 0) + 1
        codex["last_status"] = status
        codex["last_returncode"] = returncode
        codex["last_run_at"] = now
        item["codex"] = codex
        item["updated_at"] = now
        if returncode == 0:
            item["state"] = "ready"
            item.pop("last_error", None)
        else:
            item["last_error"] = f"codex worker exited {returncode}"
        break


def advance_codex_worker(
    config: ServiceConfig,
    queue: dict[str, Any],
    *,
    runner: CommandRunner,
    now: str,
) -> list[dict[str, Any]]:
    if not config.enable_codex_worker:
        return []
    item = select_next_codex_item(queue, max_attempts=max(1, config.max_codex_attempts))
    if not item:
        return []

    command = build_codex_worker_command(config, item)
    result = runner(command)
    status = "ready" if result.returncode == 0 else "codex_failed"
    update_item_codex_result(queue, str(item.get("id", "")), status=status, returncode=result.returncode, now=now)
    return [{"id": item.get("id", ""), "status": status, "returncode": result.returncode}]


def run_cycle(config: ServiceConfig, *, runner: CommandRunner | None = None, now: str | None = None) -> dict[str, Any]:
    now = now or utc_now_iso()
    runner = runner or (lambda command: run_subprocess(command, cwd=config.repo_root))
    summary: dict[str, Any] = {
        "started_at": now,
        "commands": [],
        "browser_recheck": [],
        "codex_worker": [],
        "post_acceptance": [],
        "selected": None,
        "migration": {"status": "none"},
    }

    queue = read_json(config.queue_path, empty_queue(now))
    summary["browser_recheck"] = refresh_browser_pending(config, queue, runner=runner, now=now)
    summary["codex_worker"] = advance_codex_worker(config, queue, runner=runner, now=now)
    summary["post_acceptance"] = advance_post_acceptance(config, queue, runner=runner, now=now)
    if summary["browser_recheck"] or summary["codex_worker"] or summary["post_acceptance"]:
        write_json(config.queue_path, queue)

    if not config.skip_status_sync:
        command = build_status_sync_command(config)
        result = runner(command)
        summary["commands"].append({"command": command, "returncode": result.returncode})

    if not config.skip_scout:
        command = build_scout_scan_command(config)
        result = runner(command)
        summary["commands"].append({"command": command, "returncode": result.returncode})
        if result.returncode != 0:
            write_json(config.queue_path, queue)
            summary["migration"] = {"status": "scout_failed", "returncode": result.returncode}
            return summary

    snapshot = load_candidate_snapshot(config.repo_root, config.candidate_snapshot)
    candidates = snapshot.get("candidates") if isinstance(snapshot.get("candidates"), list) else []
    queue = upsert_candidates(queue, candidates, now=now)
    selected = select_next_ready_item(queue)
    if not selected:
        write_json(config.queue_path, queue)
        summary["migration"] = {"status": "idle"}
        return summary

    summary["selected"] = selected["id"]
    if config.dry_run:
        write_json(config.queue_path, queue)
        summary["migration"] = {"status": "dry_run"}
        return summary

    for _ in range(max(1, config.max_migrations_per_cycle)):
        selected = select_next_ready_item(queue)
        if not selected:
            break
        command = build_auto_migrate_command(config, selected)
        result = runner(command)
        summary["commands"].append({"command": command, "returncode": result.returncode})
        if result.returncode == 0:
            if config.enable_build_install and config.functional_check:
                state = functional_check_state(config.repo_root, str(selected["slug"])) or "browser_pending"
            else:
                state = migration_success_state(config)
            update_item_state(queue, str(selected["id"]), state=state, now=now)
            summary["migration"] = {"status": state, "returncode": 0}
        elif config.enable_build_install and config.functional_check:
            state = functional_check_state(config.repo_root, str(selected["slug"]))
            if state in {"browser_pending", "browser_failed", "browser_passed"}:
                update_item_state(queue, str(selected["id"]), state=state, now=now)
                summary["migration"] = {"status": state, "returncode": result.returncode}
            else:
                update_item_state(
                    queue,
                    str(selected["id"]),
                    state="build_failed",
                    now=now,
                    last_error=f"auto_migrate exited {result.returncode}",
                )
                summary["migration"] = {"status": "build_failed", "returncode": result.returncode}
                break
        else:
            update_item_state(
                queue,
                str(selected["id"]),
                state="build_failed",
                now=now,
                last_error=f"auto_migrate exited {result.returncode}",
            )
            summary["migration"] = {"status": "build_failed", "returncode": result.returncode}
            break

    write_json(config.queue_path, queue)
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the 7x24 LazyCat AI auto-migration service.")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--queue-path", default=DEFAULT_QUEUE_PATH)
    parser.add_argument("--candidate-snapshot", default=DEFAULT_CANDIDATE_SNAPSHOT)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--once", action="store_true", help="Run one cycle and exit.")
    parser.add_argument("--daemon", action="store_true", help="Run continuously.")
    parser.add_argument("--interval-seconds", type=int, default=3600)
    parser.add_argument("--skip-status-sync", action="store_true")
    parser.add_argument("--skip-scout", action="store_true")
    parser.add_argument("--skip-github-search", action="store_true")
    parser.add_argument("--skip-awesome-selfhosted", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--enable-build-install", action="store_true")
    parser.add_argument("--functional-check", action="store_true")
    parser.add_argument("--box-domain", default="")
    parser.add_argument("--developer-url", default="")
    parser.add_argument("--max-migrations-per-cycle", type=int, default=1)
    parser.add_argument("--commit-scaffold", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--enable-codex-worker", action="store_true")
    parser.add_argument("--max-codex-attempts", type=int, default=1)
    return parser.parse_args()


def build_config(args: argparse.Namespace) -> ServiceConfig:
    repo_root = Path(args.repo_root).resolve()
    queue_path = Path(args.queue_path)
    if not queue_path.is_absolute():
        queue_path = repo_root / queue_path
    if args.functional_check and not args.box_domain:
        raise SystemExit("--functional-check requires --box-domain")
    developer_url = args.developer_url or load_project_config(repo_root).lazycat.developer_apps_url
    return ServiceConfig(
        repo_root=repo_root,
        queue_path=queue_path,
        candidate_snapshot=args.candidate_snapshot,
        scan_limit=args.limit,
        skip_status_sync=args.skip_status_sync,
        skip_scout=args.skip_scout,
        skip_github_search=args.skip_github_search,
        skip_awesome_selfhosted=args.skip_awesome_selfhosted,
        dry_run=args.dry_run,
        enable_build_install=args.enable_build_install,
        functional_check=args.functional_check,
        box_domain=args.box_domain,
        developer_url=developer_url,
        max_migrations_per_cycle=max(1, args.max_migrations_per_cycle),
        commit_scaffold=args.commit_scaffold,
        resume=args.resume,
        enable_codex_worker=args.enable_codex_worker,
        max_codex_attempts=max(1, args.max_codex_attempts),
    )


def main() -> int:
    args = parse_args()
    config = build_config(args)
    if not args.daemon:
        print(json.dumps(run_cycle(config), ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    interval = max(60, args.interval_seconds)
    while True:
        print(json.dumps(run_cycle(config), ensure_ascii=False, indent=2, sort_keys=True), flush=True)
        time.sleep(interval)


if __name__ == "__main__":
    raise SystemExit(main())
