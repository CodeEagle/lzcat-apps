#!/usr/bin/env python3
"""File a GitHub Issue for every queue item the AI flagged needs_human.

Runs as a step in auto-discover.yml after sync. Idempotent: each slug gets at
most one open Issue. We dedupe on title, so re-runs don't spam the Issues
tab. Closing the Issue manually is the operator's signal that the candidate
has been triaged; this script does NOT reopen closed issues.

The Issue title format is::

    [needs-triage] <slug> — AI requested human verdict

State transitions on the queue side are handled by the existing
discord_human_replies / merge_discovery_review flow once the operator
provides a verdict — this script's job is purely to surface the prompt
where the operator sees it.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ISSUE_TITLE_PREFIX = "[needs-triage]"
ISSUE_LABEL = "needs-triage"


def utc_now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _gh(args: list[str]) -> tuple[int, str, str]:
    env = os.environ.copy()
    env["GH_TOKEN"] = env.get("GH_PAT") or env.get("GH_TOKEN", "")
    out = subprocess.run(["gh"] + args, capture_output=True, text=True, env=env, check=False)
    return out.returncode, out.stdout or "", out.stderr or ""


def existing_issue_titles(repo: str) -> set[str]:
    """Return the set of [needs-triage] titles currently OPEN in the repo.

    We only dedupe against open issues so that closing & reopening a
    triage cycle is possible (operator closes after verdict; if the AI
    re-flags later for a different reason, a new issue gets filed).
    """
    rc, stdout, stderr = _gh([
        "issue", "list",
        "--repo", repo,
        "--state", "open",
        "--label", ISSUE_LABEL,
        "--limit", "500",
        "--json", "title",
    ])
    if rc != 0:
        print(f"warn: gh issue list failed (rc={rc}): {stderr.strip()}", file=sys.stderr)
        return set()
    try:
        return {entry.get("title", "") for entry in json.loads(stdout) if isinstance(entry, dict)}
    except json.JSONDecodeError:
        return set()


def issue_title(slug: str) -> str:
    return f"{ISSUE_TITLE_PREFIX} {slug} — AI requested human verdict"


def issue_body(item: dict[str, Any]) -> str:
    slug = str(item.get("slug", "")).strip() or "(no slug)"
    cand = item.get("candidate") if isinstance(item.get("candidate"), dict) else {}
    review = item.get("discovery_review") if isinstance(item.get("discovery_review"), dict) else {}
    human_req = item.get("human_request") if isinstance(item.get("human_request"), dict) else {}

    repo_url = cand.get("repo_url") or item.get("source", "")
    description = cand.get("description", "").strip()
    stars = cand.get("total_stars")
    language = cand.get("language", "").strip()

    score = review.get("score")
    reason = str(review.get("reason") or "").strip()
    evidence = review.get("evidence") if isinstance(review.get("evidence"), list) else []
    question = str(human_req.get("question") or "").strip()

    lines: list[str] = [
        f"**Slug**: `{slug}`",
        f"**Upstream**: {repo_url}",
    ]
    if description:
        lines.append(f"**Description**: {description}")
    meta_bits: list[str] = []
    if language:
        meta_bits.append(f"Language: {language}")
    if stars is not None:
        meta_bits.append(f"Stars: {stars}")
    if meta_bits:
        lines.append(f"**Meta**: {' • '.join(meta_bits)}")
    lines.append("")

    lines.append("## AI verdict")
    lines.append("")
    if score is not None:
        try:
            lines.append(f"- Verdict: `needs_human` • Score **{float(score):.2f}**")
        except (TypeError, ValueError):
            lines.append("- Verdict: `needs_human`")
    else:
        lines.append("- Verdict: `needs_human`")
    if reason:
        lines.append(f"- Reason: {reason}")
    if evidence:
        lines.append("- Evidence:")
        for e in evidence[:8]:
            estr = str(e).strip()
            if estr:
                lines.append(f"  - {estr}")
    if question:
        lines.append("")
        lines.append(f"**Question for human**: {question}")
    lines.append("")
    lines.append("## How to respond")
    lines.append("")
    lines.append("Edit the queue item directly:")
    lines.append("")
    lines.append("```bash")
    lines.append(f"# To approve for migration:")
    lines.append(f"jq '(.items[] | select(.slug == \"{slug}\")).state = \"ready\"' \\")
    lines.append("    registry/auto-migration/queue.json > /tmp/q.json && \\")
    lines.append("    mv /tmp/q.json registry/auto-migration/queue.json")
    lines.append("")
    lines.append(f"# To reject:")
    lines.append(f"jq '(.items[] | select(.slug == \"{slug}\")).state = \"filtered_out\"' \\")
    lines.append("    registry/auto-migration/queue.json > /tmp/q.json && \\")
    lines.append("    mv /tmp/q.json registry/auto-migration/queue.json")
    lines.append("```")
    lines.append("")
    lines.append("Then close this issue. Sync will mirror the new state to the project board within 30 min.")
    lines.append("")
    lines.append(f"_Auto-filed by `scripts/needs_human_to_issues.py` at {utc_now_iso()}._")
    return "\n".join(lines)


def needs_human_items(queue: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in queue.get("items") or []:
        if not isinstance(item, dict):
            continue
        if item.get("state") != "waiting_for_human":
            continue
        # Already-answered items: human_response set means operator already
        # handled it; the merge_waiting_for_human flow will pick it up.
        if isinstance(item.get("human_response"), dict):
            continue
        human_req = item.get("human_request") if isinstance(item.get("human_request"), dict) else {}
        if human_req.get("kind") != "discovery_review":
            continue
        if not str(item.get("slug", "")).strip():
            continue
        out.append(item)
    return out


def file_issue(repo: str, item: dict[str, Any], *, dry_run: bool) -> tuple[bool, str]:
    slug = str(item["slug"]).strip()
    title = issue_title(slug)
    body = issue_body(item)
    if dry_run:
        return True, f"DRY-RUN would file: {title}"
    rc, stdout, stderr = _gh([
        "issue", "create",
        "--repo", repo,
        "--title", title,
        "--body", body,
        "--label", ISSUE_LABEL,
    ])
    if rc != 0:
        return False, f"gh issue create failed (rc={rc}): {stderr.strip()}"
    return True, stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--repo", default="CodeEagle/lzcat-apps", help="owner/name of the GitHub repo")
    parser.add_argument(
        "--queue-path",
        default="registry/auto-migration/queue.json",
        help="path to queue.json (relative to repo-root)",
    )
    parser.add_argument(
        "--max-issues",
        type=int,
        default=10,
        help="cap how many new issues to file per run (avoid burst-spamming)",
    )
    parser.add_argument("--dry-run", action="store_true", help="print actions without calling gh")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    queue_path = Path(args.queue_path)
    if not queue_path.is_absolute():
        queue_path = repo_root / queue_path
    if not queue_path.exists():
        print(f"queue file not found: {queue_path}", file=sys.stderr)
        return 1

    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    needs_human = needs_human_items(queue)
    if not needs_human:
        print(json.dumps({"filed": [], "skipped_existing": [], "reason": "no needs_human items"}))
        return 0

    existing = existing_issue_titles(args.repo) if not args.dry_run else set()
    filed: list[str] = []
    skipped_existing: list[str] = []
    errors: list[str] = []

    for item in needs_human:
        slug = item["slug"]
        if issue_title(slug) in existing:
            skipped_existing.append(slug)
            continue
        if len(filed) >= max(0, args.max_issues):
            break
        ok, msg = file_issue(args.repo, item, dry_run=args.dry_run)
        if ok:
            filed.append(slug)
        else:
            errors.append(f"{slug}: {msg}")

    print(json.dumps({
        "filed": filed,
        "skipped_existing": skipped_existing,
        "errors": errors,
    }, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
