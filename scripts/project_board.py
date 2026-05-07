#!/usr/bin/env python3
"""GitHub Projects v2 wrapper for the auto-migration pipeline.

Subcommands:
  bootstrap          Find or create the Project, ensure the 10 schema fields,
                     cache node IDs.
  sync               Reconcile registry/auto-migration/queue.json -> Project items.
                     Items whose discovery_review.score >= threshold are promoted
                     Inbox -> Approved. Excluded slugs are skipped (or moved to
                     Filtered if already on the board).
  list-approved      Print up to N approved slugs (text or JSON) for matrix.
  read <slug>        Print all fields, or one field with --field.
  update <slug>      Mutate Status (--status) and/or arbitrary fields (--field k=v).
  upsert <slug>      Find-or-create then update (Upstream / Build Strategy / AI Score).
  archive <slug>     Move to a terminal status (Published / Filtered) and archive
                     the item on the Project.

State / config:
  project-config.json::project_board       owner, repo, project_number, fields
  project-config.json::migration.auto_approve_score_threshold  default 0.8
  registry/auto-migration/project-cache.json   ownerId / projectId / fieldIds
                                               (gitignored — recreate via bootstrap)
  registry/auto-migration/exclude-list.json    {"slugs": [...]}; consulted on sync
  registry/auto-migration/queue.json           source for sync

Auth:
  Reads GH_PAT, then GH_TOKEN, then falls back to whatever `gh auth` already has.
  Required scopes: project (read+write), repo (read+write).
"""

from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Iterable

CACHE_PATH = "registry/auto-migration/project-cache.json"
QUEUE_PATH = "registry/auto-migration/queue.json"
EXCLUDE_LIST_PATH = "registry/auto-migration/exclude-list.json"
PROJECT_CONFIG_PATH = "project-config.json"

DEFAULT_PROJECT_TITLE = "Migration Queue"
DEFAULT_OWNER = "CodeEagle"
DEFAULT_REPO = "lzcat-apps"
DEFAULT_AUTO_APPROVE_THRESHOLD = 0.8

# (field_key, field_label, data_type, [options])
FIELD_SCHEMA: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    (
        "status",
        "Status",
        "SINGLE_SELECT",
        (
            "Inbox",
            "Approved",
            "In-Progress",
            "Browser-Test",
            "Awaiting-Human",
            "Published",
            "Blocked",
            "Filtered",
        ),
    ),
    ("slug", "Slug", "TEXT", ()),
    ("upstream", "Upstream", "TEXT", ()),
    (
        "build_strategy",
        "Build Strategy",
        "SINGLE_SELECT",
        (
            "official_image",
            "upstream_dockerfile",
            "target_repo_dockerfile",
            "upstream_with_target_template",
            "precompiled_binary",
        ),
    ),
    ("ai_score", "AI Score", "NUMBER", ()),
    ("branch", "Branch", "TEXT", ()),
    ("pr", "PR", "TEXT", ()),
    ("last_run", "Last Run", "DATE", ()),
    ("failures", "Failures", "TEXT", ()),
    ("codex_attempts", "Codex Attempts", "NUMBER", ()),
    # Audit / context fields requested by operator. Filled by sync from
    # queue.json so each card carries enough info that you don't need to
    # cross-reference queue.json or the ai-reviews.jsonl audit log just to
    # decide what's going on.
    ("discovered", "Discovered", "DATE", ()),     # when scout first saw the repo
    ("reviewed", "Reviewed", "DATE", ()),         # when AI last reached a verdict
    ("reasoning", "Reasoning", "TEXT", ()),       # AI verdict + top evidence (truncated)
    ("store_hits", "Store Hits", "TEXT", ()),     # lazycat app-store search summary
)

TERMINAL_STATUSES = {"Published", "Filtered"}


# ---- gh / GraphQL -------------------------------------------------------------

class GraphQLError(RuntimeError):
    """Raised when `gh api graphql` returns a non-rate-limit GraphQL error."""


class RateLimited(RuntimeError):
    """Raised when GitHub returns a rate-limit signal we should back off from."""


def _gh_env() -> dict[str, str]:
    env = os.environ.copy()
    pat = env.get("GH_PAT") or env.get("GH_TOKEN")
    if pat:
        env["GH_TOKEN"] = pat
    return env


def _is_rate_limited(payload: dict[str, Any], stderr: str) -> bool:
    if "RATE_LIMITED" in stderr or "rate limit" in stderr.lower():
        return True
    for err in payload.get("errors") or []:
        if isinstance(err, dict) and err.get("type") == "RATE_LIMITED":
            return True
    return False


def gh_graphql(
    query: str,
    variables: dict[str, Any] | None = None,
    *,
    max_retries: int = 5,
) -> dict[str, Any]:
    """Run a GraphQL request via `gh api graphql`. Retries on 429 / RATE_LIMITED."""
    cmd = ["gh", "api", "graphql", "-f", f"query={query}"]
    for k, v in (variables or {}).items():
        if isinstance(v, bool):
            cmd += ["-F", f"{k}={'true' if v else 'false'}"]
        elif isinstance(v, (int, float)):
            cmd += ["-F", f"{k}={v}"]
        else:
            cmd += ["-f", f"{k}={v}"]

    delay = 2.0
    for attempt in range(max_retries):
        out = subprocess.run(cmd, capture_output=True, text=True, check=False, env=_gh_env())
        stdout = out.stdout or ""
        stderr = out.stderr or ""
        try:
            payload = json.loads(stdout) if stdout.strip() else {}
        except json.JSONDecodeError:
            payload = {}

        rate_limited = _is_rate_limited(payload, stderr) or out.returncode == 429
        if rate_limited and attempt < max_retries - 1:
            time.sleep(delay + random.random())
            delay *= 2
            continue

        if out.returncode != 0:
            raise GraphQLError(f"gh graphql failed (rc={out.returncode}): {stderr.strip() or stdout.strip()}")
        if "errors" in payload:
            raise GraphQLError(f"GraphQL errors: {payload['errors']}")
        return payload.get("data", {})

    raise RateLimited("Rate-limited after exhausting retries")


