#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


STORE_SEARCH_REVIEW_STATUSES = {"portable", "needs_review"}
DEFAULT_STORE_SEARCH_LIMIT = 50
DEFAULT_STORE_SEARCH_TTL_SECONDS = 24 * 60 * 60
StoreSearcher = Callable[[dict[str, Any]], dict[str, Any]]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_utc_iso(value: str) -> datetime | None:
    raw = value.strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp_path.replace(path)


def github_full_name_from_url(url: str) -> str:
    value = url.strip().rstrip("/").removesuffix(".git")
    if "github.com/" not in value:
        return ""
    return value.rsplit("github.com/", 1)[-1].strip("/")


def normalize_local_agent_candidate(project: dict[str, Any], *, origin: str) -> dict[str, Any] | None:
    full_name = str(project.get("full_name", "")).strip()
    repo_url = str(project.get("repo_url", "")).strip()
    if not full_name and repo_url:
        full_name = github_full_name_from_url(repo_url)
    if not full_name:
        owner = str(project.get("owner", "")).strip()
        repo = str(project.get("repo", "")).strip()
        if owner and repo:
            full_name = f"{owner}/{repo}"
    if "/" not in full_name:
        return None

    owner, repo = full_name.split("/", 1)
    if not repo_url:
        repo_url = f"https://github.com/{full_name}"

    status = str(project.get("status", "")).strip().lower()
    if not status:
        status = "needs_review" if origin == "external_sources" else "portable"
    if status == "already_migrated":
        status = "already_migrated_by_other"

    candidate = {
        "full_name": full_name,
        "owner": str(project.get("owner") or owner).strip(),
        "repo": str(project.get("repo") or repo).strip(),
        "repo_url": repo_url,
        "description": str(project.get("description", "")).strip(),
        "language": str(project.get("language", "")).strip(),
        "stars_today": int(project.get("stars_today") or 0),
        "total_stars": int(project.get("total_stars") or 0),
        "status": status,
        "status_reason": str(project.get("status_reason", "")).strip(),
        "sources": project.get("sources") if isinstance(project.get("sources"), list) else [],
        "source_labels": project.get("source_labels") if isinstance(project.get("source_labels"), list) else [],
        "external_signal": str(project.get("external_signal", "")).strip(),
        "external_url": str(project.get("external_url", "")).strip(),
        "discovery_source": "local_agent",
        "local_agent": {
            "origin": origin,
            "first_seen_at": str(project.get("first_seen_at", "")).strip(),
            "last_seen_at": str(project.get("last_seen_at", "")).strip(),
            "last_checked_at": str(project.get("last_checked_at", "")).strip(),
            "manual_decision": str(project.get("manual_decision", "")).strip(),
        },
    }
    return candidate


def local_agent_candidate_cache_key(candidate: dict[str, Any]) -> str:
    full_name = str(candidate.get("full_name", "")).strip().lower()
    if full_name:
        return f"github:{full_name}"
    repo_url = str(candidate.get("repo_url", "")).strip().rstrip("/").removesuffix(".git")
    if "github.com/" in repo_url:
        repo_url = repo_url.rsplit("github.com/", 1)[-1]
    return f"github:{repo_url.lower()}" if repo_url else ""


def candidate_store_search_repo(candidate: dict[str, Any]) -> dict[str, Any]:
    full_name = str(candidate.get("full_name", "")).strip()
    owner = str(candidate.get("owner", "")).strip()
    repo = str(candidate.get("repo", "")).strip()
    if full_name and "/" in full_name and (not owner or not repo):
        owner, repo = full_name.split("/", 1)
    return {
        "source_name": "local_agent",
        "source_label": "LocalAgent",
        "owner": owner,
        "repo": repo,
        "full_name": full_name,
        "repo_url": str(candidate.get("repo_url", "")).strip() or (f"https://github.com/{full_name}" if full_name else ""),
        "description": str(candidate.get("description", "")).strip(),
        "language": str(candidate.get("language", "")).strip(),
        "total_stars": int(candidate.get("total_stars") or 0),
        "stars_today": int(candidate.get("stars_today") or 0),
    }


def load_store_search_cache(cache_path: Path | None) -> dict[str, Any]:
    if cache_path is None:
        return {"schema_version": 1, "items": {}}
    cache = read_json(cache_path, {"schema_version": 1, "items": {}})
    if not isinstance(cache.get("items"), dict):
        cache["items"] = {}
    cache["schema_version"] = 1
    return cache


