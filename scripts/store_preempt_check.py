#!/usr/bin/env python3
"""Pre-migration recheck: has someone else published this slug to the LazyCat
App Store while it was waiting in the Approved column?

Approved → In-Progress can sit for hours/days while the dispatcher works
through the queue. Another developer could ship the same upstream to the
store in that window. This script re-runs the lazycat search ONE more time
right before the migration cycle starts, and bails with abort code if a
strong match is found (mechanical) or if Claude says the hits represent the
same product (ambiguous case).

Usage:
  python3 scripts/store_preempt_check.py <slug>

Exit codes:
  0  proceed — store is clear or hits don't match this product
  3  abort — already published; worker should mark Filtered and stop
  1  soft fail — couldn't determine (network error, no queue entry, etc).
     Caller should treat as proceed-with-caution.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ai_review_log import append_review  # noqa: E402
from scout_core import classify_search_hits, search_lazycat  # noqa: E402

DEFAULT_QUEUE_PATH = "registry/auto-migration/queue.json"
DEFAULT_MODEL = "claude-sonnet-4-6"


def _find_item(queue_path: Path, slug: str) -> dict[str, Any] | None:
    if not queue_path.exists():
        return None
    payload = json.loads(queue_path.read_text(encoding="utf-8"))
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return None
    target = slug.strip()
    for it in items:
        if isinstance(it, dict) and str(it.get("slug", "")).strip() == target:
            return it
    return None


def _repo_payload_from_item(item: dict[str, Any]) -> dict[str, Any]:
    candidate = item.get("candidate") if isinstance(item.get("candidate"), dict) else {}
    full_name = (candidate.get("full_name") or item.get("source") or "").strip()
    if "/" in full_name:
        owner, repo = full_name.split("/", 1)
    else:
        owner = candidate.get("owner") or ""
        repo = candidate.get("repo") or item.get("slug") or full_name
    return {
        "owner": owner.strip(),
        "repo": repo.strip(),
        "full_name": full_name,
        "repo_url": (candidate.get("repo_url") or f"https://github.com/{full_name}").strip(),
        "description": str(candidate.get("description") or "").strip(),
    }


def _claude_says_preempted(repo: dict[str, Any], hits: list[dict[str, str]], *, model: str) -> bool:
    """Ask claude: do any of these hits represent THIS exact product?

    Falls back to "not preempted" on any error so we don't block work on
    network hiccups.
    """
    if not hits:
        return False
    prompt = f"""You are a fast preempt-check reviewer for the LazyCat
auto-migration pipeline. The candidate is about to be migrated; we
re-searched the LazyCat App Store and got the matches below. Your only
question: is ANY of these matches actually the same product as the
upstream? If yes, the migration is preempted (someone else already shipped
it) and we should abort. If matches are similar-named but different
products, we proceed.

Reply with ONE JSON object only, no prose, no code fences:
  {{"preempted": true|false, "match": "<store-slug-or-empty>", "reason": "<≤30 words>"}}

Upstream:
- repo: {repo.get('full_name', '')}
- url: {repo.get('repo_url', '')}
- description: {repo.get('description', '')[:400]}

LazyCat App Store hits (label + URL):
""" + "\n".join(
        f"- {h.get('raw_label','')} | {h.get('detail_url','')}" for h in hits[:25]
    ) + "\n\nReply with the JSON now."

    try:
        cmd = [
            "claude",
            "--print",
            "--dangerously-skip-permissions",
            "--model",
            model,
            "--output-format",
            "text",
        ]
        proc = subprocess.run(cmd, input=prompt, text=True, capture_output=True, check=False, timeout=120)
        if proc.returncode != 0:
            return False
        match = re.search(r"\{.*\}", proc.stdout or "", re.DOTALL)
        if not match:
            return False
        payload = json.loads(match.group(0))
        return bool(payload.get("preempted"))
    except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError, OSError):
        return False


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("slug")
    p.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    p.add_argument("--queue-path", default=DEFAULT_QUEUE_PATH)
    p.add_argument("--model", default=os.environ.get("LZCAT_PREEMPT_MODEL", DEFAULT_MODEL))
    p.add_argument(
        "--no-ai",
        action="store_true",
        help="Skip the Claude verification on ambiguous hits; mechanical only.",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    queue_path = Path(args.queue_path)
    if not queue_path.is_absolute():
        queue_path = repo_root / queue_path

    item = _find_item(queue_path, args.slug)
    if item is None:
        print(f"store_preempt_check: queue entry not found for slug={args.slug!r}", file=sys.stderr)
        return 1

    repo = _repo_payload_from_item(item)
    if not repo["repo"]:
        print(f"store_preempt_check: queue entry has no repo info for slug={args.slug!r}", file=sys.stderr)
        return 1

    try:
        result = search_lazycat(repo)
    except Exception as exc:  # network / parser failure — proceed-with-caution
        print(f"store_preempt_check: search failed: {exc}", file=sys.stderr)
        return 1

    hits = result.get("hits", [])
    status = result.get("status", "portable")

    summary = {
        "slug": args.slug,
        "search_status": status,
        "hit_count": len(hits),
        "first_hits": [h.get("raw_label", "") for h in hits[:5]],
        "search_reason": result.get("reason", ""),
    }

    def _log(decision: str, model: str = "", reason: str = "", verdict: str = "") -> None:
        # Every preempt-check decision lands in ai-reviews.jsonl so we can
        # later answer "why did slug X get filtered right before migration?".
        append_review(
            repo_root,
            reviewer="preempt",
            slug=args.slug,
            item_id=str(item.get("id", "")),
            model=model,
            verdict=verdict or decision,
            score=None,
            reason=reason or result.get("reason", ""),
            evidence=[h.get("raw_label", "") for h in hits[:5]],
            task_dir="",
            returncode=0,
            extra={
                "search_status": status,
                "hit_count": len(hits),
                "first_hit_urls": [h.get("detail_url", "") for h in hits[:5]],
                "decision": decision,
                "upstream": repo.get("repo_url", ""),
            },
        )

    if status == "already_migrated":
        # Mechanical strong-match: hit label matches repo name.
        summary["decision"] = "abort"
        summary["abort_reason"] = "mechanical_strong_match"
        _log("abort", reason=result.get("reason", ""), verdict="preempted")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 3

    if status == "needs_review" and hits and not args.no_ai:
        if _claude_says_preempted(repo, hits, model=args.model):
            summary["decision"] = "abort"
            summary["abort_reason"] = "claude_preempt_verdict"
            _log("abort", model=args.model, verdict="preempted",
                 reason="claude says one of the store hits is the same product")
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return 3

    summary["decision"] = "proceed"
    _log("proceed", verdict="clear")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