# ---- cache --------------------------------------------------------------------

def load_cache(repo_root: Path) -> dict[str, Any]:
    p = repo_root / CACHE_PATH
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def save_cache(repo_root: Path, cache: dict[str, Any]) -> None:
    p = repo_root / CACHE_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cache, indent=2, sort_keys=True) + "\n", encoding="utf-8")


# ---- config -------------------------------------------------------------------

def load_project_config(repo_root: Path) -> dict[str, Any]:
    p = repo_root / PROJECT_CONFIG_PATH
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def project_board_settings(config: dict[str, Any]) -> dict[str, Any]:
    pb = config.get("project_board") if isinstance(config.get("project_board"), dict) else {}
    return {
        "owner": str(pb.get("owner") or DEFAULT_OWNER).strip() or DEFAULT_OWNER,
        "repo": str(pb.get("repo") or DEFAULT_REPO).strip() or DEFAULT_REPO,
        "project_number": int(pb.get("project_number") or 0) or None,
        "project_title": str(pb.get("project_title") or DEFAULT_PROJECT_TITLE).strip() or DEFAULT_PROJECT_TITLE,
    }


def auto_approve_threshold(config: dict[str, Any]) -> float:
    migration = config.get("migration") if isinstance(config.get("migration"), dict) else {}
    raw = migration.get("auto_approve_score_threshold", DEFAULT_AUTO_APPROVE_THRESHOLD)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return DEFAULT_AUTO_APPROVE_THRESHOLD


def load_exclude_slugs(repo_root: Path) -> set[str]:
    p = repo_root / EXCLUDE_LIST_PATH
    if not p.exists():
        return set()
    payload = json.loads(p.read_text(encoding="utf-8"))
    raw = payload.get("slugs") if isinstance(payload, dict) else None
    if not isinstance(raw, list):
        return set()
    return {str(s).strip() for s in raw if str(s).strip()}


def write_project_config(repo_root: Path, config: dict[str, Any]) -> None:
    p = repo_root / PROJECT_CONFIG_PATH
    p.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# ---- queue --------------------------------------------------------------------

def load_queue(repo_root: Path) -> dict[str, Any]:
    p = repo_root / QUEUE_PATH
    if not p.exists():
        return {"items": []}
    payload = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        return {"items": []}
    return payload


def queue_item_score(item: dict[str, Any]) -> float | None:
    review = item.get("discovery_review") if isinstance(item.get("discovery_review"), dict) else {}
    raw = review.get("score")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def queue_item_upstream(item: dict[str, Any]) -> str:
    candidate = item.get("candidate") if isinstance(item.get("candidate"), dict) else {}
    for key in ("repo_url", "html_url", "url", "full_name"):
        v = candidate.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    src = item.get("source")
    return str(src or "").strip()


def queue_item_strategy(item: dict[str, Any]) -> str:
    candidate = item.get("candidate") if isinstance(item.get("candidate"), dict) else {}
    return str(candidate.get("build_strategy") or item.get("build_strategy") or "").strip()


# ---- card-enrichment helpers --------------------------------------------------
# These extract the audit context (when found, when AI judged, AI reasoning,
# store-search hits) that goes onto each Project card. Plain-text values get
# truncated to keep card payloads under GitHub's per-field limits.

_TEXT_FIELD_LIMIT = 800   # GitHub Projects v2 single text field limit ~1024; leave headroom


def _truncate(text: str, limit: int = _TEXT_FIELD_LIMIT) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _iso_to_date(value: Any) -> str:
    """Coerce an ISO timestamp / date string to YYYY-MM-DD."""
    if not isinstance(value, str):
        return ""
    s = value.strip()
    if not s:
        return ""
    return s[:10]


def queue_item_discovered(item: dict[str, Any]) -> str:
    candidate = item.get("candidate") if isinstance(item.get("candidate"), dict) else {}
    for key in ("first_seen_at", "last_checked_at"):
        v = candidate.get(key)
        date = _iso_to_date(v)
        if date:
            return date
    return _iso_to_date(item.get("created_at"))


def queue_item_reviewed(item: dict[str, Any]) -> str:
    review = item.get("discovery_review") if isinstance(item.get("discovery_review"), dict) else {}
    return _iso_to_date(review.get("reviewed_at") or review.get("last_run_at"))


def queue_item_reasoning(item: dict[str, Any]) -> str:
    review = item.get("discovery_review") if isinstance(item.get("discovery_review"), dict) else {}
    parts: list[str] = []
    verdict = str(review.get("status") or "").strip()
    if verdict:
        parts.append(f"verdict: {verdict}")
    reason = str(review.get("reason") or "").strip()
    if reason:
        parts.append(reason)
    evidence = review.get("evidence")
    if isinstance(evidence, list):
        bullets = [f"• {str(e).strip()}" for e in evidence[:3] if str(e).strip()]
        if bullets:
            parts.extend(bullets)
    if not parts:
        last_error = str(item.get("last_error") or "").strip()
        if last_error:
            parts.append(f"error: {last_error}")
    return _truncate(" | ".join(parts))


def queue_item_store_hits(item: dict[str, Any]) -> str:
    candidate = item.get("candidate") if isinstance(item.get("candidate"), dict) else {}
    hits = candidate.get("lazycat_hits")
    if not isinstance(hits, list) or not hits:
        return "0 hits"
    labels: list[str] = []
    for h in hits[:5]:
        if not isinstance(h, dict):
            continue
        raw = str(h.get("raw_label") or "").strip()
        if raw:
            # Drop the trailing "<download_count>" most labels carry.
            labels.append(raw.rsplit(" ", 1)[0] if raw and raw.split(" ")[-1].isdigit() else raw)
    summary = f"{len(hits)} hits"
    if labels:
        summary += ": " + ", ".join(labels[:5])
    if len(hits) > 5:
        summary += f" (+{len(hits) - 5} more)"
    return _truncate(summary)


