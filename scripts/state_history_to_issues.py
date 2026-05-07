#!/usr/bin/env python3
"""Mirror the full migration record of each queue item to per-slug GitHub Issues.

For every queue item that has any recorded migration activity, this
script ensures a tracking GitHub Issue exists (one issue per slug,
reused across the lifetime of the migration) and posts every unposted
process artifact as a comment on it. The goal is that the issue's
comment timeline is the human-readable, append-only record of the
entire migration — everything the automation did, every AI verdict,
every codex run, every state transition, every error.

Sources mirrored to comments (all idempotent — each artifact is posted
exactly once and tracked via a dedicated bookkeeping field):

  1. ``state_history[]``               — state transitions
  2. ``discovery_review`` block        — AI's discovery verdict, with
                                         prompt + reason + evidence + score
  3. ``codex.last_run_at``             — outcome of the latest codex run
                                         (rc, status, task_dir)
  4. ``last_error``                    — newest error string seen on
                                         the item
  5. ``ai-reviews.jsonl`` (per-slug)   — every audited AI review for the
                                         slug (discovery, verify, preempt …)

Wired into auto-discover.yml as a final step after sync, so every
30-minute cron flushes the latest cycle's artifacts onto each slug's
tracking issue. Idempotent — re-runs post nothing new.

Per-item bookkeeping (saved back into queue.json):

  * ``github_issue_number``         — the tracking issue's #
  * ``state_history_posted_count``  — how many ``state_history[]``
                                      entries have already been posted
  * ``discovery_review_posted_at``  — last posted ``reviewed_at`` value
  * ``codex_run_posted_at``         — last posted ``codex.last_run_at``
  * ``last_error_posted_hash``      — sha1 of last posted ``last_error``
  * ``ai_reviews_posted_count``     — how many ai-reviews.jsonl entries
                                      for this slug have been posted

Title format:        ``[migration] <slug>``
Label:               ``migration`` (auto-created if missing — the
                     current ``needs-triage`` label is for a
                     different audit channel)
Body:                lightweight summary + pointers to queue.json,
                     state-history.jsonl, ai-reviews.jsonl

Failure-tolerant: any single-slug error is recorded in the run
summary but does not abort the whole batch.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ISSUE_TITLE_PREFIX = "[migration]"
ISSUE_LABEL = "migration"
DEFAULT_AI_REVIEWS_PATH = Path("registry/auto-migration/ai-reviews.jsonl")


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _gh(args: list[str], *, input: str | None = None) -> tuple[int, str, str]:
    env = os.environ.copy()
    env["GH_TOKEN"] = env.get("GH_PAT") or env.get("GH_TOKEN", "")
    out = subprocess.run(
        ["gh"] + args,
        capture_output=True, text=True, check=False, env=env, input=input,
    )
    return out.returncode, out.stdout or "", out.stderr or ""


def issue_title(slug: str) -> str:
    return f"{ISSUE_TITLE_PREFIX} {slug}"


def issue_body(item: dict[str, Any]) -> str:
    slug = str(item.get("slug", "")).strip() or "(no slug)"
    cand = item.get("candidate") if isinstance(item.get("candidate"), dict) else {}
    repo_url = cand.get("repo_url") or item.get("source", "")
    description = cand.get("description", "").strip()
    lines = [
        f"**Slug**: `{slug}`",
        f"**Upstream**: {repo_url}",
    ]
    if description:
        lines.append(f"**Description**: {description}")
    lines.append("")
    lines.append(
        "Migration timeline tracker. State changes, AI reviews, codex runs "
        "and errors auto-post as comments below."
    )
    lines.append("")
    lines.append("References:")
    lines.append("- queue: `registry/auto-migration/queue.json` (search by slug)")
    lines.append("- audit log: `registry/auto-migration/state-history.jsonl`")
    lines.append("- AI reviews: `registry/auto-migration/ai-reviews.jsonl`")
    lines.append("")
    lines.append(f"_Auto-created by `scripts/state_history_to_issues.py` at {utc_now_iso()}._")
    return "\n".join(lines)


def comment_body(entry: dict[str, Any], item: dict[str, Any]) -> str:
    src = str(entry.get("from") or "—").strip() or "—"
    dst = str(entry.get("to") or "?").strip() or "?"
    via = str(entry.get("source") or "").strip()
    ts = str(entry.get("ts") or "").strip()
    reason = str(entry.get("reason") or "").strip()
    run_id = str(entry.get("run_id") or "").strip()

    lines = [f"### `{src}` → `{dst}`"]
    meta = []
    if via:
        meta.append(f"via `{via}`")
    if ts:
        meta.append(f"@ {ts}")
    if run_id:
        meta.append(
            f"[run #{run_id}](https://github.com/CodeEagle/lzcat-apps/actions/runs/{run_id})"
        )
    if meta:
        lines.append(" • ".join(meta))
    lines.append("")
    if reason:
        lines.append(reason)
    lines.append("")

    # Compact context block
    details = []
    attempts = item.get("attempts")
    if attempts is not None:
        details.append(f"- attempts: `{attempts}`")
    last_error = str(item.get("last_error") or "").strip()
    if last_error:
        details.append(f"- last_error: `{last_error[:300]}`")
    review = item.get("discovery_review") if isinstance(item.get("discovery_review"), dict) else None
    if isinstance(review, dict):
        verdict = str(review.get("status") or "").strip()
        score = review.get("score")
        if verdict:
            details.append(f"- AI verdict: `{verdict}`" + (f" (score `{score}`)" if score is not None else ""))
    if details:
        lines.append("<details><summary>context</summary>")
        lines.append("")
        lines.extend(details)
        lines.append("")
        lines.append("</details>")
    return "\n".join(lines)


def discovery_review_comment_body(review: dict[str, Any]) -> str:
    """Render the AI's discovery verdict (status / score / reason / evidence)."""
    status = str(review.get("status") or "?").strip() or "?"
    reviewer = str(review.get("reviewer") or "").strip()
    score = review.get("score")
    reviewed_at = str(review.get("reviewed_at") or "").strip()
    reason = str(review.get("reason") or "").strip()
    evidence = review.get("evidence") if isinstance(review.get("evidence"), list) else []
    prompt = str(review.get("prompt") or "").strip()

    score_str = f" (score `{score}`)" if score is not None else ""
    lines = [f"### Discovery Review → `{status}`{score_str}"]
    meta = []
    if reviewer:
        meta.append(f"reviewer: `{reviewer}`")
    if reviewed_at:
        meta.append(f"@ {reviewed_at}")
    if meta:
        lines.append(" • ".join(meta))
    lines.append("")
    if reason:
        lines.append(reason)
        lines.append("")
    if evidence:
        lines.append("**Evidence:**")
        for e in evidence:
            lines.append(f"- {str(e).strip()}")
        lines.append("")
    if prompt:
        lines.append("<details><summary>prompt</summary>")
        lines.append("")
        lines.append("```")
        lines.append(prompt[:2000])
        lines.append("```")
        lines.append("")
        lines.append("</details>")
    return "\n".join(lines).rstrip() + "\n"


