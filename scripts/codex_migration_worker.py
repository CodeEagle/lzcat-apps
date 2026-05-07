#!/usr/bin/env python3
"""Per-item migration repair worker.

Despite the historical `codex_*` naming kept for queue.json and import
back-compat, this now invokes the Claude Code CLI (`claude --print …`) from
@anthropic-ai/claude-code rather than the OpenAI Codex CLI. Session resume
uses Claude's `--resume <sessionId>` flag; session IDs are extracted from the
stream-json event log emitted by Claude Code on stdout.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


DEFAULT_TASK_ROOT = "registry/auto-migration/codex-tasks"
DEFAULT_OUTBOX = "registry/auto-migration/notifications"
DEFAULT_CODEX_WORKER_MODEL = "claude-sonnet-4-6"
SESSION_ID_PATTERN = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)


@dataclass(frozen=True)
class CodexWorkerConfig:
    repo_root: Path
    task_dir: Path
    outbox_dir: Path | None = None
    box_domain: str = ""
    model: str = DEFAULT_CODEX_WORKER_MODEL
    session_id: str = ""
    execute: bool = True


@dataclass(frozen=True)
class CodexRunResult:
    returncode: int
    session_id: str = ""


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


try:
    from .codex_discovery_reviewer import (
        fetch_license_info,
        fetch_repo_signals,
        format_license_block,
        format_repo_signals_block,
    )
except ImportError:  # pragma: no cover
    from codex_discovery_reviewer import (
        fetch_license_info,
        fetch_repo_signals,
        format_license_block,
        format_repo_signals_block,
    )


def build_planning_prompt(
    repo_root: Path,
    item: dict[str, Any],
    *,
    queue_path: Path | None = None,
    box_domain: str = "",
    repo_signals: dict[str, Any] | None = None,
    license_info: dict[str, Any] | None = None,
) -> str:
    """Pre-build planning prompt — claude examines upstream source and
    PRE-WRITES apps/<slug>/Dockerfile.template + adjusts lzc-build.yml's
    build_strategy BEFORE the mechanical build chain runs.

    Run this once per slug right after scaffold succeeds and before the
    first build attempt; build_codex_prompt below stays as the
    after-build_failed repair path. Together they bracket the build.
    """
    slug = str(item.get("slug", "")).strip()
    app_dir = repo_root / "apps" / slug if slug else repo_root / "apps"
    item_json = json.dumps(item, ensure_ascii=False, indent=2, sort_keys=True)
    if repo_signals is None:
        repo_signals = fetch_repo_signals(item)
    if license_info is None:
        license_info = fetch_license_info(item)
    repo_signals_block = format_repo_signals_block(repo_signals)
    license_block = format_license_block(license_info)
    manifest = read_text_if_exists(app_dir / "lzc-manifest.yml", max_chars=4000)
    build_yml = read_text_if_exists(app_dir / "lzc-build.yml", max_chars=2000)
    readme = read_text_if_exists(app_dir / "README.md", max_chars=4000)

    return f"""You are Claude, the migration PLANNER for the LazyCat lzcat-apps pipeline.

Goal:
- Pre-arm the mechanical build chain so it succeeds on the FIRST attempt.
- Decide the right `build_strategy` for this slug from actual source code.
- If the upstream lacks a Dockerfile, write a tailored
  `apps/{slug}/Dockerfile.template` that builds and runs the upstream as
  a containerized service.
- Update `apps/{slug}/lzc-build.yml`'s build_strategy field to match.
- Lightly tweak `apps/{slug}/lzc-manifest.yml` if obvious defaults are
  wrong for this app (port, service name, env vars upstream README needs).

Hard guardrails:
- DO NOT run the build, install, or any LazyCat CLI commands.
- DO NOT modify scripts/ — fixes belong in `apps/{slug}/` only.
- DO NOT commit / push — the orchestrator handles git.
- KEEP existing `lzc-sdk-version`, `manifest`, `pkgout`, `icon` lines
  in lzc-build.yml verbatim; only add/change `build_strategy`.
- If the right strategy is already obvious from the existing
  lzc-build.yml AND the existing files build cleanly, exit cleanly with
  the message: `PLANNER: skipped — existing scaffolding looks correct`.

Slug: `{slug}`
Upstream license:
{license_block}

Upstream source-code signals:
{repo_signals_block}

Build strategies (set via `build_strategy:` line in lzc-build.yml):
  * `official_image` — upstream publishes a runnable Docker image. Use when
    README / files suggest a published image AND there's no Dockerfile in
    the source tree.
  * `upstream_dockerfile` — upstream has its own Dockerfile at root or a
    clearly-named subdir. Set this when the file tree confirms a
    Dockerfile exists; no need to write a template.
  * `upstream_with_target_template` — upstream has buildable source but
    no Dockerfile. Write `apps/{slug}/Dockerfile.template` from scratch:
    pick the right base image (rust:1-slim for Cargo.toml, node:20-slim
    for package.json, python:3.12-slim for pyproject.toml,
    golang:1.22-alpine for go.mod), COPY upstream into /app, RUN the
    build command, expose the right port, CMD with the entrypoint
    (binary path, `node server.js`, `python -m app`, etc.). Use multi-
    stage when the build artifact is a binary you can drop into a slim
    runtime.
  * `precompiled_binary` — only when upstream releases binary artifacts on
    GitHub Releases and you'd rather pull than compile.

Decision flow:
  1. file tree has `Dockerfile` (root or first-level subdir) → strategy
     `upstream_dockerfile`. Update lzc-build.yml only.
  2. README explicitly references a published image (ghcr.io / docker.io
     URL) → `official_image`. Update lzc-build.yml only.
  3. otherwise upstream is buildable from source → strategy
     `upstream_with_target_template` AND write Dockerfile.template.
  4. unclear / unsupported → exit cleanly. Mechanical fallbacks +
     post-failure repair will pick up.

