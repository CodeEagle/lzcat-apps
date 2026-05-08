#!/usr/bin/env python3
"""Discovery review worker.

Despite the historical `codex_*` naming kept for queue.json and import
back-compat, this now invokes the Claude Code CLI (`claude --print …`) from
@anthropic-ai/claude-code rather than the OpenAI Codex CLI. Configure the
model via `migration.codex_worker_model` in project-config.json — defaults to
`claude-sonnet-4-6`.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_TASK_ROOT = "registry/auto-migration/discovery-review-tasks"
DEFAULT_OUTBOX = "registry/auto-migration/notifications"
DEFAULT_CODEX_WORKER_MODEL = "claude-sonnet-4-6"


@dataclass(frozen=True)
class DiscoveryReviewerConfig:
    repo_root: Path
    queue_path: Path
    task_dir: Path
    outbox_dir: Path | None = None
    developer_url: str = ""
    model: str = DEFAULT_CODEX_WORKER_MODEL
    execute: bool = True


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def safe_task_name(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z_.-]+", "-", value).strip("-").lower() or "unknown"


def read_text_if_exists(path: Path, *, max_chars: int = 12000) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]


def lazycat_store_search_guidance(item: dict[str, Any]) -> str:
    candidate = item.get("candidate") if isinstance(item.get("candidate"), dict) else {}
    hits = candidate.get("lazycat_hits") or item.get("lazycat_hits")
    if not isinstance(hits, list) or not hits:
        search = candidate.get("lazycat_store_search") if isinstance(candidate.get("lazycat_store_search"), dict) else {}
        search_hits = search.get("hits")
        hits = search_hits if isinstance(search_hits, list) else []

    if not hits:
        return (
            "No LazyCat app-store search hits are attached to this queue item. "
            "Do not infer that an app is already published unless local publication data or explicit evidence says so."
        )

    lines = [
        "This queue item includes LazyCat app-store search hits. Treat these hits as first-class evidence.",
        "If a hit is clearly the same product/app as the upstream repo, choose `skip` and cite the hit.",
        "If the match is ambiguous, weak, or depends on ownership/listing judgment, choose `needs_human`; do not guess.",
        "Do not choose `migrate` while an unresolved store hit could represent an already published app.",
        "LazyCat app-store search hits:",
    ]
    for hit in hits[:5]:
        if not isinstance(hit, dict):
            continue
        label = str(hit.get("raw_label") or hit.get("label") or "").strip()
        url = str(hit.get("detail_url") or hit.get("url") or "").strip()
        reason = str(hit.get("reason") or "").strip()
        parts = [part for part in [label, url, reason] if part]
        if parts:
            lines.append(f"- {' | '.join(parts)}")
    return "\n".join(lines)


def _resolve_full_name(item: dict[str, Any]) -> str:
    candidate = item.get("candidate") if isinstance(item.get("candidate"), dict) else {}
    full_name = str(candidate.get("full_name") or "").strip()
    if "/" not in full_name:
        source = str(item.get("source") or "").strip()
        if "/" in source and not source.startswith("http"):
            full_name = source
    return full_name


def _gh_headers() -> dict[str, str]:
    token = os.environ.get("GH_PAT") or os.environ.get("GH_TOKEN") or ""
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "lzcat-discovery-reviewer",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _gh_get_json(url: str, *, timeout: float, headers: dict[str, str] | None = None) -> Any:
    req = urllib.request.Request(url, headers=headers or _gh_headers())
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - URL is constructed
        return json.loads(resp.read().decode("utf-8"))


def _gh_decode_content_base64(payload: dict[str, Any], *, max_bytes: int) -> str:
    content = payload.get("content")
    encoding = payload.get("encoding")
    if not isinstance(content, str) or encoding != "base64":
        return ""
    try:
        raw = base64.b64decode(content)
    except (binascii.Error, ValueError):
        return ""
    return raw.decode("utf-8", errors="replace")[:max_bytes]


# Files we always pre-fetch when present in the upstream repo's root tree
# (claude needs to see source code, not just description text — otherwise
# the "naked framework" disqualifier (h) misfires on items whose
# description happens to say "framework" but whose source is clearly a
# deployable service). Each maps to a target field on the signals dict
# and a cap on body size to keep the prompt token budget reasonable.
_REPO_SIGNAL_FILES: tuple[tuple[str, str, int], ...] = (
    ("Dockerfile",          "dockerfile",  3000),
    ("Containerfile",       "dockerfile",  3000),
    ("dockerfile",          "dockerfile",  3000),
    ("docker-compose.yml",  "compose",     3000),
    ("docker-compose.yaml", "compose",     3000),
    ("compose.yml",         "compose",     3000),
    ("compose.yaml",        "compose",     3000),
    ("pyproject.toml",      "pyproject",   2000),
    ("setup.py",            "setup_py",    2000),
    ("requirements.txt",    "requirements", 1500),
    ("go.mod",              "go_mod",      1500),
    ("Cargo.toml",          "cargo_toml",  2000),
)


def fetch_repo_signals(item: dict[str, Any], *, timeout: float = 10.0) -> dict[str, Any]:
    """Pre-fetch deployability signals from the upstream GitHub repo.

    Returns a dict with the root file tree, README excerpt, and excerpts
    of common containerization / service-runtime indicator files
    (Dockerfile, docker-compose, package.json deps + scripts,
    pyproject/setup/requirements, go.mod, Cargo.toml). The result is
    spliced into the discovery prompt so claude judges based on actual
    source-code shape rather than just the description text.

    Rate-limit aware: at most ~6 GitHub API calls per item.
    Best-effort: every fetch is wrapped — partial data still beats no
    data, and a flaky API never blocks an entire discovery cycle.
    """
    full_name = _resolve_full_name(item)
    if "/" not in full_name:
        return {"fetch_status": "skip", "error": "no upstream owner/repo on item"}

    out: dict[str, Any] = {
        "fetch_status": "ok",
        "full_name": full_name,
        "files": [],          # [{name, type, size}, ...] root listing
        "dockerfile": "",
        "compose": "",
        "package_json": None, # {scripts, dependencies, devDependencies, has_start, framework_hits}
        "pyproject": "",
        "setup_py": "",
        "requirements": "",
        "go_mod": "",
        "cargo_toml": "",
        "readme": "",
        "errors": [],
    }
    headers = _gh_headers()

    # 1. Root tree (lists top-level entries; tells us which signal files
    # actually exist before we burn API calls fetching them).
    try:
        tree = _gh_get_json(
            f"https://api.github.com/repos/{full_name}/contents/",
            timeout=timeout, headers=headers,
        )
        if isinstance(tree, list):
            out["files"] = [
                {"name": e.get("name"), "type": e.get("type"), "size": e.get("size")}
                for e in tree[:300] if isinstance(e, dict)
            ]
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return {"fetch_status": "not_found", "full_name": full_name, "errors": []}
        out["errors"].append(f"tree: HTTP {exc.code}")
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        out["errors"].append(f"tree: {exc}")

    file_names = {str(f.get("name") or "") for f in out["files"]}

    # 2. README via the dedicated /readme endpoint (handles README.md,
    # README.rst, README.txt and case variants without us guessing).
    try:
        readme_payload = _gh_get_json(
            f"https://api.github.com/repos/{full_name}/readme",
            timeout=timeout, headers=headers,
        )
        if isinstance(readme_payload, dict):
            out["readme"] = _gh_decode_content_base64(readme_payload, max_bytes=6000)
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            out["errors"].append(f"readme: HTTP {exc.code}")
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        out["errors"].append(f"readme: {exc}")

    # 3. Signal files. Only fetch when present in the tree to avoid
    # burning quota on 404s.
    for fname, field, cap in _REPO_SIGNAL_FILES:
        if out[field]:  # already populated by an earlier alias
            continue
        if fname not in file_names:
            continue
        try:
            payload = _gh_get_json(
                f"https://api.github.com/repos/{full_name}/contents/{fname}",
                timeout=timeout, headers=headers,
            )
            if isinstance(payload, dict):
                out[field] = _gh_decode_content_base64(payload, max_bytes=cap)
        except urllib.error.HTTPError as exc:
            out["errors"].append(f"{fname}: HTTP {exc.code}")
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            out["errors"].append(f"{fname}: {exc}")

    # 4. package.json — structured parse so claude doesn't have to read JSON.
    if "package.json" in file_names:
        try:
            payload = _gh_get_json(
                f"https://api.github.com/repos/{full_name}/contents/package.json",
                timeout=timeout, headers=headers,
            )
            body = _gh_decode_content_base64(payload, max_bytes=12000) if isinstance(payload, dict) else ""
            if body:
                data = json.loads(body)
                if isinstance(data, dict):
                    deps = list((data.get("dependencies") or {}).keys())
                    dev_deps = list((data.get("devDependencies") or {}).keys())
                    scripts = data.get("scripts") if isinstance(data.get("scripts"), dict) else {}
                    framework_hits = sorted({
                        d for d in (deps + dev_deps)
                        if d in {
                            "react", "vue", "@vue/cli", "next", "nuxt", "svelte",
                            "@sveltejs/kit", "angular", "@angular/core",
                            "express", "fastify", "koa", "hono", "@nestjs/core",
                            "vite", "webpack", "parcel",
                        }
                    })
                    out["package_json"] = {
                        "scripts": scripts,
                        "dependencies_top": deps[:20],
                        "devDependencies_top": dev_deps[:20],
                        "has_start": "start" in scripts or "serve" in scripts or "dev" in scripts,
                        "framework_hits": framework_hits,
                    }
        except urllib.error.HTTPError as exc:
            out["errors"].append(f"package.json: HTTP {exc.code}")
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError) as exc:
            out["errors"].append(f"package.json: {exc}")

    return out


def format_repo_signals_block(signals: dict[str, Any]) -> str:
    """Render fetch_repo_signals() into a markdown block for the prompt."""
    status = str(signals.get("fetch_status") or "").strip()
    if status == "skip":
        return f"- Source-code signals skipped: {signals.get('error') or 'unknown'}."
    if status == "not_found":
        return (
            "- Upstream repo returned 404 — repo may have been deleted or made private. "
            "Default verdict is `skip` with reason citing the missing upstream."
        )

    lines: list[str] = []
    files = signals.get("files") or []
    if files:
        # Compact: show first 60 entries with type + size
        listings = []
        for f in files[:60]:
            n = f.get("name") or ""
            t = f.get("type") or ""
            sz = f.get("size") or 0
            sz_str = f" {sz}b" if t == "file" and sz else ""
            listings.append(f"{n}{'/' if t == 'dir' else ''}{sz_str}")
        lines.append("- Root file tree (first 60 entries):")
        lines.append("  ```")
        # 4 columns
        for i in range(0, len(listings), 4):
            lines.append("  " + "  ".join(listings[i:i+4]))
        lines.append("  ```")

    pkg = signals.get("package_json")
    if isinstance(pkg, dict):
        lines.append("- `package.json` summary:")
        scripts = pkg.get("scripts") or {}
        if scripts:
            keys = ", ".join(sorted(scripts.keys())[:10])
            lines.append(f"  - scripts: `{keys}`")
        if pkg.get("framework_hits"):
            lines.append(f"  - framework deps: {', '.join(pkg['framework_hits'])}")
        if pkg.get("dependencies_top"):
            lines.append(f"  - dependencies (top 20): {', '.join(pkg['dependencies_top'])}")
        lines.append(f"  - has_start_script: {pkg.get('has_start', False)}")

    if signals.get("dockerfile"):
        lines.append("- Dockerfile excerpt:")
        lines.append("  ```")
        for line in signals["dockerfile"].splitlines()[:40]:
            lines.append("  " + line)
        lines.append("  ```")

    if signals.get("compose"):
        lines.append("- docker-compose excerpt:")
        lines.append("  ```")
        for line in signals["compose"].splitlines()[:40]:
            lines.append("  " + line)
        lines.append("  ```")

    for field, label in (
        ("pyproject", "pyproject.toml"),
        ("setup_py", "setup.py"),
        ("requirements", "requirements.txt"),
        ("go_mod", "go.mod"),
        ("cargo_toml", "Cargo.toml"),
    ):
        body = signals.get(field) or ""
        if body:
            lines.append(f"- {label} excerpt:")
            lines.append("  ```")
            for line in body.splitlines()[:30]:
                lines.append("  " + line)
            lines.append("  ```")

    readme = signals.get("readme") or ""
    if readme:
        lines.append("- README excerpt (first 6 KB):")
        lines.append("  ```")
        for line in readme.splitlines()[:80]:
            lines.append("  " + line)
        lines.append("  ```")

    if signals.get("errors"):
        lines.append(f"- (partial fetch — errors: {'; '.join(signals['errors'][:3])})")

    if not lines:
        return "- No source-code signals fetched."
    return "\n".join(lines)


def fetch_license_info(item: dict[str, Any], *, timeout: float = 10.0) -> dict[str, Any]:
    """Live-fetch the upstream repo's LICENSE via the GitHub REST API.

    Discovery review previously told Claude to "inspect the LICENSE file"
    but didn't actually give it the file — the candidate dict scout
    builds carries no license metadata, and at discovery time no upstream
    clone exists locally either. This function plugs that hole: it hits
    ``GET /repos/{owner}/{name}/license`` and returns the SPDX id, the
    license display name, and a snippet of the raw LICENSE text. The
    result is injected verbatim into the prompt so the Step 0 commercial-
    use check has actual evidence to work with.

    Returns a dict with ``fetch_status`` ∈ {ok, not_found, skip, error}.
    Best-effort: any network/auth/decode error is swallowed and surfaced
    via ``error`` so a flaky GitHub never blocks a discovery cycle.
    """
    candidate = item.get("candidate") if isinstance(item.get("candidate"), dict) else {}
    full_name = str(candidate.get("full_name") or "").strip()
    if "/" not in full_name:
        # Some scout sources stash owner/repo in item.source instead.
        source = str(item.get("source") or "").strip()
        if "/" in source and not source.startswith("http"):
            full_name = source
    if "/" not in full_name:
        return {"fetch_status": "skip", "error": "no upstream owner/repo on item"}

    token = os.environ.get("GH_PAT") or os.environ.get("GH_TOKEN") or ""
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "lzcat-discovery-reviewer",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    url = f"https://api.github.com/repos/{full_name}/license"
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - URL is constructed
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return {"fetch_status": "not_found", "spdx": "", "name": "", "snippet": ""}
        return {"fetch_status": "error", "error": f"HTTP {exc.code} {exc.reason}"}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"fetch_status": "error", "error": f"network: {exc}"}
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return {"fetch_status": "error", "error": f"decode: {exc}"}

    license_obj = payload.get("license") if isinstance(payload, dict) else None
    spdx = ""
    name = ""
    if isinstance(license_obj, dict):
        spdx = str(license_obj.get("spdx_id") or "").strip()
        name = str(license_obj.get("name") or "").strip()

    snippet = ""
    content = payload.get("content") if isinstance(payload, dict) else ""
    encoding = payload.get("encoding") if isinstance(payload, dict) else ""
    if isinstance(content, str) and encoding == "base64":
        try:
            snippet = base64.b64decode(content).decode("utf-8", errors="replace")[:4000]
        except (binascii.Error, ValueError):
            snippet = ""

    return {"fetch_status": "ok", "spdx": spdx, "name": name, "snippet": snippet}


def format_license_block(info: dict[str, Any]) -> str:
    """Render fetch_license_info() result into a human-readable Markdown
    block to splice into the discovery prompt.
    """
    status = str(info.get("fetch_status") or "").strip()
    if status == "ok":
        spdx = str(info.get("spdx") or "").strip() or "(no SPDX id detected)"
        name = str(info.get("name") or "").strip() or "(no name)"
        snippet = str(info.get("snippet") or "").strip()
        lines = [f"- SPDX: `{spdx}`", f"- Name: {name}"]
        if snippet:
            lines.append("- LICENSE file (first 4 KB):")
            lines.append("```")
            lines.append(snippet)
            lines.append("```")
        return "\n".join(lines)
    if status == "not_found":
        return (
            "- **No LICENSE file found in the upstream repo.** "
            "Apply the NO LICENSE / UNLICENSED branch of Step 0 — "
            "default verdict is `needs_human`."
        )
    if status == "skip":
        return (
            f"- License fetch skipped: {info.get('error') or 'unknown'}. "
            "If the candidate dict / README excerpt does not surface a license, "
            "default verdict is `needs_human`."
        )
    return (
        f"- License fetch failed: {info.get('error') or 'unknown'}. "
        "If you cannot determine the license from other signals (README excerpt, "
        "candidate metadata), default verdict is `needs_human`."
    )


def build_codex_prompt(
    repo_root: Path,
    queue_path: Path,
    item: dict[str, Any],
    *,
    developer_url: str = "",
    license_info: dict[str, Any] | None = None,
    repo_signals: dict[str, Any] | None = None,
) -> str:
    item_json = json.dumps(item, ensure_ascii=False, indent=2, sort_keys=True)
    publication_status = read_text_if_exists(repo_root / "registry" / "status" / "local-publication-status.json", max_chars=12000)
    latest_candidates = read_text_if_exists(repo_root / "registry" / "candidates" / "latest.json", max_chars=12000)
    local_agent_candidates = read_text_if_exists(
        repo_root / "registry" / "candidates" / "local-agent-latest.json",
        max_chars=12000,
    )
    store_search_guidance = lazycat_store_search_guidance(item)
    if license_info is None:
        license_info = fetch_license_info(item)
    license_block = format_license_block(license_info)
    if repo_signals is None:
        repo_signals = fetch_repo_signals(item)
    repo_signals_block = format_repo_signals_block(repo_signals)

    return f"""You are Claude, the discovery reviewer for the LazyCat lzcat-apps auto-migration pipeline.