def codex_run_comment_body(codex: dict[str, Any], item: dict[str, Any]) -> str:
    """Render the latest codex worker run (status / rc / task_dir)."""
    status = str(codex.get("last_status") or "?").strip() or "?"
    rc = codex.get("last_returncode")
    run_at = str(codex.get("last_run_at") or "").strip()
    attempts = codex.get("attempts")
    task_dir = str(codex.get("last_task_dir") or "").strip()
    session_id = str(codex.get("session_id") or "").strip()

    rc_str = f" (rc=`{rc}`)" if rc is not None else ""
    lines = [f"### Codex Run → `{status}`{rc_str}"]
    meta = []
    if attempts is not None:
        meta.append(f"attempt `{attempts}`")
    if run_at:
        meta.append(f"@ {run_at}")
    if meta:
        lines.append(" • ".join(meta))
    lines.append("")
    details = []
    if task_dir:
        details.append(f"- task_dir: `{task_dir}`")
    if session_id:
        details.append(f"- session_id: `{session_id}`")
    last_error = str(item.get("last_error") or "").strip()
    if last_error and rc is not None and int(rc) != 0:
        details.append(f"- last_error: `{last_error[:300]}`")
    if details:
        lines.extend(details)
    return "\n".join(lines).rstrip() + "\n"


def last_error_comment_body(item: dict[str, Any]) -> str:
    """Render the current ``last_error`` payload as a fenced block."""
    err = str(item.get("last_error") or "").strip()
    state = str(item.get("state") or "?").strip() or "?"
    updated_at = str(item.get("updated_at") or "").strip()
    lines = [f"### Error in state `{state}`"]
    if updated_at:
        lines.append(f"@ {updated_at}")
    lines.append("")
    lines.append("```")
    lines.append(err[:4000])
    lines.append("```")
    return "\n".join(lines).rstrip() + "\n"


