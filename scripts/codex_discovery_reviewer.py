#!/usr/bin/env python3
"""Discovery review worker.

Despite the historical `codex_*` naming kept for queue.json and import
back-compat, this now invokes the Claude Code CLI (`claude --print …`) from
@anthropic-ai/claude-code rather than the OpenAI Codex CLI. Configure the
model via `migration.codex_worker_model` in project-config.json — defaults to
`claude-sonnet-4-6`.
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


DEFAULT_TASK_ROOT = "registry/auto-migration/discovery-review-tasks"
DEFAULT_OUTBOX = "registry/auto-migration/notifications"
DEFAULT_CODEX_WORKER_MODEL = "claude-sonnet-4-6"


@dataclass(frozen=True)
class DiscoveryReviewerConfig:
    repo_root: Path
    queue_path: Path
    task_dir: Path
    outbox_dir: Path | None = None
    developer_url: str = ""
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


def lazycat_store_search_guidance(item: dict[str, Any]) -> str:
    candidate = item.get("candidate") if isinstance(item.get("candidate"), dict) else {}
    hits = candidate.get("lazycat_hits") or item.get("lazycat_hits")
    if not isinstance(hits, list) or not hits:
        search = candidate.get("lazycat_store_search") if isinstance(candidate.get("lazycat_store_search"), dict) else {}
        search_hits = search.get("hits")
        hits = search_hits if isinstance(search_hits, list) else []

    if not hits:
        return (
            "No LazyCat app-store search hits are attached to this queue item. "
            "Do not infer that an app is already published unless local publication data or explicit evidence says so."
        )

    lines = [
        "This queue item includes LazyCat app-store search hits. Treat these hits as first-class evidence.",
        "If a hit is clearly the same product/app as the upstream repo, choose `skip` and cite the hit.",
        "If the match is ambiguous, weak, or depends on ownership/listing judgment, choose `needs_human`; do not guess.",
        "Do not choose `migrate` while an unresolved store hit could represent an already published app.",
        "LazyCat app-store search hits:",
    ]
    for hit in hits[:5]:
        if not isinstance(hit, dict):
            continue
        label = str(hit.get("raw_label") or hit.get("label") or "").strip()
        url = str(hit.get("detail_url") or hit.get("url") or "").strip()
        reason = str(hit.get("reason") or "").strip()
        parts = [part for part in [label, url, reason] if part]
        if parts:
            lines.append(f"- {' | '.join(parts)}")
    return "\n".join(lines)


def build_codex_prompt(
    repo_root: Path,
    queue_path: Path,
    item: dict[str, Any],
    *,
    developer_url: str = "",
) -> str:
    item_json = json.dumps(item, ensure_ascii=False, indent=2, sort_keys=True)
    publication_status = read_text_if_exists(repo_root / "registry" / "status" / "local-publication-status.json", max_chars=12000)
    latest_candidates = read_text_if_exists(repo_root / "registry" / "candidates" / "latest.json", max_chars=12000)
    local_agent_candidates = read_text_if_exists(
        repo_root / "registry" / "candidates" / "local-agent-latest.json",
        max_chars=12000,
    )
    store_search_guidance = lazycat_store_search_guidance(item)

    return f"""You are Claude, the discovery reviewer for the LazyCat lzcat-apps auto-migration pipeline.

Goal:
- Decide whether this discovery candidate should proceed to migration before any build or migration starts.
- Return exactly one decision: `migrate`, `skip`, or `needs_human`.
- Use evidence from the upstream repository, local LazyCat publication status, candidate snapshots, and the user's developer app page when available.
- Do not run the migration, do not build packages, do not submit or publish anything.

Asymmetric cost model — bias HEAVILY toward `migrate`:
- A false positive (you say `migrate`, the slug turns out non-deployable) costs ONE worker run that ends in build_failed → Blocked. Cheap, recoverable.
- A false negative (you say `skip`, the slug was actually useful) is permanent — the candidate is lost from the pipeline.
- The threshold is intentionally LOW. Reserve `skip` only for cases that match an explicit disqualifier from the list below.