Goal:
- Decide whether this discovery candidate should proceed to migration before any build or migration starts.
- Return exactly one decision: `migrate`, `skip`, or `needs_human`.
- Use evidence from the upstream repository, local LazyCat publication status, candidate snapshots, and the user's developer app page when available.
- Do not run the migration, do not build packages, do not submit or publish anything.

Asymmetric cost model — bias HEAVILY toward `migrate`:
- A false positive (you say `migrate`, the slug turns out non-deployable) costs ONE worker run that ends in build_failed → Blocked. Cheap, recoverable.
- A false negative (you say `skip`, the slug was actually useful) is permanent — the candidate is lost from the pipeline.
- The threshold is intentionally LOW. Reserve `skip` only for cases that match an explicit disqualifier from the list below.

What this project actually packages — broader than "native self-hosted server":
The LazyCat app-store accepts ANYTHING that can be containerized into a
web-accessible service on a user's personal cloud, including:
- Native self-hosted server apps (Vaultwarden, Nextcloud, Home Assistant, Airflow)
- CLI tools / libraries wrapped as a web service (markitdown → web converter UI; ffmpeg → media-tools UI)
- Documentation / wiki / knowledge bases served as a personal wiki (HackTricks, Awesome-* viewers)
- Terminal / TUI / desktop apps wrapped in a browser shell (Warp, ttyd-style apps)
- ML/data tools with any UI surface (DVC Studio, Jupyter-like notebooks)
- Bots, schedulers, background services with a web dashboard
- Even single-purpose utilities (URL shorteners, paste bins, file servers) regardless of star count