def render_card_body(item: dict[str, Any]) -> str:
    """Markdown body for the Issue / draft that backs each Project card.

    Goal: a single glance gives the operator the upstream URL, AI verdict
    chain, store-search summary, and timestamps without opening queue.json.
    """
    candidate = item.get("candidate") if isinstance(item.get("candidate"), dict) else {}
    review = item.get("discovery_review") if isinstance(item.get("discovery_review"), dict) else {}
    slug = str(item.get("slug", "")).strip() or "(unknown slug)"
    upstream = queue_item_upstream(item)

    lines: list[str] = []
    lines.append(f"# `{slug}`")
    lines.append("")
    if upstream:
        lines.append(f"**Upstream**: {upstream}")
    description = str(candidate.get("description") or "").strip()
    if description:
        lines.append(f"**Description**: {description}")
    lang = str(candidate.get("language") or "").strip()
    stars = candidate.get("total_stars")
    bits: list[str] = []
    if lang:
        bits.append(f"Language: {lang}")
    if stars is not None:
        bits.append(f"Stars: {stars}")
    discovered = queue_item_discovered(item)
    if discovered:
        bits.append(f"Discovered: {discovered}")
    reviewed = queue_item_reviewed(item)
    if reviewed:
        bits.append(f"Reviewed: {reviewed}")
    if bits:
        lines.append(f"**Meta**: {' • '.join(bits)}")
    lines.append("")

    # AI verdict
    verdict = str(review.get("status") or "").strip()
    score = review.get("score")
    reason = str(review.get("reason") or "").strip()
    evidence = review.get("evidence") if isinstance(review.get("evidence"), list) else []
    if verdict or score is not None or reason or evidence:
        lines.append("## AI verdict")
        meta_bits: list[str] = []
        if verdict:
            meta_bits.append(f"`{verdict}`")
        if score is not None:
            try:
                meta_bits.append(f"score **{float(score):.2f}**")
            except (TypeError, ValueError):
                pass
        reviewer = str(review.get("reviewer") or "").strip()
        if reviewer:
            meta_bits.append(f"by {reviewer}")
        if meta_bits:
            lines.append(" • ".join(meta_bits))
        if reason:
            lines.append("")
            lines.append(f"_{reason}_")
        if evidence:
            lines.append("")
            lines.append("**Evidence:**")
            for e in evidence[:10]:
                e_str = str(e).strip()
                if e_str:
                    lines.append(f"- {e_str}")
        lines.append("")

    # Store hits — full list, with URLs.
    hits = candidate.get("lazycat_hits") if isinstance(candidate.get("lazycat_hits"), list) else []
    if hits:
        lines.append(f"## LazyCat App Store hits ({len(hits)})")
        lines.append("")
        for h in hits[:25]:
            if not isinstance(h, dict):
                continue
            label = str(h.get("raw_label") or "").strip()
            url = str(h.get("detail_url") or "").strip()
            if url and label:
                lines.append(f"- [{label}]({url})")
            elif label:
                lines.append(f"- {label}")
            elif url:
                lines.append(f"- {url}")
        if len(hits) > 25:
            lines.append(f"- _… +{len(hits) - 25} more_")
        lines.append("")

    # Errors / blockers
    last_error = str(item.get("last_error") or "").strip()
    if last_error:
        lines.append("## Last error")
        lines.append("")
        lines.append("```")
        lines.append(last_error[:1500])
        lines.append("```")
        lines.append("")

    # Sources
    sources = candidate.get("source_labels") if isinstance(candidate.get("source_labels"), list) else []
    if sources:
        lines.append(f"**Discovered via**: {', '.join(str(s) for s in sources)}")

    lines.append("")
    lines.append(f"_Auto-generated by `scripts/project_board.py`. Item id: `{item.get('id', '')}`_")
    return "\n".join(lines).strip() + "\n"


def repository_id(owner: str, name: str) -> str:
    data = gh_graphql(REPOSITORY_ID_QUERY, {"owner": owner, "name": name})
    return str((data.get("repository") or {}).get("id") or "")


def update_draft_body(draft_issue_id: str, body: str) -> None:
    gh_graphql(UPDATE_DRAFT_ISSUE_MUTATION, {"draftIssueId": draft_issue_id, "body": body})


def convert_draft_to_issue(item_id: str, repo_id: str) -> dict[str, Any]:
    data = gh_graphql(CONVERT_DRAFT_TO_ISSUE_MUTATION, {"itemId": item_id, "repositoryId": repo_id})
    return data["convertProjectV2DraftIssueItemToIssue"]["item"]


def update_issue_body(issue_id: str, body: str) -> None:
    gh_graphql(UPDATE_ISSUE_BODY_MUTATION, {"issueId": issue_id, "body": body})


# ---- bootstrap ----------------------------------------------------------------

USER_LOOKUP_QUERY = """
query($login: String!) { user(login: $login) { id login } }
"""

ORG_LOOKUP_QUERY = """
query($login: String!) { organization(login: $login) { id login } }
"""

LIST_USER_PROJECTS_QUERY = """
query($login: String!, $cursor: String) {
  user(login: $login) {
    projectsV2(first: 50, after: $cursor) {
      pageInfo { hasNextPage endCursor }
      nodes { id number title closed }
    }
  }
}
"""

LIST_ORG_PROJECTS_QUERY = """
query($login: String!, $cursor: String) {
  organization(login: $login) {
    projectsV2(first: 50, after: $cursor) {
      pageInfo { hasNextPage endCursor }
      nodes { id number title closed }
    }
  }
}
"""

CREATE_PROJECT_MUTATION = """
mutation($ownerId: ID!, $title: String!) {
  createProjectV2(input: { ownerId: $ownerId, title: $title }) {
    projectV2 { id number title }
  }
}
"""

PROJECT_FIELDS_QUERY = """
query($projectId: ID!, $cursor: String) {
  node(id: $projectId) {
    ... on ProjectV2 {
      fields(first: 50, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        nodes {
          ... on ProjectV2Field { id name dataType }
          ... on ProjectV2SingleSelectField {
            id name dataType
            options { id name }
          }
          ... on ProjectV2IterationField { id name dataType }
        }
      }
    }
  }
}
"""