def ai_review_comment_body(entry: dict[str, Any]) -> str:
    """Render one ``ai-reviews.jsonl`` row (any reviewer kind)."""
    reviewer = str(entry.get("reviewer") or "?").strip() or "?"
    verdict = str(entry.get("verdict") or "?").strip() or "?"
    score = entry.get("score")
    ts = str(entry.get("ts") or "").strip()
    model = str(entry.get("model") or "").strip()
    reason = str(entry.get("reason") or "").strip()
    evidence = entry.get("evidence") if isinstance(entry.get("evidence"), list) else []
    task_dir = str(entry.get("task_dir") or "").strip()
    rc = entry.get("returncode")

    score_str = f" (score `{score}`)" if score is not None else ""
    lines = [f"### AI Review · `{reviewer}` → `{verdict}`{score_str}"]
    meta = []
    if model:
        meta.append(f"model: `{model}`")
    if ts:
        meta.append(f"@ {ts}")
    if rc is not None:
        meta.append(f"rc=`{rc}`")
    if meta:
        lines.append(" • ".join(meta))
    lines.append("")
    if reason:
        lines.append(reason)
        lines.append("")
    if evidence:
        lines.append("**Evidence:**")
        for e in evidence:
            lines.append(f"- {str(e).strip()}")
        lines.append("")
    if task_dir:
        lines.append(f"<sub>task_dir: `{task_dir}`</sub>")
    return "\n".join(lines).rstrip() + "\n"


def load_ai_reviews_by_slug(path: Path) -> dict[str, list[dict[str, Any]]]:
    """Group ``ai-reviews.jsonl`` rows by slug, sorted by ``ts`` ascending.

    Returns an empty dict if the file is missing — the AI-reviews channel
    is optional, callers should still post the other artifact kinds.
    """
    if not path.exists():
        return {}
    by_slug: dict[str, list[dict[str, Any]]] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError:
            continue
        slug = str(entry.get("slug") or "").strip()
        if not slug:
            continue
        by_slug.setdefault(slug, []).append(entry)
    for entries in by_slug.values():
        entries.sort(key=lambda e: str(e.get("ts") or ""))
    return by_slug


def find_existing_issue(repo: str, title: str) -> int | None:
    """Look up an open issue by exact title; returns its number or None."""
    rc, stdout, _ = _gh([
        "issue", "list",
        "--repo", repo,
        "--state", "all",
        "--search", f'"{title}" in:title',
        "--limit", "5",
        "--json", "number,title",
    ])
    if rc != 0:
        return None
    try:
        rows = json.loads(stdout)
    except json.JSONDecodeError:
        return None
    for row in rows:
        if isinstance(row, dict) and row.get("title", "").strip() == title:
            n = row.get("number")
            if isinstance(n, int):
                return n
    return None


def ensure_label(repo: str, label: str) -> None:
    """Create the `migration` label idempotently — gh label create exits
    rc=1 if the label exists; we swallow that.
    """
    _gh([
        "label", "create", label,
        "--repo", repo,
        "--description", "Per-slug migration tracker (state_history → issue comments)",
        "--color", "5319E7",
    ])


def create_issue(repo: str, item: dict[str, Any]) -> int | None:
    slug = str(item.get("slug", "")).strip()
    title = issue_title(slug)
    body = issue_body(item)
    rc, stdout, stderr = _gh([
        "issue", "create",
        "--repo", repo,
        "--title", title,
        "--body", body,
        "--label", ISSUE_LABEL,
    ])
    if rc != 0:
        print(f"warn: issue create {slug!r} failed (rc={rc}): {stderr.strip()}", file=sys.stderr)
        return None
    # gh issue create prints the issue URL on success; extract the number.
    last_line = (stdout.strip().splitlines() or [""])[-1]
    if "/issues/" in last_line:
        try:
            return int(last_line.rsplit("/", 1)[-1])
        except ValueError:
            return None
    return None


