from __future__ import annotations

from typing import Any

try:
    from .publication_status import normalize_repo
except ImportError:  # pragma: no cover - direct script execution
    from publication_status import normalize_repo


FILTERED_CANDIDATE_STATUSES = {"already_migrated", "excluded"}
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
    item["state"] = "filtered_out"
    item["candidate_status"] = "already_migrated" if reason in {"published_upstream", "candidate_already_migrated"} else "excluded"
    item["last_error"] = last_error
    item["filtered_reason"] = reason
    item["updated_at"] = now
    item.pop("human_request", None)
    item.pop("human_response", None)


def _mark_discovery_review(item: dict[str, Any], *, now: str) -> None:
    candidate = _candidate(item)
    source = str(item.get("source") or candidate.get("full_name") or "").strip()
    repo_url = str(candidate.get("repo_url", "")).strip()
    reason = str(candidate.get("status_reason") or "Needs AI discovery review").strip()
    item["state"] = "discovery_review"
    item["candidate_status"] = "needs_review"
    item["discovery_review"] = {
        "created_at": now,
        "status": "pending",
        "prompt": (
            "判断是否值得迁移这个 LazyCat 候选项目。"
            f"\n上游：{source}"
            f"\n仓库：{repo_url}"
            f"\n发现原因：{reason}"
            "\n请判断：migrate / skip / needs_human，并给出证据。"
        ),
    }
    item["updated_at"] = now


def reconcile_queue_items(
    queue: dict[str, Any],
    *,
    publication_index: dict[str, dict[str, Any]],
    now: str,
) -> list[dict[str, str]]:
    changes: list[dict[str, str]] = []
    for item in _items(queue):
        state = str(item.get("state", "")).strip()
        if state not in RECONCILABLE_STATES:
            continue

        status = _candidate_status(item)
        if status == "already_migrated":
            if state == "filtered_out" and item.get("filtered_reason") == "candidate_already_migrated":
                continue
            _mark_filtered(
                item,
                now=now,
                reason="candidate_already_migrated",
                last_error=_candidate_reason(item) or "Candidate is already migrated according to discovery evidence.",
            )
            changes.append({"id": str(item.get("id", "")).strip(), "status": "filtered_out", "reason": "candidate_already_migrated"})
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
            _mark_discovery_review(item, now=now)
            changes.append({"id": str(item.get("id", "")).strip(), "status": "discovery_review", "reason": "needs_ai_review"})
    return changes
