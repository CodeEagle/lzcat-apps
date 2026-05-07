from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    from .publication_status import normalize_repo
    from .state_history import record_state_transition
except ImportError:  # pragma: no cover - direct script execution
    from publication_status import normalize_repo
    from state_history import record_state_transition


FILTERED_CANDIDATE_STATUSES = {"already_migrated", "already_migrated_by_other", "excluded"}
MIGRATED_PUBLICATION_STATUSES = {"published", "migrated"}
RECONCILABLE_STATES = {
    "ready",
    "build_failed",
    "browser_failed",
    "codex_failed",
    "filtered_out",
    "waiting_for_human",
    "discovery_review",
}

EXCLUDE_LIST_PATH = "registry/auto-migration/exclude-list.json"


def load_exclude_slugs(repo_root: Path) -> set[str]:
    path = repo_root / EXCLUDE_LIST_PATH
    if not path.exists():
        return set()
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw = payload.get("slugs") if isinstance(payload, dict) else None
    if not isinstance(raw, list):
        return set()
    return {str(s).strip() for s in raw if str(s).strip()}


def _items(queue: dict[str, Any]) -> list[dict[str, Any]]:
    items = queue.get("items")
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _candidate(item: dict[str, Any]) -> dict[str, Any]:
    candidate = item.get("candidate")
    return candidate if isinstance(candidate, dict) else {}


def _candidate_status(item: dict[str, Any]) -> str:
    return str(item.get("candidate_status") or _candidate(item).get("status") or "").strip().lower()


def _has_committed_verdict(item: dict[str, Any]) -> bool:
    """True when the AI reviewer (or operator) has already issued a final
    verdict on the item.

    discovery_gate.reconcile_queue_items uses this to skip the
    "needs_review → discovery_review" demotion path. Without it, items
    promoted past discovery_review (state=ready / scaffolded / etc.)
    get bounced back to discovery_review every cycle because their
    ``candidate_status`` field still reads "needs_review" from scout —
    a known foot-gun that re-demoted stellaclaw, cosmos-server, and
    every other AI-promoted ready item.
    """
    review = item.get("discovery_review")
    if not isinstance(review, dict):
        return False
    status = str(review.get("status") or "").strip().lower()
    return status in {"migrate", "skip", "needs_human"}


def _candidate_reason(item: dict[str, Any]) -> str:
    return str(_candidate(item).get("status_reason") or item.get("last_error") or "").strip()


def _source_repos(item: dict[str, Any]) -> list[str]:
    repos: list[str] = []
    candidate = _candidate(item)
    for value in [
        item.get("source"),
        candidate.get("full_name"),
        candidate.get("repo_url"),
    ]:
        text = str(value or "").strip().rstrip("/").removesuffix(".git")
        if not text:
            continue
        if "github.com/" in text:
            text = text.rsplit("github.com/", 1)[-1]
        normalized = normalize_repo(text)
        if "/" in normalized and normalized not in repos:
            repos.append(normalized)
    return repos