What this project actually packages — broader than "native self-hosted server":
The LazyCat app-store accepts ANYTHING that can be containerized into a
web-accessible service on a user's personal cloud, including:
- Native self-hosted server apps (Vaultwarden, Nextcloud, Home Assistant, Airflow)
- CLI tools / libraries wrapped as a web service (markitdown → web converter UI; ffmpeg → media-tools UI)
- Documentation / wiki / knowledge bases served as a personal wiki (HackTricks, Awesome-* viewers)
- Terminal / TUI / desktop apps wrapped in a browser shell (Warp, ttyd-style apps)
- ML/data tools with any UI surface (DVC Studio, Jupyter-like notebooks)
- Bots, schedulers, background services with a web dashboard
- Even single-purpose utilities (URL shorteners, paste bins, file servers) regardless of star count

Step 0 — Commercial-use license check (RUN THIS FIRST, BEFORE any other decision):
LazyCat is a commercial app store; only candidates whose upstream license permits
commercial redistribution can ship there. Inspect the upstream LICENSE file (and
`license` field in package.json / Cargo.toml / pyproject.toml / go.mod when
present). Classify into:

  * COMMERCIAL-OK — proceed with normal `migrate`/`skip` evaluation:
      MIT, Apache-2.0, BSD-2-Clause, BSD-3-Clause, ISC, Unlicense, CC0, MPL-2.0,
      LGPL-2.1/3.0, GPL-2.0/3.0, AGPL-3.0 (copyleft is fine — it just propagates
      to derivative works).

  * NON-COMMERCIAL — fire `skip` immediately with:
      `state = "filtered_out"`, `filtered_reason = "non_commercial_license"`,
      `last_error = "License does not allow commercial use: <SPDX or name>"`,
      `discovery_review.status = "skip"`,
      `discovery_review.reason` MUST start with "不能商用：<license name>",
      `discovery_review.evidence` MUST cite the LICENSE file or license field.
      Common non-commercial licenses to recognize:
        - CC-BY-NC, CC-BY-NC-SA, CC-BY-NC-ND (any "NC" variant)
        - "非商用" / "Non-Commercial Use Only" / "for personal use only" clauses
        - Custom licenses with explicit "no commercial use" / "no resale" terms

  * RESTRICTIVE-BUT-COMMERCIALLY-DEPLOYABLE-CASE-BY-CASE — fire `needs_human`
    so the operator can read the specific terms before we ship:
        - SSPL (MongoDB / Elastic-style server-side license)
        - Elastic License v2 (free for end-user, restricted for hosting providers)
        - BUSL / Business Source License (time-limited non-commercial, converts
          to Apache after N years — operator must check the change date)
        - Commons Clause variants
        - Any custom license without an SPDX identifier
    Write `human_request.question` asking whether the operator's distribution
    plan complies with the upstream license terms.

  * NO LICENSE / UNLICENSED — fire `needs_human`. Distributing source without a
    license grants no rights; the operator must reach out to the upstream
    author or skip.

If Step 0 says skip or needs_human, the rest of the decision rules below are
moot — write the verdict and stop.

Decision rules (only when Step 0 says COMMERCIAL-OK):
- `migrate`: the upstream is a real software project (not abandoned spam) AND the README / description suggests there is functionality a user might want to run on their personal cloud. Stars / language / size / age do NOT disqualify. If you can imagine ANY way to wrap it into a web-accessible container, choose `migrate`.
- `skip`: ONLY when one of these EXPLICIT disqualifiers applies —
  (a) academic coursework / homework / graduation thesis with no real users
  (b) literal "template" / "skeleton" / "boilerplate" / "starter" repo
  (c) curated *list* of links (awesome-* index) — but a viewer/server FOR such lists IS migrate
  (d) "Hello World" / "test" / personal scratchpad with no description and no commits past initial
  (e) already-published in the LazyCat app store (covered by store-search hits — see below)
  (f) someone's personal homepage / résumé / blog content (not a deployable app)
  (g) blatant SaaS wrapper that ONLY works against a paid third-party API with no self-host path
  (h) the candidate is JUST a programming-language standard library, web framework (React, Vue, Express), or developer SDK, with literally NOTHING runnable as an end-user service. Caveat: many real apps' descriptions mention they're "built on Django" or "a CTF framework" or "an X framework for Y" — those are END-USER APPS that USE/PROVIDE a framework, NOT naked frameworks. dpaste (pasteboard app built on Django), ctfd (CTF competition platform), nuclio (serverless platform with dashboard) are all `migrate`. Only fire (h) when the repo is purely a library imported by other code with no service / web UI / dashboard at all.