def add_comment(repo: str, issue_number: int, body: str) -> bool:
    rc, _, stderr = _gh(
        ["issue", "comment", str(issue_number), "--repo", repo, "--body-file", "-"],
        input=body,
    )
    if rc != 0:
        print(f"warn: comment on #{issue_number} failed (rc={rc}): {stderr.strip()}", file=sys.stderr)
        return False
    return True


def _collect_unposted_artifacts(
    item: dict[str, Any],
    ai_reviews_for_slug: list[dict[str, Any]],
) -> list[tuple[str, str, str, Any]]:
    """Walk every mirrored source on ``item`` and return unposted artifacts.

    Each artifact is a tuple ``(kind, ts, body, marker)`` where ``marker`` is
    the value to write into the corresponding bookkeeping field after the
    comment has been successfully posted (see ``_apply_marker``). The list
    is sorted by ``ts`` so the comment timeline reads chronologically.
    """
    artifacts: list[tuple[str, str, str, Any]] = []

    # 1. state_history diff — every transition since posted_count
    history = item.get("state_history") or []
    if isinstance(history, list):
        posted = int(item.get("state_history_posted_count") or 0)
        for i, entry in enumerate(history[posted:], start=posted):
            if not isinstance(entry, dict):
                continue
            ts = str(entry.get("ts") or "")
            body = comment_body(entry, item)
            artifacts.append(("state_history", ts, body, i + 1))

    # 2. discovery_review — post once per ``reviewed_at`` value
    review = item.get("discovery_review")
    if isinstance(review, dict):
        reviewed_at = str(review.get("reviewed_at") or "").strip()
        if reviewed_at and reviewed_at != str(item.get("discovery_review_posted_at") or "").strip():
            body = discovery_review_comment_body(review)
            artifacts.append(("discovery_review", reviewed_at, body, reviewed_at))

    # 3. codex run — post once per ``codex.last_run_at`` value
    codex = item.get("codex")
    if isinstance(codex, dict):
        last_run_at = str(codex.get("last_run_at") or "").strip()
        if last_run_at and last_run_at != str(item.get("codex_run_posted_at") or "").strip():
            body = codex_run_comment_body(codex, item)
            artifacts.append(("codex_run", last_run_at, body, last_run_at))

    # 4. last_error — post once per distinct error string (sha1 fingerprint)
    last_error = str(item.get("last_error") or "").strip()
    if last_error:
        h = hashlib.sha1(last_error.encode("utf-8", errors="replace")).hexdigest()
        if h != str(item.get("last_error_posted_hash") or "").strip():
            body = last_error_comment_body(item)
            ts = str(item.get("updated_at") or "")
            artifacts.append(("last_error", ts, body, h))

    # 5. ai-reviews.jsonl — every audited AI verdict for this slug
    posted_count = int(item.get("ai_reviews_posted_count") or 0)
    for i, entry in enumerate(ai_reviews_for_slug[posted_count:], start=posted_count):
        if not isinstance(entry, dict):
            continue
        ts = str(entry.get("ts") or "")
        body = ai_review_comment_body(entry)
        artifacts.append(("ai_review", ts, body, i + 1))

    artifacts.sort(key=lambda a: a[1] or "")
    return artifacts


def _apply_marker(item: dict[str, Any], kind: str, marker: Any) -> None:
    """Persist the ``marker`` for ``kind`` so the artifact isn't re-posted."""
    if kind == "state_history":
        cur = int(item.get("state_history_posted_count") or 0)
        item["state_history_posted_count"] = max(cur, int(marker))
    elif kind == "discovery_review":
        item["discovery_review_posted_at"] = str(marker)
    elif kind == "codex_run":
        item["codex_run_posted_at"] = str(marker)
    elif kind == "last_error":
        item["last_error_posted_hash"] = str(marker)
    elif kind == "ai_review":
        cur = int(item.get("ai_reviews_posted_count") or 0)
        item["ai_reviews_posted_count"] = max(cur, int(marker))


def _has_any_known_artifact(
    item: dict[str, Any],
    ai_reviews_for_slug: list[dict[str, Any]],
) -> bool:
    """True if the item carries at least one artifact source we know how to mirror."""
    if isinstance(item.get("state_history"), list) and item["state_history"]:
        return True
    if isinstance(item.get("discovery_review"), dict):
        if str(item["discovery_review"].get("reviewed_at") or "").strip():
            return True
    if isinstance(item.get("codex"), dict):
        if str(item["codex"].get("last_run_at") or "").strip():
            return True
    if str(item.get("last_error") or "").strip():
        return True
    if ai_reviews_for_slug:
        return True
    return False