CREATE_FIELD_MUTATION_TEMPLATE = """
mutation($projectId: ID!, $name: String!) {{
  createProjectV2Field(input: {{
    projectId: $projectId, name: $name, dataType: {data_type}{options_clause}
  }}) {{
    projectV2Field {{
      ... on ProjectV2Field {{ id name dataType }}
      ... on ProjectV2SingleSelectField {{ id name dataType options {{ id name }} }}
    }}
  }}
}}
"""


def lookup_owner(login: str) -> dict[str, Any]:
    try:
        data = gh_graphql(USER_LOOKUP_QUERY, {"login": login})
        if data.get("user"):
            return {"id": data["user"]["id"], "type": "user", "login": data["user"]["login"]}
    except GraphQLError:
        pass
    data = gh_graphql(ORG_LOOKUP_QUERY, {"login": login})
    if data.get("organization"):
        return {"id": data["organization"]["id"], "type": "organization", "login": data["organization"]["login"]}
    raise GraphQLError(f"Owner '{login}' not found as user or organization")


def find_project(
    owner_login: str,
    owner_type: str,
    *,
    number: int | None,
    title: str,
) -> dict[str, Any] | None:
    query = LIST_ORG_PROJECTS_QUERY if owner_type == "organization" else LIST_USER_PROJECTS_QUERY
    cursor: str | None = None
    while True:
        data = gh_graphql(query, {"login": owner_login, "cursor": cursor or ""})
        owner_payload = data.get("organization") if owner_type == "organization" else data.get("user")
        owner_payload = owner_payload or {}
        projects = (owner_payload.get("projectsV2") or {}).get("nodes") or []
        for proj in projects:
            if not isinstance(proj, dict):
                continue
            if proj.get("closed"):
                continue
            if number and proj.get("number") == number:
                return proj
            if not number and proj.get("title") == title:
                return proj
        page = (owner_payload.get("projectsV2") or {}).get("pageInfo") or {}
        if not page.get("hasNextPage"):
            return None
        cursor = page.get("endCursor")


def create_project(owner_id: str, title: str) -> dict[str, Any]:
    data = gh_graphql(CREATE_PROJECT_MUTATION, {"ownerId": owner_id, "title": title})
    return data["createProjectV2"]["projectV2"]


def list_project_fields(project_id: str) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []
    cursor: str | None = None
    while True:
        data = gh_graphql(PROJECT_FIELDS_QUERY, {"projectId": project_id, "cursor": cursor or ""})
        node = data.get("node") or {}
        page = (node.get("fields") or {}).get("pageInfo") or {}
        nodes = (node.get("fields") or {}).get("nodes") or []
        for f in nodes:
            if isinstance(f, dict) and f.get("id"):
                fields.append(f)
        if not page.get("hasNextPage"):
            break
        cursor = page.get("endCursor")
    return fields


def _escape_graphql_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def create_field(project_id: str, label: str, data_type: str, options: tuple[str, ...]) -> dict[str, Any]:
    options_clause = ""
    if data_type == "SINGLE_SELECT":
        opt_lines = [
            f'{{name: "{_escape_graphql_string(opt)}", color: GRAY, description: ""}}'
            for opt in options
        ]
        options_clause = ", singleSelectOptions: [" + ", ".join(opt_lines) + "]"
    query = CREATE_FIELD_MUTATION_TEMPLATE.format(data_type=data_type, options_clause=options_clause)
    data = gh_graphql(query, {"projectId": project_id, "name": label})
    return data["createProjectV2Field"]["projectV2Field"]


DELETE_FIELD_MUTATION = """
mutation($fieldId: ID!) {
  deleteProjectV2Field(input: { fieldId: $fieldId }) {
    projectV2Field {
      ... on ProjectV2Field { id }
      ... on ProjectV2SingleSelectField { id }
    }
  }
}
"""

UPDATE_FIELD_OPTIONS_MUTATION_TEMPLATE = """
mutation($fieldId: ID!) {{
  updateProjectV2Field(input: {{
    fieldId: $fieldId,
    singleSelectOptions: [{options}]
  }}) {{
    projectV2Field {{
      ... on ProjectV2SingleSelectField {{ id name dataType options {{ id name }} }}
    }}
  }}
}}
"""


def delete_field(field_id: str) -> None:
    gh_graphql(DELETE_FIELD_MUTATION, {"fieldId": field_id})


def update_single_select_options(field_id: str, options: tuple[str, ...]) -> dict[str, Any]:
    opt_lines = [
        f'{{name: "{_escape_graphql_string(opt)}", color: GRAY, description: ""}}'
        for opt in options
    ]
    query = UPDATE_FIELD_OPTIONS_MUTATION_TEMPLATE.format(options=", ".join(opt_lines))
    data = gh_graphql(query, {"fieldId": field_id})
    return data["updateProjectV2Field"]["projectV2Field"]


def field_options_match(node: dict[str, Any], expected: tuple[str, ...]) -> bool:
    actual = {opt.get("name") for opt in (node.get("options") or []) if isinstance(opt, dict)}
    return actual == set(expected)


def ensure_field(
    project_id: str,
    existing: dict[str, Any] | None,
    label: str,
    data_type: str,
    options: tuple[str, ...],
) -> tuple[dict[str, Any], str]:
    """Make `label` exist with the right shape. Returns (node, action) where
    action is one of 'created' / 'recreated' / 'updated' / 'kept'.

    GitHub's UI auto-creates a default Status field (Todo/In Progress/Done) on
    every new Projects v2 board. The Status field is built-in and cannot be
    deleted, but its options ARE mutable via updateProjectV2Field. For other
    single-selects we keep the simpler delete-and-recreate path so options stay
    in our declared order.
    """
    if existing is None:
        return create_field(project_id, label, data_type, options), "created"
    if existing.get("dataType") != data_type:
        delete_field(existing["id"])
        return create_field(project_id, label, data_type, options), "recreated"
    if data_type == "SINGLE_SELECT" and not field_options_match(existing, options):
        if label == "Status":
            return update_single_select_options(existing["id"], options), "updated"
        delete_field(existing["id"])
        return create_field(project_id, label, data_type, options), "recreated"
    return existing, "kept"