Step 0 — Commercial-use license check (RUN THIS FIRST, BEFORE any other decision):
LazyCat is a commercial app store; only candidates whose upstream license permits
commercial redistribution can ship there.

Upstream license (live-fetched from GitHub `/repos/<owner>/<repo>/license`):
{license_block}

Use the SPDX id and LICENSE excerpt above as your primary evidence. If
`/license` returned 404 or empty, fall back to: (a) the `license` field in
package.json / Cargo.toml / pyproject.toml / go.mod when present in the
candidate dict, (b) any explicit license phrasing in the README. Classify
into:

  * COMMERCIAL-OK — proceed with normal `migrate`/`skip` evaluation:
      MIT, Apache-2.0, BSD-2-Clause, BSD-3-Clause, ISC, Unlicense, CC0, MPL-2.0,
      LGPL-2.1/3.0, GPL-2.0/3.0, AGPL-3.0 (copyleft is fine — it just propagates
      to derivative works).

  * NON-COMMERCIAL — fire `skip` immediately with:
      `state = "filtered_out"`, `filtered_reason = "non_commercial_license"`,
      `last_error = "License does not allow commercial use: <SPDX or name>"`,
      `discovery_review.status = "skip"`,
      `discovery_review.reason` MUST start with "不能商用：<license name>",
      `discovery_review.evidence` MUST cite the LICENSE file or license field.
      Common non-commercial licenses to recognize:
        - CC-BY-NC, CC-BY-NC-SA, CC-BY-NC-ND (any "NC" variant)
        - "非商用" / "Non-Commercial Use Only" / "for personal use only" clauses
        - Custom licenses with explicit "no commercial use" / "no resale" terms

  * RESTRICTIVE-BUT-COMMERCIALLY-DEPLOYABLE-CASE-BY-CASE — fire `needs_human`
    so the operator can read the specific terms before we ship:
        - SSPL (MongoDB / Elastic-style server-side license)
        - Elastic License v2 (free for end-user, restricted for hosting providers)
        - BUSL / Business Source License (time-limited non-commercial, converts
          to Apache after N years — operator must check the change date)
        - Commons Clause variants
        - Any custom license without an SPDX identifier
    Write `human_request.question` asking whether the operator's distribution
    plan complies with the upstream license terms.

  * NO LICENSE / UNLICENSED — fire `needs_human`. Distributing source without a
    license grants no rights; the operator must reach out to the upstream
    author or skip.