- `needs_human`: ambiguous app-store match where the upstream MIGHT already be listed (operator should confirm). Do NOT use `needs_human` just because you're unsure about quality; default to `migrate` and let the worker confirm by attempting a build. (License-driven `needs_human` is handled in Step 0 above.)

LazyCat app-store search review:
{store_search_guidance}

Required queue update:
- Open and update this queue file: {queue_path}
- Find the item whose `id` is `{item.get("id", "")}`.
- For every decision, additionally write a numeric `discovery_review.score`
  in the closed interval [0.0, 1.0] reflecting your confidence the candidate
  is worth dispatching to a worker. The threshold is intentionally low so
  the pipeline isn't starved of work; almost every real software project
  should land above it:
    * 0.90+   confident migrate (clear app/service/wiki with active users)
    * 0.70    healthy candidate, multiple positive signals
    * 0.65    threshold for AI auto-approve (Inbox → Approved)
    * 0.55    leans migrate (has utility, partial signals) — STILL ABOVE threshold
    * 0.40    lean skip — needs an explicit disqualifier
    * 0.15-   confident skip (clear coursework / template / personal homepage / web framework)
  The score MUST be a JSON number (not a string).
- For `migrate`, set `state` to `ready`, clear `last_error` and `filtered_reason`, and write:
  `discovery_review.status = "migrate"`, `discovery_review.reviewed_at`, `discovery_review.reviewer = "claude"`,
  `discovery_review.reason`, `discovery_review.evidence` as a short list, and `discovery_review.score`.