def cache_field_node(node: dict[str, Any]) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "id": node.get("id"),
        "name": node.get("name"),
        "data_type": node.get("dataType"),
    }
    if node.get("dataType") == "SINGLE_SELECT":
        entry["options"] = {
            opt.get("name"): opt.get("id")
            for opt in (node.get("options") or [])
            if isinstance(opt, dict) and opt.get("name")
        }
    return entry


def cmd_bootstrap(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    config = load_project_config(repo_root)
    settings = project_board_settings(config)
    owner_login = settings["owner"]
    title = settings["project_title"]

    cache = load_cache(repo_root)
    cache.setdefault("project", {})
    cache.setdefault("fields", {})

    owner = lookup_owner(owner_login)
    cache["project"]["owner"] = owner["login"]
    cache["project"]["owner_type"] = owner["type"]
    cache["project"]["owner_id"] = owner["id"]

    project = find_project(owner_login, owner["type"], number=settings["project_number"], title=title)
    created_project = False
    if project is None:
        project = create_project(owner["id"], title)
        created_project = True
    cache["project"]["project_id"] = project["id"]
    cache["project"]["project_number"] = project["number"]
    cache["project"]["project_title"] = project["title"]

    if not settings["project_number"] or settings["project_number"] != project["number"]:
        config.setdefault("project_board", {})
        config["project_board"]["owner"] = owner_login
        config["project_board"]["repo"] = settings["repo"]
        config["project_board"]["project_number"] = project["number"]
        config["project_board"]["project_title"] = project["title"]
        write_project_config(repo_root, config)

    existing_fields = {f.get("name"): f for f in list_project_fields(project["id"])}
    created_fields: list[str] = []
    recreated_fields: list[str] = []
    updated_fields: list[str] = []
    for key, label, data_type, options in FIELD_SCHEMA:
        node, action = ensure_field(
            project["id"], existing_fields.get(label), label, data_type, options
        )
        existing_fields[label] = node
        if action == "created":
            created_fields.append(label)
        elif action == "recreated":
            recreated_fields.append(label)
        elif action == "updated":
            updated_fields.append(label)
        cache["fields"][label] = cache_field_node(node)

    save_cache(repo_root, cache)
    summary = {
        "project_id": project["id"],
        "project_number": project["number"],
        "project_title": project["title"],
        "created_project": created_project,
        "created_fields": created_fields,
        "recreated_fields": recreated_fields,
        "updated_fields": updated_fields,
        "fields": sorted(cache["fields"].keys()),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


# ---- item lookup --------------------------------------------------------------

PROJECT_ITEMS_BY_SLUG_QUERY = """
query($projectId: ID!, $cursor: String) {
  node(id: $projectId) {
    ... on ProjectV2 {
      items(first: 100, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id
          isArchived
          type
          content {
            __typename
            ... on DraftIssue { id title body }
            ... on Issue { id number url body title }
          }
          fieldValues(first: 30) {
            nodes {
              ... on ProjectV2ItemFieldTextValue {
                text
                field { ... on ProjectV2FieldCommon { id name } }
              }
              ... on ProjectV2ItemFieldNumberValue {
                number
                field { ... on ProjectV2FieldCommon { id name } }
              }
              ... on ProjectV2ItemFieldDateValue {
                date
                field { ... on ProjectV2FieldCommon { id name } }
              }
              ... on ProjectV2ItemFieldSingleSelectValue {
                name
                optionId
                field { ... on ProjectV2FieldCommon { id name } }
              }
            }
          }
        }
      }
    }
  }
}
"""

ADD_DRAFT_ITEM_MUTATION = """
mutation($projectId: ID!, $title: String!) {
  addProjectV2DraftIssue(input: { projectId: $projectId, title: $title }) {
    projectItem { id }
  }
}
"""

UPDATE_DRAFT_ISSUE_MUTATION = """
mutation($draftIssueId: ID!, $body: String!) {
  updateProjectV2DraftIssue(input: { draftIssueId: $draftIssueId, body: $body }) {
    draftIssue { id }
  }
}
"""

CONVERT_DRAFT_TO_ISSUE_MUTATION = """
mutation($itemId: ID!, $repositoryId: ID!) {
  convertProjectV2DraftIssueItemToIssue(input: { itemId: $itemId, repositoryId: $repositoryId }) {
    item {
      id
      content {
        __typename
        ... on Issue { id number url body }
      }
    }
  }
}
"""

REPOSITORY_ID_QUERY = """
query($owner: String!, $name: String!) {
  repository(owner: $owner, name: $name) { id }
}
"""

UPDATE_ISSUE_BODY_MUTATION = """
mutation($issueId: ID!, $body: String!) {
  updateIssue(input: { id: $issueId, body: $body }) { issue { id } }
}
"""

UPDATE_TEXT_FIELD = """
mutation($projectId: ID!, $itemId: ID!, $fieldId: ID!, $text: String!) {
  updateProjectV2ItemFieldValue(input: {
    projectId: $projectId, itemId: $itemId, fieldId: $fieldId,
    value: { text: $text }
  }) { projectV2Item { id } }
}
"""

UPDATE_NUMBER_FIELD_TEMPLATE = """
mutation($projectId: ID!, $itemId: ID!, $fieldId: ID!) {{
  updateProjectV2ItemFieldValue(input: {{
    projectId: $projectId, itemId: $itemId, fieldId: $fieldId,
    value: {{ number: {number} }}
  }}) {{ projectV2Item {{ id }} }}
}}
"""

UPDATE_DATE_FIELD = """
mutation($projectId: ID!, $itemId: ID!, $fieldId: ID!, $date: Date!) {
  updateProjectV2ItemFieldValue(input: {
    projectId: $projectId, itemId: $itemId, fieldId: $fieldId,
    value: { date: $date }
  }) { projectV2Item { id } }
}
"""

UPDATE_SINGLE_SELECT_FIELD = """
mutation($projectId: ID!, $itemId: ID!, $fieldId: ID!, $optionId: String!) {
  updateProjectV2ItemFieldValue(input: {
    projectId: $projectId, itemId: $itemId, fieldId: $fieldId,
    value: { singleSelectOptionId: $optionId }
  }) { projectV2Item { id } }
}
"""

ARCHIVE_ITEM_MUTATION = """
mutation($projectId: ID!, $itemId: ID!) {
  archiveProjectV2Item(input: { projectId: $projectId, itemId: $itemId }) {
    item { id }
  }
}
"""


def _item_field_map(item: dict[str, Any]) -> dict[str, Any]:
    """Flatten an item's fieldValues into {field_name: value}."""
    out: dict[str, Any] = {}
    for fv in (item.get("fieldValues") or {}).get("nodes") or []:
        if not isinstance(fv, dict):
            continue
        field = fv.get("field") or {}
        name = field.get("name")
        if not name:
            continue
        if "text" in fv:
            out[name] = fv.get("text")
        elif "number" in fv:
            out[name] = fv.get("number")
        elif "date" in fv:
            out[name] = fv.get("date")
        elif "name" in fv:
            out[name] = {"name": fv.get("name"), "optionId": fv.get("optionId")}
    return out


def list_project_items(project_id: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    cursor: str | None = None
    while True:
        data = gh_graphql(PROJECT_ITEMS_BY_SLUG_QUERY, {"projectId": project_id, "cursor": cursor or ""})
        node = data.get("node") or {}
        page = (node.get("items") or {}).get("pageInfo") or {}
        nodes = (node.get("items") or {}).get("nodes") or []
        items.extend(n for n in nodes if isinstance(n, dict))
        if not page.get("hasNextPage"):
            break
        cursor = page.get("endCursor")
    return items


def find_item_by_slug(project_id: str, slug: str) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Return (item_node, flat_fields) or (None, {})."""
    for item in list_project_items(project_id):
        flat = _item_field_map(item)
        if str(flat.get("Slug") or "").strip() == slug:
            return item, flat
    return None, {}


def add_item(project_id: str, slug: str) -> str:
    data = gh_graphql(ADD_DRAFT_ITEM_MUTATION, {"projectId": project_id, "title": slug})
    return data["addProjectV2DraftIssue"]["projectItem"]["id"]


def _require_field(cache: dict[str, Any], label: str) -> dict[str, Any]:
    field = (cache.get("fields") or {}).get(label)
    if not field or not field.get("id"):
        raise RuntimeError(f"Field '{label}' missing from project-cache.json — run bootstrap first")
    return field


def set_field(
    project_id: str,
    item_id: str,
    cache: dict[str, Any],
    label: str,
    value: Any,
) -> None:
    field = _require_field(cache, label)
    fid = field["id"]
    dtype = field.get("data_type")
    if dtype == "TEXT":
        gh_graphql(UPDATE_TEXT_FIELD, {"projectId": project_id, "itemId": item_id, "fieldId": fid, "text": str(value)})
    elif dtype == "NUMBER":
        # Float values inlined into the query — gh's -F flag stringifies decimals
        # in a way GraphQL rejects ("Variable $number of type Float! was provided invalid value").
        number = float(value)
        if number != number or number in (float("inf"), float("-inf")):
            raise RuntimeError(f"Refusing to send non-finite number to '{label}': {number!r}")
        query = UPDATE_NUMBER_FIELD_TEMPLATE.format(number=repr(number))
        gh_graphql(query, {"projectId": project_id, "itemId": item_id, "fieldId": fid})
    elif dtype == "DATE":
        gh_graphql(UPDATE_DATE_FIELD, {"projectId": project_id, "itemId": item_id, "fieldId": fid, "date": str(value)})
    elif dtype == "SINGLE_SELECT":
        option_id = (field.get("options") or {}).get(str(value))
        if not option_id:
            raise RuntimeError(f"Single-select field '{label}' has no option '{value}'")
        gh_graphql(
            UPDATE_SINGLE_SELECT_FIELD,
            {"projectId": project_id, "itemId": item_id, "fieldId": fid, "optionId": option_id},
        )
    else:
        raise RuntimeError(f"Unsupported field data type {dtype!r} for '{label}'")


def archive_item(project_id: str, item_id: str) -> None:
    gh_graphql(ARCHIVE_ITEM_MUTATION, {"projectId": project_id, "itemId": item_id})


# ---- subcommands --------------------------------------------------------------

def _load_for_command(args: argparse.Namespace) -> tuple[Path, dict[str, Any], str]:
    repo_root = Path(args.repo_root).resolve()
    cache = load_cache(repo_root)
    project = cache.get("project") or {}
    project_id = project.get("project_id")
    if not project_id:
        raise RuntimeError("Project not bootstrapped — run `project_board.py bootstrap` first")
    return repo_root, cache, project_id


def _ensure_item(project_id: str, slug: str) -> tuple[str, dict[str, Any], bool]:
    """Look up an item by Slug; create one if missing. Returns (item_id, flat_fields, created)."""
    node, flat = find_item_by_slug(project_id, slug)
    if node is not None:
        return node["id"], flat, False
    item_id = add_item(project_id, slug)
    return item_id, {}, True


def _build_item_index(project_id: str) -> dict[str, tuple[dict[str, Any], dict[str, Any]]]:
    """One-shot fetch of every Project item, keyed by Slug field text.

    `cmd_sync` previously called `find_item_by_slug` per queue entry, which
    walks the entire item list (paginated) on every invocation — O(N²) when
    queue and board are both large. This helper does the walk once so sync
    stays linear in queue size.
    """
    out: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    for node in list_project_items(project_id):
        flat = _item_field_map(node)
        slug = str(flat.get("Slug") or "").strip()
        if slug and slug not in out:
            out[slug] = (node, flat)
    return out


def cmd_sync(args: argparse.Namespace) -> int:
    repo_root, cache, project_id = _load_for_command(args)
    project_config = load_project_config(repo_root)
    threshold = auto_approve_threshold(project_config)
    exclude = load_exclude_slugs(repo_root)
    queue = load_queue(repo_root)
    items = [i for i in queue.get("items", []) if isinstance(i, dict)]

    # Single fetch up-front; everything below is in-memory lookup. Newly-added
    # items get folded into the index as we create them, so duplicate slugs in
    # queue.json don't trigger duplicate creates.
    index = _build_item_index(project_id)

    # Optional: convert/render rich card body so each Project item is an
    # issue with a markdown body. Disabled by default — enable via
    # `--render-body` so the operator can opt in once they've decided
    # they want the candidates spilling into the repo Issues tab.
    repo_id = ""
    settings = project_board_settings(project_config)
    if getattr(args, "render_body", False):
        repo_id = repository_id(settings["owner"], settings["repo"])

    summary: dict[str, list[str]] = {
        "created": [],
        "updated": [],
        "approved": [],
        "filtered_excluded": [],
        "skipped_no_slug": [],
        "issues_created": [],
        "bodies_updated": [],
    }

    for item in items:
        slug = str(item.get("slug", "")).strip()
        if not slug:
            summary["skipped_no_slug"].append(str(item.get("id", "")))
            continue

        if slug in exclude:
            existing = index.get(slug)
            if existing is None:
                summary["filtered_excluded"].append(slug)
                continue
            node, _ = existing
            set_field(project_id, node["id"], cache, "Status", "Filtered")
            summary["filtered_excluded"].append(slug)
            continue

        existing = index.get(slug)
        if existing is None:
            item_id = add_item(project_id, slug)
            flat: dict[str, Any] = {}
            created = True
        else:
            node, flat = existing
            item_id = node["id"]
            created = False

        if created:
            summary["created"].append(slug)
            set_field(project_id, item_id, cache, "Slug", slug)
            set_field(project_id, item_id, cache, "Status", "Inbox")
            flat = {"Slug": slug, "Status": {"name": "Inbox"}}
            # Cache the freshly-created node so a duplicate slug downstream
            # in this same sync resolves to the same item.
            index[slug] = ({"id": item_id}, flat)

        upstream = queue_item_upstream(item)
        if upstream and flat.get("Upstream") != upstream:
            set_field(project_id, item_id, cache, "Upstream", upstream)
            flat["Upstream"] = upstream
        strategy = queue_item_strategy(item)
        if strategy:
            current_strategy = flat.get("Build Strategy")
            current_name = current_strategy.get("name") if isinstance(current_strategy, dict) else current_strategy
            if current_name != strategy:
                try:
                    set_field(project_id, item_id, cache, "Build Strategy", strategy)
                    flat["Build Strategy"] = {"name": strategy}
                except RuntimeError:
                    # Unknown strategy option — ignore rather than blocking sync.
                    pass

        score = queue_item_score(item)
        if score is not None and flat.get("AI Score") != score:
            set_field(project_id, item_id, cache, "AI Score", score)
            flat["AI Score"] = score

        # Audit / context fields. We only push when the value changed so we
        # don't burn GraphQL calls every cycle. set_field tolerates dropping
        # a field if bootstrap hasn't created it yet (caught and ignored).
        for field_label, value in (
            ("Discovered", queue_item_discovered(item)),
            ("Reviewed", queue_item_reviewed(item)),
            ("Reasoning", queue_item_reasoning(item)),
            ("Store Hits", queue_item_store_hits(item)),
        ):
            if not value:
                continue
            if flat.get(field_label) == value:
                continue
            try:
                set_field(project_id, item_id, cache, field_label, value)
                flat[field_label] = value
            except RuntimeError:
                # Field missing in cache — bootstrap will add it next cycle.
                pass

        current_status = flat.get("Status")
        current_status_name = (
            current_status.get("name") if isinstance(current_status, dict) else current_status
        )
        downstream = {"In-Progress", "Browser-Test", "Awaiting-Human"} | TERMINAL_STATUSES
        # Auto-approve when EITHER the AI reviewer scored this item past the
        # threshold, OR discovery_gate already classified the candidate as
        # mechanically-ready (state="ready" — passed all mechanical filters,
        # didn't need an AI second opinion). Both routes signal "go".
        item_state = str(item.get("state") or "").strip()
        ai_says_go = score is not None and score >= threshold
        gate_says_go = item_state == "ready"
        if (
            (ai_says_go or gate_says_go)
            and current_status_name not in ({"Approved"} | downstream)
        ):
            set_field(project_id, item_id, cache, "Status", "Approved")
            flat["Status"] = {"name": "Approved"}
            summary["approved"].append(slug)
        elif not created:
            summary["updated"].append(slug)

        # Render the rich markdown body if --render-body is set. Drafts get
        # body filled then converted to actual Issues; existing Issues get
        # body updated in place. Cards already converted are recognized via
        # the item.content.__typename surfaced in _build_item_index.
        if getattr(args, "render_body", False) and repo_id:
            body = render_card_body(item)
            existing_node = index.get(slug, ({}, {}))[0] if existing else None
            content = (existing_node or {}).get("content") if existing_node else None
            content_type = (content or {}).get("__typename") if isinstance(content, dict) else None
            existing_body = (content or {}).get("body") if isinstance(content, dict) else ""
            content_id = (content or {}).get("id") if isinstance(content, dict) else None
            try:
                if created or content_type == "DraftIssue":
                    # Need to look up the draft id for newly-created items.
                    if content_id is None:
                        # Just-added items — refetch from server is expensive,
                        # cheaper to re-list this slug. Defer to next sync.
                        pass
                    else:
                        if existing_body != body:
                            update_draft_body(content_id, body)
                        # Convert draft → Issue once it has the body.
                        new_node = convert_draft_to_issue(item_id, repo_id)
                        if new_node:
                            content = new_node.get("content") or {}
                            index[slug] = (
                                {"id": item_id, "isArchived": False, "content": content},
                                flat,
                            )
                            summary["issues_created"].append(slug)
                elif content_type == "Issue" and isinstance(content, dict):
                    if existing_body != body and content.get("id"):
                        update_issue_body(content["id"], body)
                        summary["bodies_updated"].append(slug)
            except (GraphQLError, RuntimeError) as exc:
                # Body rendering must never fail the overall sync — log to
                # the audit summary instead.
                summary.setdefault("body_errors", []).append(f"{slug}: {exc}")

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def _approved_items(project_id: str) -> list[tuple[str, dict[str, Any]]]:
    out: list[tuple[str, dict[str, Any]]] = []
    for item in list_project_items(project_id):
        if item.get("isArchived"):
            continue
        flat = _item_field_map(item)
        status = flat.get("Status")
        status_name = status.get("name") if isinstance(status, dict) else status
        if status_name == "Approved":
            out.append((str(flat.get("Slug") or "").strip(), flat))
    return [pair for pair in out if pair[0]]


def cmd_list_approved(args: argparse.Namespace) -> int:
    _, _, project_id = _load_for_command(args)
    pairs = _approved_items(project_id)

    def sort_key(pair: tuple[str, dict[str, Any]]) -> tuple[int, str]:
        last_run = pair[1].get("Last Run")
        if isinstance(last_run, str) and last_run:
            return (0, last_run)
        return (1, pair[0])

    pairs.sort(key=sort_key)
    slugs = [s for s, _ in pairs[: max(args.limit, 0)]]
    if args.format == "json":
        print(json.dumps(slugs))
    else:
        for s in slugs:
            print(s)
    return 0


def cmd_read(args: argparse.Namespace) -> int:
    _, _, project_id = _load_for_command(args)
    node, flat = find_item_by_slug(project_id, args.slug)
    if node is None:
        print(json.dumps({"error": f"slug '{args.slug}' not on board"}, indent=2))
        return 1
    if args.field:
        value = flat.get(args.field)
        if isinstance(value, dict):
            print(value.get("name") or "")
        else:
            print("" if value is None else str(value))
        return 0
    print(json.dumps(flat, indent=2, sort_keys=True, default=str))
    return 0


def cmd_update(args: argparse.Namespace) -> int:
    _, cache, project_id = _load_for_command(args)
    node, _ = find_item_by_slug(project_id, args.slug)
    if node is None:
        print(json.dumps({"error": f"slug '{args.slug}' not on board"}, indent=2))
        return 1
    item_id = node["id"]
    if args.status:
        set_field(project_id, item_id, cache, "Status", args.status)
    for raw in args.field or []:
        if "=" not in raw:
            raise SystemExit(f"--field expects key=value, got {raw!r}")
        label, value = raw.split("=", 1)
        set_field(project_id, item_id, cache, label.strip(), value.strip())
    print(json.dumps({"slug": args.slug, "status": args.status, "fields": args.field or []}, indent=2))
    return 0


def cmd_upsert(args: argparse.Namespace) -> int:
    _, cache, project_id = _load_for_command(args)
    item_id, flat, created = _ensure_item(project_id, args.slug)
    if created:
        set_field(project_id, item_id, cache, "Slug", args.slug)
        set_field(project_id, item_id, cache, "Status", "Inbox")
    if args.upstream and flat.get("Upstream") != args.upstream:
        set_field(project_id, item_id, cache, "Upstream", args.upstream)
    if args.strategy:
        cur = flat.get("Build Strategy")
        cur_name = cur.get("name") if isinstance(cur, dict) else cur
        if cur_name != args.strategy:
            set_field(project_id, item_id, cache, "Build Strategy", args.strategy)
    if args.score is not None and flat.get("AI Score") != args.score:
        set_field(project_id, item_id, cache, "AI Score", args.score)
    print(json.dumps({"slug": args.slug, "created": created, "item_id": item_id}, indent=2))
    return 0


def cmd_archive(args: argparse.Namespace) -> int:
    _, cache, project_id = _load_for_command(args)
    node, _ = find_item_by_slug(project_id, args.slug)
    if node is None:
        print(json.dumps({"error": f"slug '{args.slug}' not on board"}, indent=2))
        return 1
    item_id = node["id"]
    if args.status not in TERMINAL_STATUSES:
        raise SystemExit(f"--status must be one of {sorted(TERMINAL_STATUSES)}, got {args.status!r}")
    set_field(project_id, item_id, cache, "Status", args.status)
    archive_item(project_id, item_id)
    print(json.dumps({"slug": args.slug, "status": args.status, "archived": True}, indent=2))
    return 0


# ---- argparse -----------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="project_board.py", description=__doc__.split("\n\n")[0])
    p.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("bootstrap", help="Find/create the Project; ensure all 10 fields; cache IDs")
    s.set_defaults(func=cmd_bootstrap)

    s = sub.add_parser("sync", help="Reconcile queue.json -> Project items; auto-approve high scorers")
    s.add_argument(
        "--render-body",
        action="store_true",
        help="Convert each draft card to a real GitHub Issue with a markdown body "
             "(verdict + evidence + store hits + dates). Subsequent runs update existing issues.",
    )
    s.set_defaults(func=cmd_sync)

    s = sub.add_parser("list-approved", help="Print approved slugs for the dispatcher")
    s.add_argument("-n", "--limit", type=int, default=2)
    s.add_argument("--format", choices=["text", "json"], default="text")
    s.set_defaults(func=cmd_list_approved)

    s = sub.add_parser("read", help="Print item fields by slug")
    s.add_argument("slug")
    s.add_argument("--field", help="If set, print just this field's value")
    s.set_defaults(func=cmd_read)

    s = sub.add_parser("update", help="Set Status and/or arbitrary fields on an existing item")
    s.add_argument("slug")
    s.add_argument("--status")
    s.add_argument("--field", action="append", default=[], help="key=value (repeatable)")
    s.set_defaults(func=cmd_update)

    s = sub.add_parser("upsert", help="Find or create an item, then update its core fields")
    s.add_argument("slug")
    s.add_argument("--upstream", default="")
    s.add_argument("--strategy", default="")
    s.add_argument("--score", type=float, default=None)
    s.set_defaults(func=cmd_upsert)

    s = sub.add_parser("archive", help="Move item to a terminal Status and archive it")
    s.add_argument("slug")
    s.add_argument("--status", default="Published", choices=sorted(TERMINAL_STATUSES))
    s.set_defaults(func=cmd_archive)

    return p


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