If Step 0 says skip or needs_human, the rest of the decision rules below are
moot — write the verdict and stop.

Upstream source-code signals (live-fetched from GitHub — root file
tree + key file excerpts):
{repo_signals_block}

You MUST use the source-code signals above (NOT the description text
alone) when judging disqualifier (h) "naked framework / SDK". A repo
that has any of:
  * Dockerfile / Containerfile / docker-compose
  * package.json with a `start` / `serve` / `dev` script OR a web
    framework dep (react/vue/next/svelte/express/fastify/nest/...)
  * a backend entrypoint (main.py / server.py / app.py / cmd/server/
    main.go / src/main.rs / etc.) AND a web framework dep
    (FastAPI / Flask / Django / actix-web / axum / gin / fiber)
  * an `index.html` / `public/`/`static/` directory at root
… is NOT a naked framework, regardless of whether the description
uses the word "framework". Examples that are migrate despite the
"framework" wording: ctfd, dpaste, nuclio, agent-runtime servers
("multi-agent service framework" — the SERVICE part means it's a
deployable runtime), and any "X framework for Y" where X ships a
runnable binary.

Decision rules (only when Step 0 says COMMERCIAL-OK):
- `migrate`: the upstream is a real software project (not abandoned spam) AND the README / description / **source-code signals** suggest there is functionality a user might want to run on their personal cloud. Stars / language / size / age do NOT disqualify. If you can imagine ANY way to wrap it into a web-accessible container, choose `migrate`.
- `skip`: ONLY when one of these EXPLICIT disqualifiers applies —
  (a) academic coursework / homework / graduation thesis with no real users
  (b) literal "template" / "skeleton" / "boilerplate" / "starter" repo
  (c) curated *list* of links (awesome-* index) — but a viewer/server FOR such lists IS migrate
  (d) "Hello World" / "test" / personal scratchpad with no description and no commits past initial
  (e) already-published in the LazyCat app store (covered by store-search hits — see below)
  (f) someone's personal homepage / résumé / blog content (not a deployable app)
  (g) blatant SaaS wrapper that ONLY works against a paid third-party API with no self-host path
  (h) the candidate is JUST a programming-language standard library, web framework (React, Vue, Express), or developer SDK, with literally NOTHING runnable as an end-user service. Caveat: many real apps' descriptions mention they're "built on Django" or "a CTF framework" or "an X framework for Y" — those are END-USER APPS that USE/PROVIDE a framework, NOT naked frameworks. dpaste (pasteboard app built on Django), ctfd (CTF competition platform), nuclio (serverless platform with dashboard) are all `migrate`. Only fire (h) when the repo is purely a library imported by other code with no service / web UI / dashboard at all.
