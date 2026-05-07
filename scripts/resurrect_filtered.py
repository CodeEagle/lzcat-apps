#!/usr/bin/env python3
"""Send qualifying filtered_out items back to discovery_review.

When the AI reviewer's prompt or the discovery gate's mechanical filters
get tightened or loosened, the existing filtered_out backlog is now
mis-classified by the new policy. This script resets the subset that the
NEW policy would likely re-evaluate, leaving the rest untouched.

What gets reset (idempotent — safe to re-run):
  * filtered_reason == "ai_discovery_skip"
      Old AI prompt rejected; new prompt is more permissive.
  * filtered_reason == "candidate_excluded" AND status_reason starts with
    "Likely not a deployable self-hosted app/service"
      Mechanical gate's old definition was strict ("native server only");
      new prompt accepts CLI / wiki / TUI wrappers.

What stays filtered:
  * filtered_reason == "candidate_already_migrated_by_other" / "published_upstream"
      Real upstream-already-published evidence.
  * filtered_reason == "slug_excluded"
      Operator-curated exclude list.
  * filtered_reason == "candidate_excluded" with status_reason like
    "No incentive: PKM/VPN/short-link/..."
      Operator-curated "not interested in this category" — preference,
      not a quality judgment.

Side effects on each reset item:
  * state              → discovery_review
  * candidate_status   → needs_review
  * codex_attempts     → 0 (force AI to re-evaluate)
  * last_status        → cleared
  * last_error         → cleared
  * filtered_reason    → cleared
  * discovery_review.{prompt, created_at} → re-initialized
  * resurrected_at     → now (audit trail)
  * resurrected_from_reason → original filtered_reason (audit trail)
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    from .state_history import record_state_transition
except ImportError:  # pragma: no cover - direct script execution
    from state_history import record_state_transition


RESET_REASONS_DIRECT = {"ai_discovery_skip"}
EXCLUDED_PROMPT_PREFIX_RESET = "Likely not a deployable self-hosted app/service"


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def should_reset(item: dict[str, Any]) -> tuple[bool, str]:
    """Return (reset?, audit reason)."""
    reason = str(item.get("filtered_reason") or "").strip()
    if reason in RESET_REASONS_DIRECT:
        return True, reason
    if reason == "candidate_excluded":
        cand = item.get("candidate") if isinstance(item.get("candidate"), dict) else {}
        status_reason = str(cand.get("status_reason") or "").strip()
        if status_reason.startswith(EXCLUDED_PROMPT_PREFIX_RESET):
            return True, "candidate_excluded:not_deployable"
    return False, ""


def reset_item(item: dict[str, Any], *, now: str) -> None:
    audit_reason = item.get("filtered_reason") or "unknown"
    cand = item.get("candidate") if isinstance(item.get("candidate"), dict) else {}
    candidate_repo = str(cand.get("full_name") or item.get("source") or "")
    repo_url = str(cand.get("repo_url") or "")

    item["candidate_status"] = "needs_review"
    item["resurrected_at"] = now
    item["resurrected_from_reason"] = audit_reason
    item.pop("filtered_reason", None)
    item.pop("last_error", None)
    item.pop("human_request", None)
    item.pop("human_response", None)
    record_state_transition(
        item,
        "discovery_review",
        reason=f"resurrected from filtered_out: {audit_reason}",
        source="resurrect_filtered",
        now=now,
    )

    review = item.get("discovery_review") if isinstance(item.get("discovery_review"), dict) else {}
    review["codex_attempts"] = 0
    review.pop("last_status", None)
    review.pop("last_returncode", None)
    review.pop("last_run_at", None)
    review["created_at"] = now
    review["status"] = "pending"
    review["prompt"] = (
        "Re-evaluate this LazyCat candidate under the new (more permissive) "
        "discovery prompt. Old verdict was: "
        f"{audit_reason}.\n上游：{candidate_repo}\n仓库：{repo_url}\n"
        "请按新规则重新判断 migrate / skip / needs_human 并给分。"
    )
    item["discovery_review"] = review


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--queue-path", default="registry/auto-migration/queue.json")
    parser.add_argument("--dry-run", action="store_true", help="Print plan without writing.")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    queue_path = Path(args.queue_path)
    if not queue_path.is_absolute():
        queue_path = repo_root / queue_path
    if not queue_path.exists():
        print(f"queue file not found: {queue_path}", file=sys.stderr)
        return 1

    payload = json.loads(queue_path.read_text(encoding="utf-8"))
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    now = utc_now_iso()

    reset_count = 0
    audit = Counter()
    sample: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("state") != "filtered_out":
            continue
        ok, audit_reason = should_reset(item)
        if not ok:
            continue
        if not args.dry_run:
            reset_item(item, now=now)
        reset_count += 1
        audit[audit_reason] += 1
        if len(sample) < 12:
            sample.append(f"{item.get('slug')}({audit_reason})")

    if not args.dry_run:
        queue_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    summary = {
        "dry_run": bool(args.dry_run),
        "reset_count": reset_count,
        "by_reason": dict(audit),
        "sample": sample,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
