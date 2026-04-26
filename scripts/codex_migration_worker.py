#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


DEFAULT_TASK_ROOT = "registry/auto-migration/codex-tasks"
DEFAULT_OUTBOX = "registry/auto-migration/notifications"
DEFAULT_CODEX_WORKER_MODEL = "gpt-5.5"
DEFAULT_CODEX_FALLBACK_MODEL = "gpt-5.4"


@dataclass(frozen=True)
class CodexWorkerConfig:
    repo_root: Path
    task_dir: Path
    outbox_dir: Path | None = None
    box_domain: str = ""
    model: str = DEFAULT_CODEX_WORKER_MODEL
    execute: bool = True


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def safe_task_name(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z_.-]+", "-", value).strip("-").lower() or "unknown"


def read_text_if_exists(path: Path, *, max_chars: int = 12000) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]


def read_recent_logs(repo_root: Path, *, max_chars: int = 20000) -> str:
    log_dir = repo_root / "registry" / "auto-migration" / "logs"
    chunks: list[str] = []
    for name in ("launchd.err.log", "launchd.out.log"):
        path = log_dir / name
        content = read_text_if_exists(path, max_chars=max_chars // 2)
        if content:
            chunks.append(f"## {name}\n\n{content}")
    return "\n\n".join(chunks)


def build_codex_prompt(
    repo_root: Path,
    item: dict[str, Any],
    *,
    queue_path: Path | None = None,
    box_domain: str = "",
    recent_logs: str = "",
) -> str:
    slug = str(item.get("slug", "")).strip()
    app_dir = repo_root / "apps" / slug if slug else repo_root / "apps"
    item_json = json.dumps(item, ensure_ascii=False, indent=2, sort_keys=True)
    app_state = read_text_if_exists(app_dir / ".migration-state.json", max_chars=12000)
    functional_check = read_text_if_exists(app_dir / ".functional-check.json", max_chars=6000)

    return f"""You are a Codex migration worker running unattended for the LazyCat lzcat-apps repository.

Goal:
- Fix the migration failure for this queue item.
- Prefer durable, reusable fixes in scripts/full_migrate.py or shared scripts when the failure is generic.
- Re-run the narrow failing command or relevant tests after changes.
- Leave a concise final summary with changed files and verification results.

Hard guardrails:
- Do not submit, publish, or click final LazyCat developer-console review actions.
- Do not revert unrelated user or daemon-generated changes.
- Do not delete existing app directories unless the failure investigation proves they are disposable generated output.
- Keep lzcat-apps as the single source of truth.
- If Browser Use is required, create/refresh the acceptance plan and explain the needed browser check; do not fake acceptance.
- If you are blocked on credentials, upstream ambiguity, product/listing decisions, app-store ownership, legal/license uncertainty, or final publish approval, do not guess. Update the queue item in `queue_path` to state `waiting_for_human` with a `human_request` object containing `question`, `options`, `context`, and `created_at`, then say the request should be sent to Discord.
- If the queue item already contains `human_response`, use it as the user's answer and continue from the blocked step.

Queue item:
```json
{item_json}
```

Repository:
- repo_root: {repo_root}
- app_dir: {app_dir}
- queue_path: {queue_path or "(not provided)"}
- box_domain: {box_domain or "(not provided)"}

Useful commands:
```bash
python3 scripts/full_migrate.py {item.get("source", "")} --build-mode reinstall --resume --no-commit
python3 scripts/auto_migrate.py {item.get("source", "")} --repo-root {repo_root} --build-mode reinstall --resume --functional-check --slug {slug} --box-domain {box_domain}
python3 -m unittest tests.test_full_migrate tests.test_auto_migrate tests.test_auto_migration_service -v
```

App migration state:
```json
{app_state or "{}"}
```

Functional check:
```json
{functional_check or "{}"}
```

Recent daemon logs:
```text
{recent_logs or "(no recent logs captured)"}
```
"""


def build_codex_command(config: CodexWorkerConfig) -> list[str]:
    last_message_path = config.task_dir / "last-message.md"
    return [
        "codex",
        "--ask-for-approval",
        "never",
        "exec",
        "-C",
        str(config.repo_root),
        "--model",
        config.model,
        "--sandbox",
        "danger-full-access",
        "--output-last-message",
        str(last_message_path),
        "-",
    ]


def model_requires_newer_codex(output: str) -> bool:
    return "requires a newer version of Codex" in output


def fallback_model() -> str:
    return os.environ.get("LZCAT_CODEX_FALLBACK_MODEL", DEFAULT_CODEX_FALLBACK_MODEL).strip()


def command_with_model(command: list[str], model: str) -> list[str]:
    updated = list(command)
    if "--model" in updated:
        updated[updated.index("--model") + 1] = model
    else:
        updated.extend(["--model", model])
    return updated


def write_task_bundle(
    config: CodexWorkerConfig,
    item: dict[str, Any],
    *,
    prompt: str,
    command: list[str],
    now: str,
) -> dict[str, str]:
    config.task_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = config.task_dir / "prompt.md"
    task_path = config.task_dir / "task.json"
    prompt_path.write_text(prompt, encoding="utf-8")
    task_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "created_at": now,
                "item": item,
                "command": command,
                "prompt_path": str(prompt_path),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return {"prompt_path": str(prompt_path), "task_path": str(task_path), "task_dir": str(config.task_dir)}


def relative_display(path: Path) -> str:
    parts = path.parts
    if "registry" in parts:
        return "/".join(parts[parts.index("registry") :])
    return str(path)


def write_notification(
    outbox_dir: Path,
    item: dict[str, Any],
    *,
    status: str,
    task_dir: Path,
    now: str,
) -> Path:
    outbox_dir.mkdir(parents=True, exist_ok=True)
    path = outbox_dir / f"{now.replace(':', '').replace('-', '')}-{safe_task_name(str(item.get('id', 'unknown')))}.md"
    path.write_text(
        "\n".join(
            [
                f"# Codex migration worker {status}",
                "",
                f"- time: {now}",
                f"- item: {item.get('id', '')}",
                f"- source: {item.get('source', '')}",
                f"- slug: {item.get('slug', '')}",
                f"- state: {item.get('state', '')}",
                f"- task: {relative_display(task_dir)}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return path


def run_codex(config: CodexWorkerConfig, prompt: str, command: list[str]) -> int:
    stdout_path = config.task_dir / "codex.stdout.log"
    stderr_path = config.task_dir / "codex.stderr.log"
    result = subprocess.run(command, input=prompt, text=True, capture_output=True, check=False)
    stdout_chunks = [result.stdout or ""]
    stderr_chunks = [result.stderr or ""]
    fallback_used: dict[str, Any] | None = None
    combined_output = f"{result.stdout or ''}\n{result.stderr or ''}"
    fallback = fallback_model()
    if result.returncode != 0 and fallback and fallback != config.model and model_requires_newer_codex(combined_output):
        fallback_command = command_with_model(command, fallback)
        fallback_result = subprocess.run(fallback_command, input=prompt, text=True, capture_output=True, check=False)
        stdout_chunks.append(f"\n\n--- retry with {fallback} ---\n{fallback_result.stdout or ''}")
        stderr_chunks.append(f"\n\n--- retry with {fallback} ---\n{fallback_result.stderr or ''}")
        fallback_used = {
            "from_model": config.model,
            "to_model": fallback,
            "original_returncode": result.returncode,
            "returncode": fallback_result.returncode,
        }
        result = fallback_result
    stdout_path.write_text("".join(stdout_chunks), encoding="utf-8")
    stderr_path.write_text("".join(stderr_chunks), encoding="utf-8")
    if fallback_used:
        (config.task_dir / "model-fallback.json").write_text(
            json.dumps(fallback_used, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return result.returncode


def parse_item_json(value: str) -> dict[str, Any]:
    payload = json.loads(value)
    if not isinstance(payload, dict):
        raise ValueError("--item-json must decode to an object")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a Codex worker for one LazyCat migration queue item.")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--queue-path", default="")
    parser.add_argument("--task-root", default=DEFAULT_TASK_ROOT)
    parser.add_argument("--outbox-dir", default=DEFAULT_OUTBOX)
    parser.add_argument("--item-json", required=True)
    parser.add_argument("--box-domain", default="")
    parser.add_argument("--model", default=DEFAULT_CODEX_WORKER_MODEL)
    parser.add_argument("--no-execute", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    queue_path = Path(args.queue_path).expanduser() if args.queue_path else None
    if queue_path and not queue_path.is_absolute():
        queue_path = repo_root / queue_path
    item = parse_item_json(args.item_json)
    now = utc_now_iso()
    task_root = Path(args.task_root)
    if not task_root.is_absolute():
        task_root = repo_root / task_root
    outbox_dir = Path(args.outbox_dir)
    if not outbox_dir.is_absolute():
        outbox_dir = repo_root / outbox_dir
    task_dir = task_root / f"{now.replace(':', '').replace('-', '')}-{safe_task_name(str(item.get('id', 'unknown')))}"
    config = CodexWorkerConfig(
        repo_root=repo_root,
        task_dir=task_dir,
        outbox_dir=outbox_dir,
        box_domain=args.box_domain,
        model=args.model,
        execute=not args.no_execute,
    )
    prompt = build_codex_prompt(
        repo_root,
        item,
        queue_path=queue_path,
        box_domain=args.box_domain,
        recent_logs=read_recent_logs(repo_root),
    )
    command = build_codex_command(config)
    bundle = write_task_bundle(config, item, prompt=prompt, command=command, now=now)

    status = "prepared"
    returncode = 0
    if config.execute:
        returncode = run_codex(config, prompt, command)
        status = "completed" if returncode == 0 else "failed"

    notification_path = write_notification(outbox_dir, item, status=status, task_dir=task_dir, now=now)
    result = {
        "status": status,
        "returncode": returncode,
        "task_dir": bundle["task_dir"],
        "notification_path": str(notification_path),
    }
    (task_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return returncode


if __name__ == "__main__":
    raise SystemExit(main())
