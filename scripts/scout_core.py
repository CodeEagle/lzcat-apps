from __future__ import annotations

import html
import io
import json
import os
import re
import tarfile
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import OrderedDict
from datetime import UTC, datetime, timedelta
from typing import Any

import yaml


APPSTORE_HIT_RE = re.compile(
    r"\[!\[Image \d+\]\([^)]+\)\s+(?P<label>.*?)\]\((?P<url>https?://lazycat\.cloud/appstore/detail/[^)]+)\)",
    re.DOTALL,
)
GITHUB_REPO_INPUT_RE = re.compile(
    r"^(?:https?://github\.com/)?(?P<owner>[^/\s]+)/(?P<repo>[^/\s#?]+?)(?:\.git)?/?$",
    re.IGNORECASE,
)
REPO_LINK_RE = re.compile(
    r"^\[(?P<owner>[^/\]]+)\s*/\s*(?P<repo>[^\]]+)\]\(http://github\.com/(?P<full>[^)]+)\)$"
)
TRENDING_ARTICLE_RE = re.compile(r"<article class=\"Box-row\".*?</article>", re.S)

HIGH_STAR_RECENT_DAYS = 365

TRENDING_SOURCES = (
    {
        "name": "github_trending_daily",
        "label": "GitHub Trending Daily",
        "url": "https://r.jina.ai/http://github.com/trending?since=daily",
        "defuddle_url": "https://defuddle.md/github.com/trending?since=daily",
        "fallback_url": "https://github.com/trending?since=daily",
    },
    {
        "name": "github_trending_weekly",
        "label": "GitHub Trending Weekly",
        "url": "https://r.jina.ai/http://github.com/trending?since=weekly",
        "defuddle_url": "https://defuddle.md/github.com/trending?since=weekly",
        "fallback_url": "https://github.com/trending?since=weekly",
    },
)

GITHUB_SEARCH_SOURCES = (
    {
        "name": "github_search_self_hosted_recent",
        "label": "GitHub Search Self-hosted",
        "query_template": "topic:self-hosted stars:>500 pushed:>={recent_date} archived:false fork:false",
        "sort": "updated",
        "per_page": 20,
    },
    {
        "name": "github_search_high_star_recent",
        "label": "GitHub Search High Star",
        "query_template": "stars:>2000 pushed:>={recent_date} archived:false fork:false",
        "sort": "updated",
        "per_page": 20,
    },
    {
        "name": "github_search_docker_recent",
        "label": "GitHub Search Dockerized",
        "query_template": "docker in:readme stars:>1000 pushed:>={recent_date} archived:false fork:false",
        "sort": "updated",
        "per_page": 20,
    },
)

AWESOME_SELFHOSTED_SOURCE = {
    "name": "awesome_selfhosted_high_star",
    "label": "Awesome Self-Hosted",
    "snapshot_url": "https://codeload.github.com/awesome-selfhosted/awesome-selfhosted-data/tar.gz/refs/heads/master",
    "min_stars": 1000,
    "recent_days": 540,
}


EXCLUDED_CATEGORY_RULES = (
    {
        "label": "image_hosting",
        "reason": "No incentive: image hosting / image bed",
        "keywords": ("image hosting", "imgbed", "picture bed", "photo hosting"),
    },
    {
        "label": "navigation",
        "reason": "No incentive: navigation / homepage dashboard",
        "keywords": ("start page", "startpage", "homepage dashboard", "links dashboard"),
    },
    {
        "label": "bookmark",
        "reason": "No incentive: bookmark manager",
        "keywords": ("bookmark manager", "bookmarks manager", "read later", "link saver"),
    },
    {
        "label": "notes",
        "reason": "No incentive: notes / PKM",
        "keywords": ("note taking", "notes app", "knowledge base", "pkm", "markdown notes"),
    },
    {
        "label": "vpn",
        "reason": "No incentive: VPN / tunnel / proxy",
        "keywords": ("vpn", "wireguard", "openvpn", "tailscale", "zerotier", "v2ray"),
    },
)


MANUAL_EXCLUSION_RULES = (
    {
        "full_name": "CodebuffAI/codebuff",
        "reason": "Incompatible runtime: requires macOS / desktop-native environment, not suitable for LazyCat.",
        "matched_keyword": "macos_only_repo",
    },
)