Concrete output requirements:
  * Use Edit / Write tools to modify `apps/{slug}/lzc-build.yml` and
    (if applicable) write `apps/{slug}/Dockerfile.template`.
  * Append `build_strategy: <chosen>` to lzc-build.yml. If a different
    `build_strategy` already exists, replace it.
  * Print a short final summary: which strategy you chose, which files
    you wrote, and the rationale (1-2 sentences referring to specific
    source signals).

Queue item:
```json
{item_json}
```

Repository:
- repo_root: {repo_root}
- app_dir: {app_dir}
- queue_path: {queue_path or "(not provided)"}

Current scaffolded files in apps/{slug}/:

`lzc-manifest.yml`:
```yaml
{manifest or "(missing — bootstrap_migration has not run yet)"}
```

`lzc-build.yml`:
```yaml
{build_yml or "(missing)"}
```

`README.md` (first 4 KB):
```markdown
{readme or "(missing)"}
```
"""


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

    return f"""You are Claude, the migration repair worker running unattended for the LazyCat lzcat-apps repository.

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
    """Build the Claude Code CLI invocation for one migration-repair session.

    Reads the prompt from stdin, emits stream-json so we can extract the
    session_id for the next attempt, and bypasses the interactive permission
    prompt so the worker runs unattended in CI.
    """
    cmd = [
        "claude",
        "--print",
        "--dangerously-skip-permissions",
        "--model",
        config.model,
        "--add-dir",
        str(config.repo_root),
        "--output-format",
        "stream-json",
        "--verbose",
    ]
    session_id = config.session_id.strip()
    if session_id:
        cmd.extend(["--resume", session_id])
    return cmd


def _session_id_from_value(value: Any) -> str:
    if isinstance(value, str) and SESSION_ID_PATTERN.fullmatch(value.strip()):
        return value.strip()
    return ""


def _walk_session_id(payload: Any) -> str:
    if isinstance(payload, dict):
        for key, value in payload.items():
            key_text = str(key).lower()
            if ("session" in key_text or "conversation" in key_text) and (session_id := _session_id_from_value(value)):
                return session_id
        for value in payload.values():
            if session_id := _walk_session_id(value):
                return session_id
    elif isinstance(payload, list):
        for value in payload:
            if session_id := _walk_session_id(value):
                return session_id
    return ""


def extract_session_id_from_jsonl(output: str) -> str:
    session_id = ""
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if found := _walk_session_id(payload):
            session_id = found
    if session_id:
        return session_id
    matches = SESSION_ID_PATTERN.findall(output)
    return matches[-1] if matches else ""


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
                "resumed": bool(config.session_id.strip()),
                "session_id": config.session_id.strip(),
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
                f"# Claude migration repair worker {status}",
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


def run_codex(config: CodexWorkerConfig, prompt: str, command: list[str]) -> CodexRunResult:
    stdout_path = config.task_dir / "claude.stdout.log"
    stderr_path = config.task_dir / "claude.stderr.log"
    result = subprocess.run(command, input=prompt, text=True, capture_output=True, check=False)
    stdout_path.write_text(result.stdout or "", encoding="utf-8")
    stderr_path.write_text(result.stderr or "", encoding="utf-8")
    session_id = extract_session_id_from_jsonl(result.stdout or "") or config.session_id.strip()
    return CodexRunResult(returncode=result.returncode, session_id=session_id)


def parse_item_json(value: str) -> dict[str, Any]:
    payload = json.loads(value)
    if not isinstance(payload, dict):
        raise ValueError("--item-json must decode to an object")
    return payload


def item_codex_session_id(item: dict[str, Any]) -> str:
    codex = item.get("codex") if isinstance(item.get("codex"), dict) else {}
    return str(codex.get("session_id", "")).strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a Claude repair worker for one LazyCat migration queue item.")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--queue-path", default="")
    parser.add_argument("--task-root", default=DEFAULT_TASK_ROOT)
    parser.add_argument("--outbox-dir", default=DEFAULT_OUTBOX)
    parser.add_argument("--item-json", required=True)
    parser.add_argument("--box-domain", default="")
    parser.add_argument("--model", default=DEFAULT_CODEX_WORKER_MODEL)
    parser.add_argument("--no-execute", action="store_true")
    parser.add_argument(
        "--mode", default="repair", choices=["planning", "repair"],
        help="planning: pre-build, claude writes Dockerfile.template + sets build_strategy. "
             "repair (default): post-build_failed, claude diagnoses and patches.",
    )
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
        session_id=item_codex_session_id(item),
        execute=not args.no_execute,
    )
    if args.mode == "planning":
        prompt = build_planning_prompt(
            repo_root,
            item,
            queue_path=queue_path,
            box_domain=args.box_domain,
        )
    else:
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
    session_id = config.session_id.strip()
    if config.execute:
        codex_result = run_codex(config, prompt, command)
        returncode = codex_result.returncode
        session_id = codex_result.session_id or session_id
        status = "completed" if codex_result.returncode == 0 else "failed"

    notification_path = write_notification(outbox_dir, item, status=status, task_dir=task_dir, now=now)
    result = {
        "status": status,
        "returncode": returncode,
        "resumed": bool(config.session_id.strip()),
        "session_id": session_id,
        "task_dir": bundle["task_dir"],
        "notification_path": str(notification_path),
    }
    (task_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return returncode


if __name__ == "__main__":
    raise SystemExit(main())