def process_item(
    repo: str,
    item: dict[str, Any],
    *,
    dry_run: bool,
    ai_reviews_for_slug: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    slug = str(item.get("slug", "")).strip()
    ai_reviews_for_slug = ai_reviews_for_slug or []

    # Preserve original "no history" skip semantics: when the item has
    # *literally nothing* worth mirroring yet (no state_history, no
    # discovery_review, no codex run, no error, no ai-reviews row), we
    # don't even create an issue for it.
    if not _has_any_known_artifact(item, ai_reviews_for_slug):
        return {"slug": slug, "skipped": "no history"}

    artifacts = _collect_unposted_artifacts(item, ai_reviews_for_slug)
    if not artifacts:
        return {"slug": slug, "skipped": "no new entries"}

    issue_number = item.get("github_issue_number")
    if not isinstance(issue_number, int):
        existing = find_existing_issue(repo, issue_title(slug))
        if existing:
            issue_number = existing
        else:
            if dry_run:
                return {"slug": slug, "would_create": True, "would_post": len(artifacts)}
            issue_number = create_issue(repo, item)
            if issue_number is None:
                return {"slug": slug, "error": "create issue failed"}
        item["github_issue_number"] = issue_number

    if dry_run:
        return {"slug": slug, "would_post_to": issue_number, "count": len(artifacts)}

    posted_now = 0
    kinds: dict[str, int] = {}
    for kind, _ts, body, marker in artifacts:
        if not add_comment(repo, issue_number, body):
            break
        _apply_marker(item, kind, marker)
        posted_now += 1
        kinds[kind] = kinds.get(kind, 0) + 1

    return {
        "slug": slug,
        "issue": issue_number,
        "posted": posted_now,
        "remaining": len(artifacts) - posted_now,
        "kinds": kinds,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--repo", default="CodeEagle/lzcat-apps")
    parser.add_argument("--queue-path", default="registry/auto-migration/queue.json")
    parser.add_argument("--ai-reviews-path", default=str(DEFAULT_AI_REVIEWS_PATH),
                        help="Path (relative to --repo-root, or absolute) of "
                             "the ai-reviews.jsonl audit log to mirror per-slug.")
    parser.add_argument("--max-slugs-per-run", type=int, default=20,
                        help="Cap how many slugs to process per invocation; "
                             "tail keeps catching up on subsequent crons. Avoids "
                             "rate-limiting GitHub when the artifact backlog "
                             "is first turned on across thousands of historical items.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print intended actions without calling gh.")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    queue_path = Path(args.queue_path)
    if not queue_path.is_absolute():
        queue_path = repo_root / queue_path
    if not queue_path.exists():
        print(f"queue file not found: {queue_path}", file=sys.stderr)
        return 1

    ai_reviews_path = Path(args.ai_reviews_path)
    if not ai_reviews_path.is_absolute():
        ai_reviews_path = repo_root / ai_reviews_path
    ai_reviews_index = load_ai_reviews_by_slug(ai_reviews_path)

    if not args.dry_run:
        ensure_label(args.repo, ISSUE_LABEL)

    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    items = queue.get("items") or []
    summary: list[dict[str, Any]] = []
    processed = 0
    queue_dirty = False

    for item in items:
        if processed >= args.max_slugs_per_run:
            break
        if not isinstance(item, dict):
            continue
        slug = str(item.get("slug") or "").strip()
        ai_reviews_for_slug = ai_reviews_index.get(slug, [])
        if not _has_any_known_artifact(item, ai_reviews_for_slug):
            continue
        artifacts = _collect_unposted_artifacts(item, ai_reviews_for_slug)
        if not artifacts:
            continue
        result = process_item(
            args.repo, item,
            dry_run=args.dry_run,
            ai_reviews_for_slug=ai_reviews_for_slug,
        )
        summary.append(result)
        processed += 1
        if not args.dry_run and result.get("posted"):
            queue_dirty = True
        if not args.dry_run and "github_issue_number" in item:
            queue_dirty = True

    if queue_dirty:
        # Atomic write — never half-write under a concurrent reader.
        tmp = queue_path.with_suffix(queue_path.suffix + ".tmp")
        tmp.write_text(json.dumps(queue, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, queue_path)

    print(json.dumps({"processed": processed, "results": summary}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