NON_DEPLOYABLE_RULE = {
    "label": "non_deployable",
    "reason": "Likely not a deployable self-hosted app/service",
    "keywords": (
        "sdk",
        "cli",
        "command line tool",
        "developer tool",
        "api client",
        "library",
        "framework",
        "toolkit",
        "starter kit",
        "boilerplate",
        "component",
        "plugin",
        "extension",
        "mcp",
        "model context protocol",
        "awesome list",
        "sample code",
        "model weights",
        "benchmark",
    ),
}


DEPLOYABLE_HINTS = (
    "self-hosted",
    "web app",
    "web ui",
    "dashboard",
    "server",
    "management system",
    "control panel",
    "service",
    "automation",
    "monitoring",
    "media server",
    "rss reader",
    "chat server",
    "wiki",
    "analytics",
    "cms",
    "search engine",
    "photo manager",
    "file manager",
    "password manager",
    "docker",
    "docker compose",
    "container",
    "deploy",
    "deployment",
    "admin panel",
    "portal",
)


def compact_whitespace(value: str) -> str:
    return " ".join(value.split())


def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^0-9a-zA-Z]+", " ", value.lower())).strip()


def strip_html_tags(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", value)
    return compact_whitespace(html.unescape(without_tags))


def parse_number(value: str) -> int:
    return int(value.replace(",", "").strip())


def parse_repo_input(value: str) -> tuple[str, str] | None:
    match = GITHUB_REPO_INPUT_RE.match(compact_whitespace(value))
    if not match:
        return None
    owner = compact_whitespace(match.group("owner"))
    repo = compact_whitespace(match.group("repo"))
    if not owner or not repo:
        return None
    return owner, repo


def build_search_terms(repo_name: str) -> list[str]:
    terms = [repo_name, repo_name.replace("-", " "), repo_name.replace("_", " ")]
    unique_terms: list[str] = []
    for term in terms:
        clean = compact_whitespace(term)
        if clean and clean not in unique_terms:
            unique_terms.append(clean)
    return unique_terms


def parse_appstore_hits(markdown: str) -> list[dict[str, str]]:
    if "未找到相关应用" in markdown:
        return []

    hits: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for match in APPSTORE_HIT_RE.finditer(markdown):
        detail_url = match.group("url").replace("http://", "https://")
        if detail_url in seen_urls:
            continue
        seen_urls.add(detail_url)
        hits.append(
            {
                "raw_label": compact_whitespace(match.group("label")),
                "detail_url": detail_url,
            }
        )
    return hits


def classify_search_hits(repo: dict[str, Any], hits: list[dict[str, str]]) -> tuple[str, str]:
    if not hits:
        return ("portable", "No matching app found in LazyCat app store search.")

    repo_norm = normalize(repo["repo"])
    full_name_norm = normalize(repo["full_name"])
    strong_matches = []
    for hit in hits:
        hit_norm = normalize(hit["raw_label"])
        if not hit_norm:
            continue
        if hit_norm.startswith(repo_norm + " ") or hit_norm == repo_norm:
            strong_matches.append(hit)
            continue
        if full_name_norm and full_name_norm in hit_norm:
            strong_matches.append(hit)

    if strong_matches:
        return ("already_migrated", "Strong app-store match found for repository name.")
    return ("needs_review", "App-store search returned possible matches that need manual review.")


def merge_repositories(repos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: OrderedDict[str, dict[str, Any]] = OrderedDict()
    for repo in repos:
        full_name = repo["full_name"]
        existing = merged.get(full_name)
        if not existing:
            repo = dict(repo)
            repo["sources"] = [repo["source_name"]]
            repo["source_labels"] = repo.get("source_labels", [repo.get("source_label", repo["source_name"])])
            merged[full_name] = repo
            continue

        existing["description"] = existing.get("description") or repo.get("description", "")
        existing["language"] = existing.get("language") or repo.get("language", "")
        existing["total_stars"] = max(int(existing.get("total_stars", 0) or 0), int(repo.get("total_stars", 0) or 0))
        existing["stars_today"] = max(int(existing.get("stars_today", 0) or 0), int(repo.get("stars_today", 0) or 0))
        existing["external_signal"] = existing.get("external_signal") or repo.get("external_signal", "")
        existing["external_url"] = existing.get("external_url") or repo.get("external_url", "")
        existing["sources"] = sorted(set(existing.get("sources", [])) | {repo["source_name"]})
        existing["source_labels"] = sorted(
            set(existing.get("source_labels", []))
            | set(repo.get("source_labels", [repo.get("source_label", repo["source_name"])]))
        )
    return list(merged.values())


def find_exclusion(repo: dict[str, Any]) -> dict[str, str] | None:
    for rule in MANUAL_EXCLUSION_RULES:
        if repo["full_name"].lower() == rule["full_name"].lower():
            return {
                "label": "manual_exclusion",
                "reason": rule["reason"],
                "matched_keyword": rule["matched_keyword"],
            }

    haystack = normalize(" ".join([repo["repo"], repo["full_name"], repo.get("description", "")]))
    for rule in EXCLUDED_CATEGORY_RULES:
        for keyword in rule["keywords"]:
            normalized_keyword = normalize(keyword)
            if normalized_keyword and normalized_keyword in haystack:
                return {
                    "label": rule["label"],
                    "reason": rule["reason"],
                    "matched_keyword": keyword,
                }
    return None


def fetch_bytes(url: str, timeout: int = 60, retries: int = 3, backoff_seconds: float = 1.5) -> bytes:
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "lzcat-apps-scout/1.0 (+https://github.com/CodeEagle/lzcat-apps)"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except Exception as exc:
            last_error = exc
            if attempt == retries:
                break
            time.sleep(backoff_seconds * attempt)
    assert last_error is not None
    raise last_error


def fetch_text(url: str, timeout: int = 60, retries: int = 3, backoff_seconds: float = 1.5) -> str:
    return fetch_bytes(url, timeout=timeout, retries=retries, backoff_seconds=backoff_seconds).decode(
        "utf-8", errors="replace"
    )


def fetch_json(url: str, timeout: int = 60, retries: int = 3, backoff_seconds: float = 1.5) -> dict[str, Any]:
    github_token = compact_whitespace(os.environ.get("GITHUB_TOKEN", "") or os.environ.get("GH_TOKEN", ""))
    header_sets = [
        {
            "User-Agent": "lzcat-apps-scout/1.0 (+https://github.com/CodeEagle/lzcat-apps)",
            "Accept": "application/vnd.github+json",
            **({"Authorization": f"Bearer {github_token}"} if github_token else {}),
        },
        {
            "User-Agent": "lzcat-apps-scout/1.0 (+https://github.com/CodeEagle/lzcat-apps)",
            "Accept": "application/vnd.github+json",
        },
    ]
    if not github_token:
        header_sets = header_sets[:1]

    last_error: Exception | None = None
    for headers in header_sets:
        auth_failed = False
        for attempt in range(1, retries + 1):
            request = urllib.request.Request(url, headers=headers)
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    return json.loads(response.read().decode("utf-8", errors="replace"))
            except urllib.error.HTTPError as exc:
                last_error = exc
                if exc.code == 401 and "Authorization" in headers:
                    auth_failed = True
                    break
                if attempt == retries:
                    break
                time.sleep(backoff_seconds * attempt)
            except Exception as exc:
                last_error = exc
                if attempt == retries:
                    break
                time.sleep(backoff_seconds * attempt)
        if auth_failed:
            continue
    assert last_error is not None
    raise last_error


def parse_trending_repositories(markdown: str, source: dict[str, str]) -> list[dict[str, Any]]:
    repos: list[dict[str, Any]] = []
    lines = markdown.splitlines()
    for index, raw_line in enumerate(lines):
        line = raw_line.strip()
        match = REPO_LINK_RE.match(line)
        if not match:
            continue

        owner = compact_whitespace(match.group("owner"))
        repo = compact_whitespace(match.group("repo"))
        full_name = compact_whitespace(match.group("full"))

        description = ""
        metadata = ""
        cursor = index + 1
        seen_description = False
        while cursor < len(lines):
            candidate = lines[cursor].strip()
            cursor += 1
            if not candidate or set(candidate) == {"-"}:
                continue
            if REPO_LINK_RE.match(candidate):
                break
            if candidate.startswith("[Sponsor]") or candidate.startswith("[Star]"):
                continue
            if not seen_description:
                description = compact_whitespace(candidate)
                seen_description = True
                continue
            metadata = compact_whitespace(candidate)
            break

        stars_today = 0
        total_stars = 0
        language = ""
        stars_today_match = re.search(r"(\d[\d,]*) stars today", metadata)
        total_stars_match = re.search(r"\[(\d[\d,]*)\]\(http://github\.com/.+?/stargazers\)", metadata)
        language_match = re.match(r"([A-Za-z0-9+#.\- ]+?)\[(\d[\d,]*)\]", metadata)

        if stars_today_match:
            stars_today = parse_number(stars_today_match.group(1))
        if total_stars_match:
            total_stars = parse_number(total_stars_match.group(1))
        if language_match:
            language = compact_whitespace(language_match.group(1))

        repos.append(
            {
                "source_name": source["name"],
                "source_label": source["label"],
                "source_labels": [source["label"]],
                "owner": owner,
                "repo": repo,
                "full_name": full_name,
                "repo_url": f"https://github.com/{full_name}",
                "description": description,
                "language": language,
                "total_stars": total_stars,
                "stars_today": stars_today,
            }
        )
    return repos


def parse_trending_repositories_html(document: str, source: dict[str, str]) -> list[dict[str, Any]]:
    repos: list[dict[str, Any]] = []
    for article in TRENDING_ARTICLE_RE.findall(document):
        repo_match = re.search(r'<h2 class="h3 lh-condensed">.*?<a[^>]+href="/([^"?#]+)"', article, re.S)
        if not repo_match:
            continue
        full_name = compact_whitespace(repo_match.group(1).strip("/"))
        if "/" not in full_name:
            continue
        owner, repo = [compact_whitespace(part) for part in full_name.split("/", 1)]

        description = ""
        description_match = re.search(r'<p class="col-9 color-fg-muted my-1 [^"]*">(.*?)</p>', article, re.S)
        if description_match:
            description = strip_html_tags(description_match.group(1))

        language = ""
        language_match = re.search(r'<span itemprop="programmingLanguage">(.*?)</span>', article, re.S)
        if language_match:
            language = strip_html_tags(language_match.group(1))

        total_stars = 0
        stars_match = re.search(r'href="/[^"]+/stargazers"[^>]*>.*?</svg>\s*([\d,]+)</a>', article, re.S)
        if stars_match:
            total_stars = parse_number(stars_match.group(1))

        stars_today = 0
        stars_today_match = re.search(r"([\d,]+)\s+stars today", article, re.S)
        if stars_today_match:
            stars_today = parse_number(stars_today_match.group(1))

        repos.append(
            {
                "source_name": source["name"],
                "source_label": source["label"],
                "source_labels": [source["label"]],
                "owner": owner,
                "repo": repo,
                "full_name": full_name,
                "repo_url": f"https://github.com/{full_name}",
                "description": description,
                "language": language,
                "total_stars": total_stars,
                "stars_today": stars_today,
            }
        )
    return repos


def build_recent_date(days: int = HIGH_STAR_RECENT_DAYS) -> str:
    return (datetime.now(UTC) - timedelta(days=days)).date().isoformat()


def fetch_github_search_candidates() -> list[dict[str, Any]]:
    recent_date = build_recent_date()
    repos: list[dict[str, Any]] = []
    for source in GITHUB_SEARCH_SOURCES:
        query = source["query_template"].format(recent_date=recent_date)
        params = urllib.parse.urlencode(
            {
                "q": query,
                "sort": source.get("sort", "updated"),
                "order": "desc",
                "per_page": int(source.get("per_page", 20)),
            }
        )
        payload = fetch_json(f"https://api.github.com/search/repositories?{params}")
        for item in payload.get("items", []):
            full_name = compact_whitespace(item.get("full_name", ""))
            if not full_name or "/" not in full_name:
                continue
            owner, repo = [compact_whitespace(part) for part in full_name.split("/", 1)]
            repos.append(
                {
                    "source_name": source["name"],
                    "source_label": source["label"],
                    "source_labels": [source["label"]],
                    "owner": owner,
                    "repo": repo,
                    "full_name": full_name,
                    "repo_url": item.get("html_url", f"https://github.com/{full_name}"),
                    "description": compact_whitespace(item.get("description", "") or ""),
                    "language": compact_whitespace(item.get("language", "") or ""),
                    "total_stars": int(item.get("stargazers_count", 0) or 0),
                    "stars_today": 0,
                }
            )
    return repos


def fetch_awesome_selfhosted_candidates() -> list[dict[str, Any]]:
    snapshot_bytes = fetch_bytes(AWESOME_SELFHOSTED_SOURCE["snapshot_url"], timeout=120, retries=4)
    recent_cutoff = build_recent_date(AWESOME_SELFHOSTED_SOURCE["recent_days"])
    source_name = AWESOME_SELFHOSTED_SOURCE["name"]
    source_label = AWESOME_SELFHOSTED_SOURCE["label"]
    repos: list[dict[str, Any]] = []

    with tarfile.open(fileobj=io.BytesIO(snapshot_bytes), mode="r:gz") as archive:
        for member in archive.getmembers():
            if not member.isfile() or "/software/" not in member.name or not member.name.endswith(".yml"):
                continue
            extracted = archive.extractfile(member)
            if extracted is None:
                continue
            payload = yaml.safe_load(extracted.read().decode("utf-8", errors="replace"))
            if not isinstance(payload, dict):
                continue
            source_code_url = compact_whitespace(payload.get("source_code_url", ""))
            parsed = parse_repo_input(source_code_url)
            if not parsed:
                continue
            if bool(payload.get("archived", False)):
                continue
            if int(payload.get("stargazers_count", 0) or 0) < AWESOME_SELFHOSTED_SOURCE["min_stars"]:
                continue
            updated_at = compact_whitespace(payload.get("updated_at", ""))
            if updated_at and updated_at < recent_cutoff:
                continue
            owner, repo = parsed
            full_name = f"{owner}/{repo}"
            repos.append(
                {
                    "source_name": source_name,
                    "source_label": source_label,
                    "source_labels": [source_label],
                    "owner": owner,
                    "repo": repo,
                    "full_name": full_name,
                    "repo_url": source_code_url,
                    "description": compact_whitespace(payload.get("description", "")),
                    "language": "",
                    "total_stars": int(payload.get("stargazers_count", 0) or 0),
                    "stars_today": 0,
                    "external_signal": f"Listed on {source_label}",
                    "external_url": compact_whitespace(payload.get("website_url", "")) or source_code_url,
                }
            )
    return repos


def search_lazycat(repo: dict[str, Any]) -> dict[str, Any]:
    aggregate_hits: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    search_records: list[dict[str, Any]] = []
    errors: list[str] = []
    final_status = "portable"
    final_reason = "No matching app found in LazyCat app store search."

    for term in build_search_terms(repo["repo"]):
        query = urllib.parse.quote(term)
        search_url = f"https://lazycat.cloud/appstore/search?keyword={query}"
        jina_url = f"https://r.jina.ai/http://lazycat.cloud/appstore/search?keyword={query}"
        try:
            markdown = fetch_text(jina_url)
            hits = parse_appstore_hits(markdown)
            for hit in hits:
                if hit["detail_url"] in seen_urls:
                    continue
                seen_urls.add(hit["detail_url"])
                aggregate_hits.append(hit)
            status, reason = classify_search_hits(repo, aggregate_hits)
            search_records.append(
                {
                    "term": term,
                    "search_url": search_url,
                    "result_count": len(hits),
                }
            )
            final_status = status
            final_reason = reason
            if final_status == "already_migrated":
                break
        except Exception as exc:  # pragma: no cover - network failure path
            errors.append(f"{term}: {exc}")
            search_records.append(
                {
                    "term": term,
                    "search_url": search_url,
                    "error": str(exc),
                }
            )

    if errors and final_status == "portable" and not aggregate_hits:
        final_status = "needs_review"
        final_reason = "Search failed for one or more terms; manual review required."

    return {
        "status": final_status,
        "reason": final_reason,
        "searches": search_records,
        "hits": aggregate_hits,
        "errors": errors,
    }


def scan_remote_candidates(*, include_github_search: bool = True, include_awesome: bool = True) -> list[dict[str, Any]]:
    raw_candidates: list[dict[str, Any]] = []
    for source in TRENDING_SOURCES:
        try:
            markdown = fetch_text(source["url"])
            raw_candidates.extend(parse_trending_repositories(markdown, source))
            continue
        except urllib.error.HTTPError as exc:
            if exc.code != 451:
                raise

        if source.get("defuddle_url"):
            try:
                defuddle_markdown = fetch_text(source["defuddle_url"])
                defuddle_repos = parse_trending_repositories(defuddle_markdown, source)
                if defuddle_repos:
                    raw_candidates.extend(defuddle_repos)
                    continue
            except Exception:
                pass

        if source.get("fallback_url"):
            html_document = fetch_text(source["fallback_url"])
            raw_candidates.extend(parse_trending_repositories_html(html_document, source))

    if include_github_search:
        raw_candidates.extend(fetch_github_search_candidates())
    if include_awesome:
        raw_candidates.extend(fetch_awesome_selfhosted_candidates())
    return merge_repositories(raw_candidates)


def check_candidate(repo: dict[str, Any], *, checked_at: str) -> dict[str, Any]:
    candidate = {
        "full_name": repo["full_name"],
        "owner": repo["owner"],
        "repo": repo["repo"],
        "repo_url": repo["repo_url"],
        "description": repo.get("description", ""),
        "language": repo.get("language", ""),
        "total_stars": int(repo.get("total_stars", 0) or 0),
        "stars_today": int(repo.get("stars_today", 0) or 0),
        "sources": repo.get("sources", [repo.get("source_name", "")]),
        "source_labels": repo.get("source_labels", [repo.get("source_label", repo.get("source_name", ""))]),
        "external_signal": repo.get("external_signal", ""),
        "external_url": repo.get("external_url", ""),
        "last_checked_at": checked_at,
        "searches": [],
        "lazycat_hits": [],
    }

    exclusion = find_exclusion(repo) or find_non_deployable_reason(repo)
    if exclusion:
        candidate.update(
            {
                "status": "excluded",
                "status_reason": exclusion["reason"],
                "exclusion": exclusion,
            }
        )
        return candidate

    search_result = search_lazycat(repo)
    candidate.update(
        {
            "status": search_result["status"],
            "status_reason": search_result["reason"],
            "searches": search_result["searches"],
            "lazycat_hits": search_result["hits"],
        }
    )
    if search_result["errors"]:
        candidate["search_errors"] = search_result["errors"]
    return candidate


def find_non_deployable_reason(repo: dict[str, Any]) -> dict[str, str] | None:
    haystack = normalize(" ".join([repo["repo"], repo["full_name"], repo.get("description", "")]))
    deployable_haystack = normalize(" ".join([repo["repo"], repo.get("description", "")]))
    positive_hits = [keyword for keyword in DEPLOYABLE_HINTS if normalize(keyword) in deployable_haystack]
    repo_name_norm = normalize(repo["repo"])

    for keyword in ("mcp", "skill", "skills", "plugin", "extension", "cli"):
        normalized_keyword = normalize(keyword)
        if (
            repo_name_norm == normalized_keyword
            or repo_name_norm.startswith(normalized_keyword + " ")
            or repo_name_norm.endswith(" " + normalized_keyword)
        ):
            return {
                "label": NON_DEPLOYABLE_RULE["label"],
                "reason": NON_DEPLOYABLE_RULE["reason"],
                "matched_keyword": keyword,
            }

    if not positive_hits:
        for keyword in NON_DEPLOYABLE_RULE["keywords"]:
            normalized_keyword = normalize(keyword)
            if normalized_keyword and normalized_keyword in haystack:
                return {
                    "label": NON_DEPLOYABLE_RULE["label"],
                    "reason": NON_DEPLOYABLE_RULE["reason"],
                    "matched_keyword": keyword,
                }
    return None