def is_store_search_cache_fresh(cached: dict[str, Any], *, now: str, ttl_seconds: int) -> bool:
    if ttl_seconds < 0:
        return True
    reviewed_at = parse_utc_iso(str(cached.get("reviewed_at", "")))
    current = parse_utc_iso(now)
    if reviewed_at is None or current is None:
        return False
    return (current - reviewed_at).total_seconds() <= ttl_seconds


def default_store_searcher(repo: dict[str, Any]) -> dict[str, Any]:
    try:
        from .scout_core import search_lazycat
    except ImportError:  # pragma: no cover - direct script execution
        from scout_core import search_lazycat

    return search_lazycat(repo)


def normalize_store_search_result(payload: dict[str, Any]) -> dict[str, Any]:
    searches = payload.get("searches") if isinstance(payload.get("searches"), list) else []
    hits = payload.get("hits") if isinstance(payload.get("hits"), list) else []
    errors = payload.get("errors") if isinstance(payload.get("errors"), list) else []
    status = str(payload.get("status") or ("needs_review" if hits or errors else "portable")).strip() or "portable"
    reason = str(payload.get("reason") or "").strip()
    if not reason:
        reason = (
            "LazyCat app-store search returned matches; AI discovery review required."
            if hits
            else "No matching app found in LazyCat app store search."
        )
    return {
        "status": status,
        "reason": reason,
        "searches": searches,
        "hits": hits,
        "errors": errors,
    }


def apply_store_search_result(candidate: dict[str, Any], result: dict[str, Any], *, now: str) -> None:
    normalized = normalize_store_search_result(result)
    hits = normalized["hits"]
    candidate["lazycat_store_search"] = {
        "status": normalized["status"],
        "reason": normalized["reason"],
        "searches": normalized["searches"],
        "hits": hits,
        "errors": normalized["errors"],
        "reviewed_at": now,
    }
    candidate["searches"] = normalized["searches"]
    candidate["lazycat_hits"] = hits
    if normalized["errors"]:
        candidate["search_errors"] = normalized["errors"]

    if hits:
        evidence = [
            f"{str(hit.get('raw_label', '')).strip()} {str(hit.get('detail_url', '')).strip()}".strip()
            for hit in hits[:5]
            if isinstance(hit, dict)
        ]
        candidate["status"] = "needs_review"
        candidate["status_reason"] = "LazyCat app-store search returned matches; AI discovery review required."
        candidate["ai_store_review"] = {
            "status": "pending",
            "source": "lazycat_store_search",
            "created_at": now,
            "reason": "懒猫商店搜索有命中，需要 Codex 基于搜索结果判断是否已上架。",
            "evidence": evidence,
        }
        return

    if normalized["status"] == "portable":
        candidate["status"] = "portable"
        candidate["status_reason"] = normalized["reason"]


def apply_store_search_reviews(
    candidates: list[dict[str, Any]],
    *,
    now: str,
    cache_path: Path | None = None,
    store_searcher: StoreSearcher | None = None,
    limit: int = DEFAULT_STORE_SEARCH_LIMIT,
    ttl_seconds: int = DEFAULT_STORE_SEARCH_TTL_SECONDS,
) -> dict[str, int]:
    searcher = store_searcher or default_store_searcher
    cache = load_store_search_cache(cache_path)
    cache_items = cache["items"]
    reviewed = 0
    cache_hits = 0
    refreshed = 0
    matched = 0
    errors = 0

    for candidate in candidates:
        status = str(candidate.get("status", "")).strip().lower()
        if status not in STORE_SEARCH_REVIEW_STATUSES:
            continue
        key = local_agent_candidate_cache_key(candidate)
        if not key:
            continue
        cached = cache_items.get(key)
        if (
            isinstance(cached, dict)
            and isinstance(cached.get("search_result"), dict)
            and is_store_search_cache_fresh(cached, now=now, ttl_seconds=ttl_seconds)
        ):
            result = normalize_store_search_result(cached["search_result"])
            cache_hits += 1
        else:
            if reviewed >= max(0, limit):
                continue
            if isinstance(cached, dict):
                refreshed += 1
            try:
                result = normalize_store_search_result(searcher(candidate_store_search_repo(candidate)))
            except Exception as exc:  # pragma: no cover - exact network failure varies.
                result = {
                    "status": "needs_review",
                    "reason": "Search failed for one or more terms; manual review required.",
                    "searches": [],
                    "hits": [],
                    "errors": [str(exc)],
                }
                errors += 1
            cache_items[key] = {
                "full_name": candidate.get("full_name", ""),
                "repo_url": candidate.get("repo_url", ""),
                "reviewed_at": now,
                "search_result": result,
            }
            reviewed += 1
        apply_store_search_result(candidate, result, now=now)
        if result.get("hits"):
            matched += 1

    if cache_path is not None and reviewed:
        write_json(cache_path, cache)
    return {"reviewed": reviewed, "cache_hits": cache_hits, "refreshed": refreshed, "matched": matched, "errors": errors}