def _publication_match(item: dict[str, Any], publication_index: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    by_upstream_repo = publication_index.get("by_upstream_repo", {})
    if isinstance(by_upstream_repo, dict):
        for repo in _source_repos(item):
            record = by_upstream_repo.get(repo)
            if isinstance(record, dict):
                return record

    by_slug = publication_index.get("by_slug", {})
    slug = str(item.get("slug", "")).strip()
    if isinstance(by_slug, dict) and slug:
        record = by_slug.get(slug)
        if isinstance(record, dict):
            return record
    return None


def _mark_filtered(item: dict[str, Any], *, now: str, reason: str, last_error: str) -> None:
    item["candidate_status"] = (
        "already_migrated_by_other"
        if reason in {"published_upstream", "candidate_already_migrated", "candidate_already_migrated_by_other"}
        else "excluded"
    )
    item["last_error"] = last_error
    item["filtered_reason"] = reason
    item.pop("human_request", None)
    item.pop("human_response", None)
    record_state_transition(
        item,
        "filtered_out",
        reason=f"discovery_gate:{reason}: {last_error}".strip(": "),
        source="discovery_gate.filter",
        now=now,
    )


def _mark_discovery_review(item: dict[str, Any], *, now: str) -> None:
    candidate = _candidate(item)
    source = str(item.get("source") or candidate.get("full_name") or "").strip()
    repo_url = str(candidate.get("repo_url", "")).strip()
    reason = str(candidate.get("status_reason") or "Needs AI discovery review").strip()
    store_hit_lines = _store_hit_prompt_lines(candidate)
    item["candidate_status"] = "needs_review"
    item["discovery_review"] = {
        "created_at": now,
        "status": "pending",
        "prompt": (
            "判断是否值得迁移这个 LazyCat 候选项目。"
            f"\n上游：{source}"
            f"\n仓库：{repo_url}"
            f"\n发现原因：{reason}"
            + ("\n" + "\n".join(store_hit_lines) if store_hit_lines else "")
            + "\n请判断：migrate / skip / needs_human，并给出证据。"
        ),
    }
    record_state_transition(
        item,
        "discovery_review",
        reason=f"queued for AI review: {reason}",
        source="discovery_gate.queue",
        now=now,
    )


def _store_hit_prompt_lines(candidate: dict[str, Any]) -> list[str]:
    hits = candidate.get("lazycat_hits")
    if not isinstance(hits, list) or not hits:
        return []
    lines = [
        "懒猫商店搜索命中：",
        "请只基于这些商店搜索结果和上游信息判断是否已经上架；命中不明确时选 needs_human，不要猜。",
    ]
    for hit in hits[:5]:
        if not isinstance(hit, dict):
            continue
        label = str(hit.get("raw_label", "")).strip()
        detail_url = str(hit.get("detail_url", "")).strip()
        lines.append(f"- {label} {detail_url}".strip())
    return lines


def reconcile_queue_items(
    queue: dict[str, Any],
    *,
    publication_index: dict[str, dict[str, Any]],
    now: str,
    exclude_slugs: set[str] | None = None,
) -> list[dict[str, str]]:
    excluded = exclude_slugs or set()
    changes: list[dict[str, str]] = []
    for item in _items(queue):
        state = str(item.get("state", "")).strip()
        if state not in RECONCILABLE_STATES:
            continue

        slug = str(item.get("slug", "")).strip()
        if slug and slug in excluded:
            if state == "filtered_out" and item.get("filtered_reason") == "slug_excluded":
                continue
            _mark_filtered(
                item,
                now=now,
                reason="slug_excluded",
                last_error=f"Slug {slug!r} is in registry/auto-migration/exclude-list.json",
            )
            changes.append({"id": str(item.get("id", "")).strip(), "status": "filtered_out", "reason": "slug_excluded"})
            continue

        status = _candidate_status(item)
        if status in {"already_migrated", "already_migrated_by_other"}:
            reason = "candidate_already_migrated_by_other" if status == "already_migrated_by_other" else "candidate_already_migrated"
            if state == "filtered_out" and item.get("filtered_reason") == reason:
                continue
            _mark_filtered(
                item,
                now=now,
                reason=reason,
                last_error=_candidate_reason(item) or "Candidate is already migrated according to discovery evidence.",
            )
            changes.append({"id": str(item.get("id", "")).strip(), "status": "filtered_out", "reason": reason})
            continue
        if status == "excluded":
            if state == "filtered_out" and item.get("filtered_reason") == "candidate_excluded":
                continue
            _mark_filtered(
                item,
                now=now,
                reason="candidate_excluded",
                last_error=_candidate_reason(item) or "Candidate is excluded by discovery evidence.",
            )
            changes.append({"id": str(item.get("id", "")).strip(), "status": "filtered_out", "reason": "candidate_excluded"})
            continue

        match = _publication_match(item, publication_index)
        if match:
            publication_status = str(match.get("publication_status", "")).strip().lower()
            if publication_status in MIGRATED_PUBLICATION_STATUSES:
                if state == "filtered_out" and item.get("filtered_reason") == "published_upstream":
                    continue
                label = str(match.get("store_label") or match.get("name") or match.get("slug") or "").strip()
                _mark_filtered(
                    item,
                    now=now,
                    reason="published_upstream",
                    last_error=f"Published app found for upstream repo: {label}".strip(),
                )
                changes.append({"id": str(item.get("id", "")).strip(), "status": "filtered_out", "reason": "published_upstream"})
                continue

        if state == "filtered_out" and item.get("filtered_reason") == "ai_discovery_skip":
            continue

        if status == "needs_review" and (state != "discovery_review" or not isinstance(item.get("discovery_review"), dict)):
            # Critical: don't demote items the AI (or operator) has
            # already passed a verdict on. Without this guard, every
            # promoted-to-ready item gets bounced back to
            # discovery_review every cycle because scout's
            # candidate_status="needs_review" persists on the item
            # forever — this re-demoted stellaclaw / cosmos-server
            # and broke the entire E2E flow.
            if _has_committed_verdict(item):
                continue
            _mark_discovery_review(item, now=now)
            changes.append({"id": str(item.get("id", "")).strip(), "status": "discovery_review", "reason": "needs_ai_review"})
    return changes
