#!/usr/bin/env python3
"""Mirror queue items' ``state_history`` to per-slug GitHub Issues.

For every queue item that has any state-history entries, this script
ensures a tracking GitHub Issue exists (one issue per slug, reused
across the lifetime of the migration) and posts each unposted
``state_history[]`` entry as a comment on it.

Wired into auto-discover.yml as a final step after sync, so every
30-minute cron flushes the latest cycle's state changes onto the
slug's tracking issue. Idempotent — re-runs post nothing new.

Per-item bookkeeping (saved back into queue.json):

  * ``github_issue_number``        — the tracking issue's #
  * ``state_history_posted_count`` — how many ``state_history[]``
                                     entries have already been posted

So the diff to post on each run is simply
``state_history[posted_count:]``.

Title format:        ``[migration] <slug>``
Label:               ``migration`` (auto-created if missing — the
                     current ``needs-triage`` label is for a
                     different audit channel)
Body:                lightweight summary + pointers to queue.json
                     and state-history.jsonl

Failure-tolerant: any single-slug error is recorded in the run
summary but does not abort the whole batch.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ISSUE_TITLE_PREFIX = "[migration]"
ISSUE_LABEL = "migration"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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
    lines.append("Migration timeline tracker. State changes auto-post as comments below.")
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


def process_item(repo: str, item: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
    slug = str(item.get("slug", "")).strip()
    history = item.get("state_history") or []
    if not isinstance(history, list) or not history:
        return {"slug": slug, "skipped": "no history"}

    posted = int(item.get("state_history_posted_count") or 0)
    new_entries = history[posted:]
    if not new_entries:
        return {"slug": slug, "skipped": "no new entries"}

    issue_number = item.get("github_issue_number")
    if not isinstance(issue_number, int):
        existing = find_existing_issue(repo, issue_title(slug))
        if existing:
            issue_number = existing
        else:
            if dry_run:
                return {"slug": slug, "would_create": True, "would_post": len(new_entries)}
            issue_number = create_issue(repo, item)
            if issue_number is None:
                return {"slug": slug, "error": "create issue failed"}
        item["github_issue_number"] = issue_number

    if dry_run:
        return {"slug": slug, "would_post_to": issue_number, "count": len(new_entries)}

    posted_now = 0
    for entry in new_entries:
        if not isinstance(entry, dict):
            continue
        body = comment_body(entry, item)
        if add_comment(repo, issue_number, body):
            posted_now += 1
        else:
            break

    item["state_history_posted_count"] = posted + posted_now
    return {"slug": slug, "issue": issue_number, "posted": posted_now, "remaining": len(new_entries) - posted_now}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--repo", default="CodeEagle/lzcat-apps")
    parser.add_argument("--queue-path", default="registry/auto-migration/queue.json")
    parser.add_argument("--max-slugs-per-run", type=int, default=20,
                        help="Cap how many slugs to process per invocation; "
                             "tail keeps catching up on subsequent crons. Avoids "
                             "rate-limiting GitHub when state-history.jsonl is "
                             "first turned on across thousands of historical items.")
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
        history = item.get("state_history") or []
        if not isinstance(history, list) or not history:
            continue
        posted = int(item.get("state_history_posted_count") or 0)
        if posted >= len(history):
            continue
        result = process_item(args.repo, item, dry_run=args.dry_run)
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