- `needs_human`: ambiguous app-store match where the upstream MIGHT already be listed (operator should confirm). Do NOT use `needs_human` just because you're unsure about quality; default to `migrate` and let the worker confirm by attempting a build. (License-driven `needs_human` is handled in Step 0 above.)

LazyCat app-store search review:
{store_search_guidance}

Required queue update:
- Open and update this queue file: {queue_path}
- Find the item whose `id` is `{item.get("id", "")}`.
- For every decision, additionally write a numeric `discovery_review.score`
  in the closed interval [0.0, 1.0] reflecting your confidence the candidate
  is worth dispatching to a worker. The threshold is intentionally low so
  the pipeline isn't starved of work; almost every real software project
  should land above it:
    * 0.90+   confident migrate (clear app/service/wiki with active users)
    * 0.70    healthy candidate, multiple positive signals
    * 0.65    threshold for AI auto-approve (Inbox → Approved)
    * 0.55    leans migrate (has utility, partial signals) — STILL ABOVE threshold
    * 0.40    lean skip — needs an explicit disqualifier
    * 0.15-   confident skip (clear coursework / template / personal homepage / web framework)
  The score MUST be a JSON number (not a string).
- For `migrate`, set `state` to `ready`, clear `last_error` and `filtered_reason`, and write:
  `discovery_review.status = "migrate"`, `discovery_review.reviewed_at`, `discovery_review.reviewer = "claude"`,
  `discovery_review.reason`, `discovery_review.evidence` as a short list, and `discovery_review.score`.
