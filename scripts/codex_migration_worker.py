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
from datetime import datetime, timezone
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
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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
    """Pre-build planning prompt — claude reads SKILL.md and pre-fills
    apps/<slug>/ with everything the build phase needs (manifest, build
    config, Dockerfile.template) before the mechanical build chain
    runs. Together with build_codex_prompt (post-failure repair) they
    bracket the mechanical phase.

    The prompt is intentionally short — it points claude at the
    authoritative SOP (skills/lazycat-migrate/SKILL.md, 35 KB, 10-step
    playbook) and lets claude read it directly via --add-dir. We only
    inline the inputs claude can't fetch herself (live license, live
    source-code signals) and the things specific to the planning
    phase.
    """
    slug = str(item.get("slug", "")).strip()
    app_dir = repo_root / "apps" / slug if slug else repo_root / "apps"
    item_json = json.dumps(item, ensure_ascii=False, indent=2, sort_keys=True)
    candidate = item.get("candidate") if isinstance(item.get("candidate"), dict) else {}
    full_name = str(candidate.get("full_name") or item.get("source") or "").strip()
    repo_url = str(candidate.get("repo_url") or "").strip()
    description = str(candidate.get("description") or "").strip()
    if repo_signals is None:
        repo_signals = fetch_repo_signals(item)
    if license_info is None:
        license_info = fetch_license_info(item)
    repo_signals_block = format_repo_signals_block(repo_signals)
    license_block = format_license_block(license_info)
    manifest = read_text_if_exists(app_dir / "lzc-manifest.yml", max_chars=4000)
    build_yml = read_text_if_exists(app_dir / "lzc-build.yml", max_chars=2000)
    readme = read_text_if_exists(app_dir / "README.md", max_chars=4000)

    return f"""You are Claude, the migration planner for LazyCat lzcat-apps.

# Task

Migrate the upstream project end-to-end:
- Slug: `{slug}`
- Upstream: {full_name} ({repo_url})
- Description: {description}

# Authoritative SOP — read FIRST and follow EXACTLY

`@skills/lazycat-migrate/SKILL.md` — 35 KB, 10-step playbook covering
the full closed loop: 上游研判 → 注册/建骨架 → 预检 → 构建 → 下载 .lpk
→ 安装验收 → bb-browser 功能验证 → 商店上架 → 复盘回写.

The skill file enumerates non-negotiable defaults (账号 `CodeEagle`、
分支策略、registry/repos 接入方式、login 免密路线、Browser Use 验收
门槛、商店上架前的真实截图要求 …). Do NOT reinvent them — read
SKILL.md, follow it.

# Phase you're in: PLANNING (pre-build)

The mechanical build chain runs **immediately after you exit**, so
your job here is to pre-fill `apps/{slug}/` with everything the build
phase needs:

  * `lzc-manifest.yml` — real ports / services / data paths / env
    vars / login route — NO placeholders. Per SKILL.md `[5/10]`,
    must be filled in one pass after producing the "上游部署清单".
    **Service image rules** (critical for multi-service apps):
      - For services WE BUILD from upstream source (the primary app),
        use `image: registry.lazycat.cloud/placeholder/{slug}:bootstrap`.
        run_build.py swaps this with the real built image at packaging
        time and writes `image_targets` accordingly.
      - For SIDECAR services WE DO NOT BUILD (databases, caches, queue
        backends — mongo / postgres / redis / mariadb / mysql /
        rabbitmq / minio / elasticsearch / etc.), use the official
        registry image directly (e.g. `image: mongo:7`,
        `image: postgres:16-alpine`, `image: redis:7-alpine`,
        `image: mariadb:10.11`). NEVER point a sidecar at the
        `placeholder/{slug}:bootstrap` URI — apply_image_overrides
        will then try to swap mongo with our built app image and
        the install crashes. Observed in resumeai run 25531579892:
        planner pointed both `mongo` and `web` at the placeholder;
        even with manifest preserved, image_targets ended up with
        a mongo entry that has no Dockerfile to build.
  * `lzc-build.yml` — set the right `build_strategy` (one of
    `official_image` / `upstream_dockerfile` /
    `upstream_with_target_template` / `precompiled_binary`).
  * `Dockerfile.template` — write only when strategy is
    `upstream_with_target_template`. Multi-stage when upstream
    builds to a binary; pick the right base image (rust:1-slim,
    node:20-slim, python:3.12-slim, golang:1.22-alpine).
  * `README.md`, `icon.png` — bootstrap_migration may have written
    placeholders; update if obviously wrong.
  * `registry/repos/{slug}.json` — registry/repos/index.json
    membership; usually already there from earlier scaffold but
    verify.

Don't run any build, install, lzc-cli, or commit/push. The
orchestrator handles all of that. Your write surface is
`apps/{slug}/` only (per SKILL.md rule 5 — script over manual,
your manual edits get superseded if they belong in
`scripts/full_migrate.py`).

# Downstream phases (for context — DO NOT execute, just be aware)

Once you exit:

  1. **build phase** (this same worker run): full_migrate.py +
     run_build.py compile your Dockerfile.template into images,
     pkg into `.lpk`, push to GHCR, install to the configured
     LazyCat box.

  2. **bb-browser verification** (`auto-verify.yml`, separate
     workflow that auto-fires on this worker's success): the
     `lzcat-bb-browser` image runs `browser_acceptance_plan.py` +
     `browser_acceptance_runner.py` against the live install URL.
     SKILL.md rule 12 — install success ≠ acceptance. Browser Use
     clicks through the functional matrix and captures real
     screenshots.

  3. **store submission** (`auto-publish.yml`, human-triggered
     after Awaiting-Human passes): `prepare_store_submission.py`
     packages the screenshots + copy and opens a PR. SKILL.md
     rule 13 — screenshots MUST come from the running install,
     not designs / placeholders.

If you anticipate any of these phases will fail (e.g. the app
needs login but no 免密 route is configured, or no published
image and source isn't buildable), surface it now in the manifest /
Dockerfile.template / queue waiting_for_human field rather than
letting it explode later.

# Hard guardrails (a few critical ones — see SKILL.md for full)

- Account: SKILL.md rule 1 — `gh auth switch -u CodeEagle` before
  any `gh` command.
- Single-source: SKILL.md rule 3 — push everything in
  `CodeEagle/lzcat-apps` monorepo; do NOT spawn standalone repos
  unless the user explicitly asks.
- Branch hygiene: SKILL.md rule 14 — never merge to main before
  store submission completes (or user explicitly approves merge).
- Workflow-only build: SKILL.md rule 15 — local
  `./scripts/local_build.sh` is forbidden for canonical build;
  production builds happen in GitHub Workflows.
- License: if upstream license is missing or non-commercial, set
  the queue item to `waiting_for_human` with a
  `human_request.question` asking the operator before continuing —
  don't assume.

# Repository facts

- repo_root: {repo_root}
- queue_path: {queue_path or "(not provided)"}
- box_domain: {box_domain or "(not configured)"}
- app_dir: {app_dir}

# Inputs already gathered

Upstream license:
{license_block}

Upstream source-code signals (live-fetched):
{repo_signals_block}

Existing scaffolded files:

`apps/{slug}/lzc-manifest.yml`:
```yaml
{manifest or "(missing — bootstrap_migration has not run yet)"}
```

`apps/{slug}/lzc-build.yml`:
```yaml
{build_yml or "(missing)"}
```

`apps/{slug}/README.md` (first 4 KB):
```markdown
{readme or "(missing)"}
```

# Queue item

```json
{item_json}
```

# Output

When done, print a short summary:
- which build_strategy you chose
- which files you wrote / modified
- key decisions you made about ports / login / data paths
- any waiting_for_human / blockers you flagged

If the existing scaffolding already looks correct (e.g. another
operator pre-filled it), exit cleanly with:
`PLANNER: skipped — existing scaffolding looks correct`.
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


def run_codex(
    config: CodexWorkerConfig,
    prompt: str,
    command: list[str],
    *,
    slug: str = "",
    mode: str = "",
) -> CodexRunResult:
    """Invoke claude --print and capture stdout/stderr.

    Logs go two places:
      1. <task_dir>/claude.std{out,err}.log — canonical, but the
         task_dir lives under registry/auto-migration/codex-tasks/
         which is gitignored. Lost when the runner shuts down.
      2. apps/<slug>/.last-claude-{mode}.{stdout,stderr}.log when
         slug+mode are provided — survives worker.yml's WIP commit
         (which scopes to apps/<slug>/) so the operator can post-
         mortem debug a planner / repair failure right from the
         migration branch. Truncated to 64 KB each.
    """
    stdout_path = config.task_dir / "claude.stdout.log"
    stderr_path = config.task_dir / "claude.stderr.log"
    result = subprocess.run(command, input=prompt, text=True, capture_output=True, check=False)
    stdout_path.write_text(result.stdout or "", encoding="utf-8")
    stderr_path.write_text(result.stderr or "", encoding="utf-8")

    if slug and mode:
        app_dir = config.repo_root / "apps" / slug
        try:
            app_dir.mkdir(parents=True, exist_ok=True)
            cap = 64 * 1024
            stdout_tail = (result.stdout or "")[-cap:]
            stderr_tail = (result.stderr or "")[-cap:]
            (app_dir / f".last-claude-{mode}.stdout.log").write_text(stdout_tail, encoding="utf-8")
            (app_dir / f".last-claude-{mode}.stderr.log").write_text(stderr_tail, encoding="utf-8")
        except OSError:
            pass

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
    # Planning mode must always start a fresh claude session. The
    # repair-mode session_id stored in `item.codex.session_id` belongs
    # to a completely different prompt (post-build_failed repair) and
    # could be hours/days old; resuming it from a planning prompt
    # confuses claude (it sees the resumed conversation, not the new
    # planning task) and causes silent rc=1 exits with no file edits.
    # Observed in stellaclaw runs 25491577249 / 25492174092 /
    # 25492751352 — every planning run resumed a 12-hour-old repair
    # session and produced nothing.
    session_id = item_codex_session_id(item) if args.mode == "repair" else ""
    config = CodexWorkerConfig(
        repo_root=repo_root,
        task_dir=task_dir,
        outbox_dir=outbox_dir,
        box_domain=args.box_domain,
        model=args.model,
        session_id=session_id,
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
        codex_result = run_codex(
            config, prompt, command,
            slug=str(item.get("slug", "")).strip(),
            mode=args.mode,
        )
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