def build_local_agent_snapshot(
    local_agent_root: Path,
    *,
    now: str | None = None,
    enable_store_search: bool = False,
    store_searcher: StoreSearcher | None = None,
    store_search_cache_path: Path | None = None,
    store_search_limit: int = DEFAULT_STORE_SEARCH_LIMIT,
    store_search_ttl_seconds: int = DEFAULT_STORE_SEARCH_TTL_SECONDS,
) -> dict[str, Any]:
    now = now or utc_now_iso()
    data_dir = local_agent_root / "data"
    state = read_json(data_dir / "state.json", {"projects": {}})
    external = read_json(data_dir / "external_sources.json", {"candidates": []})

    candidates_by_name: dict[str, dict[str, Any]] = {}
    projects = state.get("projects") if isinstance(state.get("projects"), dict) else {}
    for project in projects.values():
        if not isinstance(project, dict):
            continue
        candidate = normalize_local_agent_candidate(project, origin="state.projects")
        if candidate:
            candidates_by_name[candidate["full_name"].lower()] = candidate

    external_candidates = external.get("candidates") if isinstance(external.get("candidates"), list) else []
    for project in external_candidates:
        if not isinstance(project, dict):
            continue
        candidate = normalize_local_agent_candidate(project, origin="external_sources")
        if candidate:
            candidates_by_name.setdefault(candidate["full_name"].lower(), candidate)

    candidates = sorted(
        candidates_by_name.values(),
        key=lambda item: (-int(item.get("stars_today") or 0), -int(item.get("total_stars") or 0), item["full_name"].lower()),
    )
    store_search_review = (
        apply_store_search_reviews(
            candidates,
            now=now,
            cache_path=store_search_cache_path,
            store_searcher=store_searcher,
            limit=store_search_limit,
            ttl_seconds=store_search_ttl_seconds,
        )
        if enable_store_search
        else {"reviewed": 0, "cache_hits": 0, "refreshed": 0, "matched": 0, "errors": 0}
    )
    return {
        "meta": {
            "schema_version": 1,
            "source": "local_agent",
            "generated_at": now,
            "local_agent_root": str(local_agent_root),
            "candidate_count": len(candidates),
            "store_search_review": store_search_review,
        },
        "candidates": candidates,
    }


def write_local_agent_snapshot(
    local_agent_root: Path,
    output_path: Path,
    *,
    now: str | None = None,
    enable_store_search: bool = False,
    store_searcher: StoreSearcher | None = None,
    store_search_cache_path: Path | None = None,
    store_search_limit: int = DEFAULT_STORE_SEARCH_LIMIT,
    store_search_ttl_seconds: int = DEFAULT_STORE_SEARCH_TTL_SECONDS,
) -> dict[str, Any]:
    snapshot = build_local_agent_snapshot(
        local_agent_root,
        now=now,
        enable_store_search=enable_store_search,
        store_searcher=store_searcher,
        store_search_cache_path=store_search_cache_path,
        store_search_limit=store_search_limit,
        store_search_ttl_seconds=store_search_ttl_seconds,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    temp_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp_path.replace(output_path)
    return snapshot


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import LocalAgent candidates into lzcat-apps candidate snapshot format.")
    parser.add_argument("--local-agent-root", required=True)
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    snapshot = write_local_agent_snapshot(Path(args.local_agent_root).expanduser().resolve(), Path(args.output).expanduser())
    print(json.dumps(snapshot["meta"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