- For `skip`, set `state` to `filtered_out`, set `filtered_reason` to `ai_discovery_skip` (override to `non_commercial_license` if the skip was driven by Step 0's license check), set `last_error` to a concise reason, and write:
  `discovery_review.status = "skip"`, `discovery_review.reviewed_at`, `discovery_review.reviewer = "claude"`,
  `discovery_review.reason`, `discovery_review.evidence`, and `discovery_review.score`.
- For `needs_human`, set `state` to `waiting_for_human` and write:
  `human_request.kind = "discovery_review"`, `human_request.question`, `human_request.options`,
  `human_request.context`, `human_request.created_at`, plus `discovery_review.status = "needs_human"`
  and `discovery_review.score`.
- If the item already has `human_response`, use that answer as user input and continue the decision.
- Preserve unrelated queue items and unrelated fields on this item.

Useful local files:
- registry/status/local-publication-status.json
- registry/status/developer-apps.json
- registry/candidates/latest.json
- registry/candidates/local-agent-latest.json
- project-config.json

Developer app page:
{developer_url or "(not configured)"}

Queue item:
```json
{item_json}
```

Local publication status excerpt:
```json
{publication_status or "{}"}
```

Latest candidate snapshot excerpt:
```json
{latest_candidates or "{}"}
```

LocalAgent candidate snapshot excerpt:
```json
{local_agent_candidates or "{}"}
```
"""


def build_codex_command(config: DiscoveryReviewerConfig) -> list[str]:
    """Build the Claude Code CLI invocation for one discovery-review session.

    Reads the prompt from stdin (subprocess `input=...`), prints the response
    to stdout (--output-format text keeps it unparsed), and bypasses the
    interactive permission prompt so the worker can run unattended in CI.
    """
    return [
        "claude",
        "--print",
        "--dangerously-skip-permissions",
        "--model",
        config.model,
        "--add-dir",
        str(config.repo_root),
        "--output-format",
        "text",
    ]


def write_task_bundle(
    config: DiscoveryReviewerConfig,
    item: dict[str, Any],
    *,
    prompt: str,
    command: list[str],
    now: str,
) -> dict[str, str]:
    config.task_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = config.task_dir / "prompt.md"
    task_path = config.task_dir / "task.json"
    prompt_path.write_text(prompt, encoding="utf-8")
    task_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "created_at": now,
                "item": item,
                "command": command,
                "prompt_path": str(prompt_path),
                "queue_path": str(config.queue_path),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return {"prompt_path": str(prompt_path), "task_path": str(task_path), "task_dir": str(config.task_dir)}


def relative_display(path: Path) -> str:
    parts = path.parts
    if "registry" in parts:
        return "/".join(parts[parts.index("registry") :])
    return str(path)


def write_notification(
    outbox_dir: Path,
    item: dict[str, Any],
    *,
    status: str,
    task_dir: Path,
    now: str,
) -> Path:
    outbox_dir.mkdir(parents=True, exist_ok=True)
    path = outbox_dir / f"{now.replace(':', '').replace('-', '')}-{safe_task_name(str(item.get('id', 'unknown')))}-discovery.md"
    path.write_text(
        "\n".join(
            [
                f"# Claude discovery reviewer {status}",
                "",
                f"- time: {now}",
                f"- item: {item.get('id', '')}",
                f"- source: {item.get('source', '')}",
                f"- slug: {item.get('slug', '')}",
                f"- state: {item.get('state', '')}",
                f"- task: {relative_display(task_dir)}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return path


def run_codex(config: DiscoveryReviewerConfig, prompt: str, command: list[str]) -> int:
    stdout_path = config.task_dir / "claude.stdout.log"
    stderr_path = config.task_dir / "claude.stderr.log"
    result = subprocess.run(command, input=prompt, text=True, capture_output=True, check=False)
    stdout_path.write_text(result.stdout or "", encoding="utf-8")
    stderr_path.write_text(result.stderr or "", encoding="utf-8")
    return result.returncode


def parse_item_json(value: str) -> dict[str, Any]:
    payload = json.loads(value)
    if not isinstance(payload, dict):
        raise ValueError("--item-json must decode to an object")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a Claude reviewer for one discovery_review queue item.")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--queue-path", required=True)
    parser.add_argument("--item-id", required=True)
    parser.add_argument("--item-json", required=True)
    parser.add_argument("--task-root", default=DEFAULT_TASK_ROOT)
    parser.add_argument("--outbox-dir", default=DEFAULT_OUTBOX)
    parser.add_argument("--developer-url", default="")
    parser.add_argument("--model", default=DEFAULT_CODEX_WORKER_MODEL)
    parser.add_argument("--no-execute", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    queue_path = Path(args.queue_path)
    if not queue_path.is_absolute():
        queue_path = repo_root / queue_path
    item = parse_item_json(args.item_json)
    now = utc_now_iso()
    task_root = Path(args.task_root)
    if not task_root.is_absolute():
        task_root = repo_root / task_root
    outbox_dir = Path(args.outbox_dir)
    if not outbox_dir.is_absolute():
        outbox_dir = repo_root / outbox_dir
    task_dir = task_root / f"{now.replace(':', '').replace('-', '')}-{safe_task_name(str(args.item_id))}"
    config = DiscoveryReviewerConfig(
        repo_root=repo_root,
        queue_path=queue_path,
        task_dir=task_dir,
        outbox_dir=outbox_dir,
        developer_url=args.developer_url,
        model=args.model,
        execute=not args.no_execute,
    )
    prompt = build_codex_prompt(repo_root, queue_path, item, developer_url=args.developer_url)
    command = build_codex_command(config)
    bundle = write_task_bundle(config, item, prompt=prompt, command=command, now=now)

    status = "prepared"
    returncode = 0
    if config.execute:
        returncode = run_codex(config, prompt, command)
        status = "completed" if returncode == 0 else "failed"

    notification_path = write_notification(outbox_dir, item, status=status, task_dir=task_dir, now=now)
    result = {
        "status": status,
        "returncode": returncode,
        "task_dir": bundle["task_dir"],
        "notification_path": str(notification_path),
    }
    (task_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    # Append the verdict to the cross-cycle audit log so periodic review of
    # AI calibration is possible. The reviewer writes its decision back into
    # queue.json (queue_path), so we read it out to capture model/score.
    try:
        from ai_review_log import append_review
    except ImportError:  # pragma: no cover
        from .ai_review_log import append_review  # type: ignore[no-redef]
    review = _read_back_discovery_verdict(queue_path, args.item_id)
    append_review(
        repo_root,
        reviewer="discovery",
        slug=str(item.get("slug", "")).strip(),
        item_id=args.item_id,
        model=config.model,
        verdict=str(review.get("status") or ""),
        score=review.get("score"),
        reason=str(review.get("reason") or ""),
        evidence=review.get("evidence") if isinstance(review.get("evidence"), list) else None,
        task_dir=str(task_dir),
        returncode=returncode,
        ts=now,
        extra={"source": str(item.get("source") or "")},
    )

    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return returncode


def _read_back_discovery_verdict(queue_path: Path, item_id: str) -> dict[str, Any]:
    """Pull the discovery_review object Claude wrote back for this item."""
    try:
        payload = json.loads(queue_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return {}
    target = item_id.strip()
    for entry in items:
        if isinstance(entry, dict) and str(entry.get("id", "")).strip() == target:
            review = entry.get("discovery_review")
            return review if isinstance(review, dict) else {}
    return {}


if __name__ == "__main__":
    raise SystemExit(main())