- For `skip`, set `state` to `filtered_out`, set `filtered_reason` to `ai_discovery_skip` (override to `non_commercial_license` if the skip was driven by Step 0's license check), set `last_error` to a concise reason, and write:
  `discovery_review.status = "skip"`, `discovery_review.reviewed_at`, `discovery_review.reviewer = "claude"`,
  `discovery_review.reason`, `discovery_review.evidence`, and `discovery_review.score`.
- For `needs_human`, set `state` to `waiting_for_human` and write:
  `human_request.kind = "discovery_review"`, `human_request.question`, `human_request.options`,
  `human_request.context`, `human_request.created_at`, plus `discovery_review.status = "needs_human"`
  and `discovery_review.score`.
- If the item already has `human_response`, use that answer as user input and continue the decision.
- Preserve unrelated queue items and unrelated fields on this item.

Useful local files:
- registry/status/local-publication-status.json
- registry/status/developer-apps.json
- registry/candidates/latest.json
- registry/candidates/local-agent-latest.json
- project-config.json

Developer app page:
{developer_url or "(not configured)"}

Queue item:
```json
{item_json}
```

Local publication status excerpt:
```json
{publication_status or "{}"}
```

Latest candidate snapshot excerpt:
```json
{latest_candidates or "{}"}
```

LocalAgent candidate snapshot excerpt:
```json
{local_agent_candidates or "{}"}
```
"""


def build_codex_command(config: DiscoveryReviewerConfig) -> list[str]:
    """Build the Claude Code CLI invocation for one discovery-review session.

    Reads the prompt from stdin (subprocess `input=...`), prints the response
    to stdout (--output-format text keeps it unparsed), and bypasses the
    interactive permission prompt so the worker can run unattended in CI.
    """
    return [
        "claude",
        "--print",
        "--dangerously-skip-permissions",
        "--model",
        config.model,
        "--add-dir",
        str(config.repo_root),
        "--output-format",
        "text",
    ]


def write_task_bundle(
    config: DiscoveryReviewerConfig,
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
                "queue_path": str(config.queue_path),
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
    path = outbox_dir / f"{now.replace(':', '').replace('-', '')}-{safe_task_name(str(item.get('id', 'unknown')))}-discovery.md"
    path.write_text(
        "\n".join(
            [
                f"# Claude discovery reviewer {status}",
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


def run_codex(config: DiscoveryReviewerConfig, prompt: str, command: list[str]) -> int:
    stdout_path = config.task_dir / "claude.stdout.log"
    stderr_path = config.task_dir / "claude.stderr.log"
    result = subprocess.run(command, input=prompt, text=True, capture_output=True, check=False)
    stdout_path.write_text(result.stdout or "", encoding="utf-8")
    stderr_path.write_text(result.stderr or "", encoding="utf-8")
    return result.returncode


def parse_item_json(value: str) -> dict[str, Any]:
    payload = json.loads(value)
    if not isinstance(payload, dict):
        raise ValueError("--item-json must decode to an object")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a Claude reviewer for one discovery_review queue item.")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--queue-path", required=True)
    parser.add_argument("--item-id", required=True)
    parser.add_argument("--item-json", required=True)
    parser.add_argument("--task-root", default=DEFAULT_TASK_ROOT)
    parser.add_argument("--outbox-dir", default=DEFAULT_OUTBOX)
    parser.add_argument("--developer-url", default="")
    parser.add_argument("--model", default=DEFAULT_CODEX_WORKER_MODEL)
    parser.add_argument("--no-execute", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    queue_path = Path(args.queue_path)
    if not queue_path.is_absolute():
        queue_path = repo_root / queue_path
    item = parse_item_json(args.item_json)
    now = utc_now_iso()
    task_root = Path(args.task_root)
    if not task_root.is_absolute():
        task_root = repo_root / task_root
    outbox_dir = Path(args.outbox_dir)
    if not outbox_dir.is_absolute():
        outbox_dir = repo_root / outbox_dir
    task_dir = task_root / f"{now.replace(':', '').replace('-', '')}-{safe_task_name(str(args.item_id))}"
    config = DiscoveryReviewerConfig(
        repo_root=repo_root,
        queue_path=queue_path,
        task_dir=task_dir,
        outbox_dir=outbox_dir,
        developer_url=args.developer_url,
        model=args.model,
        execute=not args.no_execute,
    )
    prompt = build_codex_prompt(repo_root, queue_path, item, developer_url=args.developer_url)
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

    # Append the verdict to the cross-cycle audit log so periodic review of
    # AI calibration is possible. The reviewer writes its decision back into
    # queue.json (queue_path), so we read it out to capture model/score.
    try:
        from ai_review_log import append_review
    except ImportError:  # pragma: no cover
        from .ai_review_log import append_review  # type: ignore[no-redef]
    review = _read_back_discovery_verdict(queue_path, args.item_id)
    append_review(
        repo_root,
        reviewer="discovery",
        slug=str(item.get("slug", "")).strip(),
        item_id=args.item_id,
        model=config.model,
        verdict=str(review.get("status") or ""),
        score=review.get("score"),
        reason=str(review.get("reason") or ""),
        evidence=review.get("evidence") if isinstance(review.get("evidence"), list) else None,
        task_dir=str(task_dir),
        returncode=returncode,
        ts=now,
        extra={"source": str(item.get("source") or "")},
    )

    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return returncode


def _read_back_discovery_verdict(queue_path: Path, item_id: str) -> dict[str, Any]:
    """Pull the discovery_review object Claude wrote back for this item."""
    try:
        payload = json.loads(queue_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return {}
    target = item_id.strip()
    for entry in items:
        if isinstance(entry, dict) and str(entry.get("id", "")).strip() == target:
            review = entry.get("discovery_review")
            return review if isinstance(review, dict) else {}
    return {}


if __name__ == "__main__":
    raise SystemExit(main())
