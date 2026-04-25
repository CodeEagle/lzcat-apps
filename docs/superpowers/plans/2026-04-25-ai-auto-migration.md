# AI Auto Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an AI-assisted LazyCat migration pipeline that discovers repos, gathers web evidence, migrates packages, installs them, and requires Codex Browser Use functional acceptance before copywriting or publishing.

**Architecture:** Keep `lzcat-apps` as the single source of truth. Add small Python modules around the existing `full_migrate.py`, `run_build.py`, and `local_build.sh` rather than replacing them. Treat Obscura as a scraping/evidence tool and Codex Browser Use as the human-visible functional acceptance gate.

**Tech Stack:** Python standard library, existing `pytest`/`unittest` test style, existing `lzc-cli`, existing GitHub Actions, Obscura CLI, Codex Browser Use.

---

## File Structure

- Create `scripts/project_config.py`: load and validate `project-config.json`.
- Create `scripts/web_probe.py`: wrapper around Obscura with deterministic JSON output and safe fallbacks.
- Create `scripts/status_sync.py`: read the developer app page and update local publication status.
- Create `scripts/scout_core.py`: reusable candidate discovery module ported from `LocalAgent/lazycat_candidate_scanner.py`.
- Create `scripts/scout.py`: CLI entry for candidate scan and candidate JSON output.
- Create `scripts/browser_acceptance_plan.py`: generate `.browser-acceptance-plan.json` from manifest and app profile.
- Create `scripts/functional_checker.py`: install/runtime checks and Browser Use gate orchestration.
- Create `scripts/record_browser_acceptance.py`: validate and write `.browser-acceptance.json`.
- Create `scripts/auto_migrate.py`: top-level orchestrator for discovered or explicit repos.
- Create `docs/browser-acceptance.md`: operator protocol for Codex Browser Use.
- Modify `scripts/local_build.sh`: add `--functional-check` option.
- Test with `tests/test_project_config.py`, `tests/test_web_probe.py`, `tests/test_status_sync.py`, `tests/test_browser_acceptance_plan.py`, `tests/test_functional_checker.py`, and `tests/test_auto_migrate.py`.

## Task 1: Project Config Loader

**Files:**
- Create: `scripts/project_config.py`
- Test: `tests/test_project_config.py`
- Existing input: `project-config.json`

- [ ] **Step 1: Write failing tests for config loading**

Create `tests/test_project_config.py`:

```python
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.project_config import load_project_config


class ProjectConfigTest(unittest.TestCase):
    def test_loads_developer_apps_url(self) -> None:
        repo_root = Path(tempfile.mkdtemp(prefix="project-config-test-"))
        (repo_root / "project-config.json").write_text(
            json.dumps(
                {
                    "lazycat": {
                        "developer_apps_url": "https://lazycat.cloud/appstore/more/developers/178",
                        "developer_id": "178",
                        "status_sync": {
                            "enabled": True,
                            "source": "developer_apps_page",
                            "purpose": "Track apps already published by this developer and update migration status.",
                        },
                    }
                }
            )
            + "\n",
            encoding="utf-8",
        )

        config = load_project_config(repo_root)

        self.assertEqual(config.lazycat.developer_id, "178")
        self.assertEqual(
            config.lazycat.developer_apps_url,
            "https://lazycat.cloud/appstore/more/developers/178",
        )
        self.assertTrue(config.lazycat.status_sync_enabled)

    def test_missing_file_uses_disabled_status_sync(self) -> None:
        repo_root = Path(tempfile.mkdtemp(prefix="project-config-test-"))

        config = load_project_config(repo_root)

        self.assertEqual(config.lazycat.developer_apps_url, "")
        self.assertFalse(config.lazycat.status_sync_enabled)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test and verify failure**

Run:

```bash
pytest tests/test_project_config.py -v
```

Expected: import error for `scripts.project_config`.

- [ ] **Step 3: Implement config loader**

Create `scripts/project_config.py`:

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class LazyCatConfig:
    developer_apps_url: str = ""
    developer_id: str = ""
    status_sync_enabled: bool = False
    status_sync_source: str = ""


@dataclass(frozen=True)
class ProjectConfig:
    lazycat: LazyCatConfig


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def load_project_config(repo_root: Path) -> ProjectConfig:
    path = repo_root / "project-config.json"
    if not path.exists():
        return ProjectConfig(lazycat=LazyCatConfig())

    payload = json.loads(path.read_text(encoding="utf-8"))
    lazycat = payload.get("lazycat", {}) if isinstance(payload, dict) else {}
    status_sync = lazycat.get("status_sync", {}) if isinstance(lazycat, dict) else {}

    return ProjectConfig(
        lazycat=LazyCatConfig(
            developer_apps_url=str(lazycat.get("developer_apps_url", "")).strip(),
            developer_id=str(lazycat.get("developer_id", "")).strip(),
            status_sync_enabled=_as_bool(status_sync.get("enabled"), False),
            status_sync_source=str(status_sync.get("source", "")).strip(),
        )
    )
```

- [ ] **Step 4: Run test and commit**

Run:

```bash
pytest tests/test_project_config.py -v
```

Expected: `2 passed`.

Commit:

```bash
git add project-config.json scripts/project_config.py tests/test_project_config.py
git commit -m "feat: add LazyCat project config loader"
```

## Task 2: Obscura Web Probe Wrapper

**Files:**
- Create: `scripts/web_probe.py`
- Test: `tests/test_web_probe.py`

- [ ] **Step 1: Write failing tests for command construction and fallback**

Create `tests/test_web_probe.py`:

```python
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.web_probe import WebProbeResult, build_obscura_fetch_command, fetch_page


class WebProbeTest(unittest.TestCase):
    def test_build_obscura_fetch_command_uses_text_dump_and_network_idle(self) -> None:
        command = build_obscura_fetch_command("https://example.com/docs", dump="text")
        self.assertEqual(
            command,
            [
                "obscura",
                "fetch",
                "https://example.com/docs",
                "--dump",
                "text",
                "--wait-until",
                "networkidle0",
                "--quiet",
            ],
        )

    @patch("scripts.web_probe.subprocess.run")
    def test_fetch_page_returns_structured_result(self, run_mock) -> None:
        run_mock.return_value.returncode = 0
        run_mock.return_value.stdout = "Example page"
        run_mock.return_value.stderr = ""

        result = fetch_page("https://example.com/docs", dump="text")

        self.assertEqual(result.url, "https://example.com/docs")
        self.assertEqual(result.dump, "text")
        self.assertEqual(result.content, "Example page")
        self.assertEqual(result.errors, [])

    def test_result_json_roundtrip(self) -> None:
        result = WebProbeResult(
            url="https://example.com",
            dump="links",
            content="[Example](https://example.com)",
            errors=[],
        )
        payload = json.loads(result.to_json())
        self.assertEqual(payload["url"], "https://example.com")
        self.assertEqual(payload["dump"], "links")
```

- [ ] **Step 2: Run test and verify failure**

Run:

```bash
pytest tests/test_web_probe.py -v
```

Expected: import error for `scripts.web_probe`.

- [ ] **Step 3: Implement web probe**

Create `scripts/web_probe.py` with:

```python
from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass
from typing import Literal


DumpKind = Literal["html", "text", "links"]


@dataclass(frozen=True)
class WebProbeResult:
    url: str
    dump: str
    content: str
    errors: list[str]

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2) + "\n"


def build_obscura_fetch_command(url: str, *, dump: DumpKind = "text") -> list[str]:
    return [
        "obscura",
        "fetch",
        url,
        "--dump",
        dump,
        "--wait-until",
        "networkidle0",
        "--quiet",
    ]


def fetch_page(url: str, *, dump: DumpKind = "text", timeout_seconds: int = 90) -> WebProbeResult:
    command = build_obscura_fetch_command(url, dump=dump)
    try:
        result = subprocess.run(
            command,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except FileNotFoundError:
        return WebProbeResult(
            url=url,
            dump=dump,
            content="",
            errors=["obscura binary not found in PATH"],
        )
    except subprocess.TimeoutExpired:
        return WebProbeResult(
            url=url,
            dump=dump,
            content="",
            errors=[f"obscura fetch timed out after {timeout_seconds}s"],
        )

    errors: list[str] = []
    if result.returncode != 0:
        errors.append((result.stderr or result.stdout or f"exit={result.returncode}").strip())

    return WebProbeResult(
        url=url,
        dump=dump,
        content=result.stdout.strip(),
        errors=errors,
    )
```

- [ ] **Step 4: Run test and commit**

Run:

```bash
pytest tests/test_web_probe.py -v
```

Expected: `3 passed`.

Commit:

```bash
git add scripts/web_probe.py tests/test_web_probe.py
git commit -m "feat: add Obscura web probe wrapper"
```

## Task 3: Developer Page Status Sync

**Files:**
- Create: `scripts/status_sync.py`
- Test: `tests/test_status_sync.py`
- Read: `project-config.json`

- [ ] **Step 1: Write tests for developer page parsing**

Create `tests/test_status_sync.py`:

```python
from __future__ import annotations

import unittest

from scripts.status_sync import parse_developer_apps


class StatusSyncTest(unittest.TestCase):
    def test_parse_developer_apps_from_lazycat_links(self) -> None:
        content = """
        [MarkItDown](https://lazycat.cloud/appstore/detail/fun.selfstudio.app.migration.microsoft.markitdown-mcp)
        [Jellyfish](https://lazycat.cloud/appstore/detail/fun.selfstudio.app.migration.jellyfish)
        """

        apps = parse_developer_apps(content)

        self.assertEqual(
            apps,
            {
                "fun.selfstudio.app.migration.microsoft.markitdown-mcp": "MarkItDown",
                "fun.selfstudio.app.migration.jellyfish": "Jellyfish",
            },
        )

    def test_parse_developer_apps_ignores_duplicate_links(self) -> None:
        content = """
        [MarkItDown](https://lazycat.cloud/appstore/detail/fun.selfstudio.app.migration.microsoft.markitdown-mcp)
        [MarkItDown](https://lazycat.cloud/appstore/detail/fun.selfstudio.app.migration.microsoft.markitdown-mcp)
        """

        apps = parse_developer_apps(content)

        self.assertEqual(len(apps), 1)
```

- [ ] **Step 2: Implement parser and CLI**

Create `scripts/status_sync.py`:

```python
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from project_config import load_project_config
from web_probe import fetch_page


DETAIL_RE = re.compile(
    r"\[(?P<label>[^\]]+)\]\(https://lazycat\.cloud/appstore/detail/(?P<package>[^)#?]+)[^)]*\)"
)


def parse_developer_apps(content: str) -> dict[str, str]:
    apps: dict[str, str] = {}
    for match in DETAIL_RE.finditer(content):
        apps.setdefault(match.group("package").strip(), match.group("label").strip())
    return apps


def write_status(repo_root: Path, apps: dict[str, str]) -> Path:
    output_dir = repo_root / "registry" / "status"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "developer-apps.json"
    output_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "source": "developer_apps_page",
                "apps": apps,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync LazyCat developer app status.")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    config = load_project_config(repo_root)
    if not config.lazycat.status_sync_enabled or not config.lazycat.developer_apps_url:
        print("status sync disabled")
        return 0

    result = fetch_page(config.lazycat.developer_apps_url, dump="links")
    if result.errors:
        print("\n".join(result.errors))
        return 1

    output_path = write_status(repo_root, parse_developer_apps(result.content))
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Run tests and commit**

Run:

```bash
pytest tests/test_status_sync.py tests/test_project_config.py tests/test_web_probe.py -v
```

Expected: all tests pass.

Commit:

```bash
git add scripts/status_sync.py tests/test_status_sync.py
git commit -m "feat: sync LazyCat developer publication status"
```

## Task 4: Scout Core Reuse From LocalAgent

**Files:**
- Create: `scripts/scout_core.py`
- Create: `scripts/scout.py`
- Test: `tests/test_scout_core.py`
- Source reference: `/Users/lincoln/Develop/GitHub/LocalAgent/lazycat_candidate_scanner.py`

- [x] **Step 1: Port pure helpers first**

Copy these pure helpers from LocalAgent and keep their names stable:

- `compact_whitespace`
- `normalize`
- `parse_repo_input`
- `build_search_terms`
- `parse_appstore_hits`
- `classify_search_hits`
- `merge_repositories`
- `find_exclusion`
- `find_non_deployable_reason`

The first commit should not include network fetching. It should only add pure parsing and classification.

- [x] **Step 2: Write tests for search terms and classification**

Create `tests/test_scout_core.py`:

```python
from __future__ import annotations

import unittest

from scripts.scout_core import build_search_terms, classify_search_hits, merge_repositories


class ScoutCoreTest(unittest.TestCase):
    def test_build_search_terms_includes_dash_and_space_variants(self) -> None:
        self.assertEqual(build_search_terms("paperclip-ai"), ["paperclip-ai", "paperclip ai"])

    def test_classify_strong_lazycat_match_as_already_migrated(self) -> None:
        status, reason = classify_search_hits(
            {"repo": "paperclip", "full_name": "paperclipai/paperclip"},
            [{"raw_label": "Paperclip AI", "detail_url": "https://lazycat.cloud/appstore/detail/x"}],
        )
        self.assertEqual(status, "already_migrated")
        self.assertIn("Strong", reason)

    def test_merge_repositories_combines_sources(self) -> None:
        repos = [
            {
                "source_name": "github_trending_daily",
                "source_label": "GitHub Trending Daily",
                "owner": "owner",
                "repo": "demo",
                "full_name": "owner/demo",
                "repo_url": "https://github.com/owner/demo",
                "description": "Demo",
                "language": "Python",
                "total_stars": 100,
                "stars_today": 3,
            },
            {
                "source_name": "awesome_selfhosted",
                "source_label": "Awesome Self-Hosted",
                "owner": "owner",
                "repo": "demo",
                "full_name": "owner/demo",
                "repo_url": "https://github.com/owner/demo",
                "description": "Demo app",
                "language": "",
                "total_stars": 120,
                "stars_today": 0,
            },
        ]

        merged = merge_repositories(repos)

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["sources"], ["awesome_selfhosted", "github_trending_daily"])
        self.assertEqual(merged[0]["total_stars"], 120)
```

- [x] **Step 3: Add network-backed sources after pure tests pass**

Port these functions into `scripts/scout_core.py`:

- `fetch_text`
- `fetch_json`
- `parse_trending_repositories`
- `parse_trending_repositories_html`
- `fetch_github_search_candidates`
- `fetch_awesome_selfhosted_candidates`
- `search_lazycat`

Keep data output compatible with LocalAgent fields:

```json
{
  "full_name": "owner/repo",
  "repo_url": "https://github.com/owner/repo",
  "description": "text",
  "status": "portable",
  "status_reason": "No matching app found in LazyCat app store search.",
  "sources": ["github_trending_daily"],
  "searches": []
}
```

- [x] **Step 4: Add `scripts/scout.py` CLI**

`scripts/scout.py` accepts:

```bash
python3 scripts/scout.py scan --limit 50
python3 scripts/scout.py check owner/repo
```

It writes:

- `registry/candidates/latest.json`
- `registry/candidates/YYYY-MM-DD.json`

It does not auto-create app registry entries in the first version.

- [x] **Step 5: Run tests and commit**

Run:

```bash
pytest tests/test_scout_core.py -v
```

Expected: all scout core tests pass.

Commit:

```bash
git add scripts/scout_core.py scripts/scout.py tests/test_scout_core.py
git commit -m "feat: reuse LocalAgent candidate discovery"
```

## Task 5: Browser Acceptance Plan Generator

**Files:**
- Create: `scripts/browser_acceptance_plan.py`
- Test: `tests/test_browser_acceptance_plan.py`

- [ ] **Step 1: Write tests for manifest-derived entry URL**

Create `tests/test_browser_acceptance_plan.py`:

```python
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.browser_acceptance_plan import build_acceptance_plan


class BrowserAcceptancePlanTest(unittest.TestCase):
    def test_builds_plan_from_manifest_and_box_domain(self) -> None:
        repo_root = Path(tempfile.mkdtemp(prefix="browser-plan-test-"))
        app_dir = repo_root / "apps" / "demo"
        app_dir.mkdir(parents=True)
        (app_dir / "lzc-manifest.yml").write_text(
            "\n".join(
                [
                    "package: fun.selfstudio.app.migration.demo",
                    "name: Demo",
                    "application:",
                    "  subdomain: demo",
                    "  routes:",
                    "    - /=http://demo:3000/",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        plan = build_acceptance_plan(repo_root, "demo", box_domain="box.heiyu.space")

        self.assertEqual(plan["slug"], "demo")
        self.assertEqual(plan["package"], "fun.selfstudio.app.migration.demo")
        self.assertEqual(plan["entry_url"], "https://demo.box.heiyu.space")
        self.assertEqual(plan["checks"][0]["name"], "open_home")
```

- [ ] **Step 2: Implement plan generator**

Create `scripts/browser_acceptance_plan.py`:

```python
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


def _read_field(text: str, field: str) -> str:
    match = re.search(rf"^{re.escape(field)}:\s*(.+)$", text, re.MULTILINE)
    return match.group(1).strip().strip("'\"") if match else ""


def _read_subdomain(text: str) -> str:
    match = re.search(r"^\s{subdomain_indent}subdomain:\s*(.+)$".format(subdomain_indent="{2,}"), text, re.MULTILINE)
    if match:
        return match.group(1).strip().strip("'\"")
    match = re.search(r"^\s*subdomain:\s*(.+)$", text, re.MULTILINE)
    return match.group(1).strip().strip("'\"") if match else ""


def build_acceptance_plan(repo_root: Path, slug: str, *, box_domain: str) -> dict[str, Any]:
    manifest_path = repo_root / "apps" / slug / "lzc-manifest.yml"
    manifest_text = manifest_path.read_text(encoding="utf-8")
    package = _read_field(manifest_text, "package")
    subdomain = _read_subdomain(manifest_text) or slug
    entry_url = f"https://{subdomain}.{box_domain.strip()}"
    return {
        "schema_version": 1,
        "slug": slug,
        "package": package,
        "entry_url": entry_url,
        "checks": [
            {
                "name": "open_home",
                "kind": "browser_use",
                "instruction": "Open entry_url and verify the page renders real app content rather than a platform error, blank page, or server error.",
            },
            {
                "name": "console_and_network",
                "kind": "browser_use",
                "instruction": "Check Browser Use dev logs and visible UI for blocking console errors or failed app resources.",
            },
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create Codex Browser Use acceptance plan.")
    parser.add_argument("slug")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--box-domain", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    output_path = repo_root / "apps" / args.slug / ".browser-acceptance-plan.json"
    output_path.write_text(
        json.dumps(
            build_acceptance_plan(repo_root, args.slug, box_domain=args.box_domain),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Run tests and commit**

Run:

```bash
pytest tests/test_browser_acceptance_plan.py -v
```

Expected: `1 passed`.

Commit:

```bash
git add scripts/browser_acceptance_plan.py tests/test_browser_acceptance_plan.py
git commit -m "feat: generate Browser Use acceptance plans"
```

## Task 6: Functional Checker and Browser Use Gate

**Files:**
- Create: `scripts/functional_checker.py`
- Create: `scripts/record_browser_acceptance.py`
- Create: `docs/browser-acceptance.md`
- Test: `tests/test_functional_checker.py`

- [ ] **Step 1: Write acceptance-result validator tests**

Create `tests/test_functional_checker.py`:

```python
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.functional_checker import classify_acceptance


class FunctionalCheckerTest(unittest.TestCase):
    def test_classify_acceptance_pass(self) -> None:
        result = {
            "status": "pass",
            "blocking_issues": [],
            "browser_use": {"dom_rendered": True, "console_errors": [], "network_failures": []},
        }
        self.assertEqual(classify_acceptance(result), "browser_pass")

    def test_classify_acceptance_failed_when_blocking_issues_exist(self) -> None:
        result = {
            "status": "pass",
            "blocking_issues": [{"category": "routing", "summary": "API 404"}],
            "browser_use": {"dom_rendered": True, "console_errors": [], "network_failures": []},
        }
        self.assertEqual(classify_acceptance(result), "browser_failed")

    def test_classify_acceptance_pending_without_result(self) -> None:
        self.assertEqual(classify_acceptance(None), "browser_pending")
```

- [ ] **Step 2: Implement functional checker core**

Create `scripts/functional_checker.py` with:

```python
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

from browser_acceptance_plan import build_acceptance_plan


def classify_acceptance(result: dict[str, Any] | None) -> str:
    if not result:
        return "browser_pending"
    if result.get("blocking_issues"):
        return "browser_failed"
    return "browser_pass" if result.get("status") == "pass" else "browser_failed"


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def lzc_status(package_id: str) -> str:
    if not package_id:
        return ""
    result = subprocess.run(
        ["lzc-cli", "app", "status", package_id],
        text=True,
        capture_output=True,
        check=False,
    )
    return ((result.stdout or "") + (result.stderr or "")).strip()


def write_functional_check(repo_root: Path, slug: str, payload: dict[str, Any]) -> Path:
    output_path = repo_root / "apps" / slug / ".functional-check.json"
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check installed LazyCat app and require Browser Use acceptance.")
    parser.add_argument("slug")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--box-domain", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    app_dir = repo_root / "apps" / args.slug
    plan = build_acceptance_plan(repo_root, args.slug, box_domain=args.box_domain)
    plan_path = app_dir / ".browser-acceptance-plan.json"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    acceptance = read_json(app_dir / ".browser-acceptance.json")
    status = classify_acceptance(acceptance)
    output = {
        "schema_version": 1,
        "slug": args.slug,
        "status": "pass" if status == "browser_pass" else status,
        "browser_acceptance_plan": str(plan_path),
        "browser_acceptance": acceptance,
    }
    output_path = write_functional_check(repo_root, args.slug, output)
    print(output_path)
    return 0 if status == "browser_pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Implement acceptance recorder**

Create `scripts/record_browser_acceptance.py`:

```python
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Record Codex Browser Use acceptance result.")
    parser.add_argument("slug")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--status", choices=["pass", "fail"], required=True)
    parser.add_argument("--entry-url", required=True)
    parser.add_argument("--evidence", default="")
    parser.add_argument("--blocking-issue", action="append", default=[])
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    issues = [{"category": "browser_use", "summary": item} for item in args.blocking_issue]
    payload = {
        "schema_version": 1,
        "slug": args.slug,
        "status": args.status,
        "accepted_at": datetime.now(UTC).isoformat(),
        "entry_url": args.entry_url,
        "browser_use": {
            "dom_rendered": args.status == "pass",
            "console_errors": [],
            "network_failures": [],
            "screenshots": [],
        },
        "checks": [
            {
                "name": "open_home",
                "status": args.status,
                "evidence": args.evidence,
            }
        ],
        "blocking_issues": issues,
    }
    output_path = repo_root / "apps" / args.slug / ".browser-acceptance.json"
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output_path)
    return 0 if args.status == "pass" and not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Document Codex Browser Use protocol**

Create `docs/browser-acceptance.md`:

```markdown
# Codex Browser Use Acceptance

Browser acceptance is required before publishing a LazyCat app.

1. Run `python3 scripts/functional_checker.py <slug> --box-domain <box-domain>`.
2. Open `apps/<slug>/.browser-acceptance-plan.json`.
3. Use Codex Browser Use to open the `entry_url`.
4. Verify the page renders real app content, not a LazyCat platform error page.
5. Check Browser Use console logs for blocking errors.
6. Exercise the primary workflow described by the app README or visible UI.
7. If the app fails, record a failed result:

```bash
python3 scripts/record_browser_acceptance.py <slug> \
  --status fail \
  --entry-url "https://<subdomain>.<box-domain>" \
  --blocking-issue "Root page renders but API calls return 404"
```

8. If the app passes, record a passing result:

```bash
python3 scripts/record_browser_acceptance.py <slug> \
  --status pass \
  --entry-url "https://<subdomain>.<box-domain>" \
  --evidence "Home page and primary workflow rendered successfully in Codex Browser Use."
```

9. Re-run `python3 scripts/functional_checker.py <slug> --box-domain <box-domain>`.
10. Publishing is allowed only when the functional checker exits with code `0`.
```

- [ ] **Step 5: Run tests and commit**

Run:

```bash
pytest tests/test_functional_checker.py tests/test_browser_acceptance_plan.py -v
```

Expected: all tests pass.

Commit:

```bash
git add scripts/functional_checker.py scripts/record_browser_acceptance.py docs/browser-acceptance.md tests/test_functional_checker.py
git commit -m "feat: require Browser Use functional acceptance"
```

## Task 7: Local Build Integration

**Files:**
- Modify: `scripts/local_build.sh`
- Test: manual shell invocation

- [ ] **Step 1: Add option parsing**

In `scripts/local_build.sh`, add variables near existing option variables:

```bash
FUNCTIONAL_CHECK=false
BOX_DOMAIN="${LAZYCAT_BOX_DOMAIN:-}"
```

Add cases in the argument loop:

```bash
--functional-check) FUNCTIONAL_CHECK=true ;;
--box-domain=*) BOX_DOMAIN="${arg#--box-domain=}" ;;
```

- [ ] **Step 2: Run functional checker after install**

At the end of `scripts/local_build.sh`, after the install block, add:

```bash
if $FUNCTIONAL_CHECK; then
  if [ -z "$BOX_DOMAIN" ]; then
    echo "--functional-check requires --box-domain=<domain> or LAZYCAT_BOX_DOMAIN" >&2
    exit 1
  fi
  python3 "$REPO_ROOT/scripts/functional_checker.py" "$APP" --box-domain "$BOX_DOMAIN"
fi
```

- [ ] **Step 3: Run shell syntax check**

Run:

```bash
bash -n scripts/local_build.sh
```

Expected: no output, exit code `0`.

- [ ] **Step 4: Commit**

```bash
git add scripts/local_build.sh
git commit -m "feat: add functional check hook to local build"
```

## Task 8: Auto Migration Orchestrator

**Files:**
- Create: `scripts/auto_migrate.py`
- Test: `tests/test_auto_migrate.py`

- [ ] **Step 1: Write tests for command planning**

Create `tests/test_auto_migrate.py`:

```python
from __future__ import annotations

import unittest

from scripts.auto_migrate import build_full_migrate_command, next_stage_after_functional_check


class AutoMigrateTest(unittest.TestCase):
    def test_build_full_migrate_command_uses_reinstall_mode(self) -> None:
        command = build_full_migrate_command("owner/repo", build_mode="reinstall")
        self.assertEqual(
            command,
            ["python3", "scripts/full_migrate.py", "owner/repo", "--build-mode", "reinstall"],
        )

    def test_next_stage_requires_browser_pass(self) -> None:
        self.assertEqual(next_stage_after_functional_check("browser_pending"), "functional_pending")
        self.assertEqual(next_stage_after_functional_check("browser_failed"), "functional_failed")
        self.assertEqual(next_stage_after_functional_check("browser_pass"), "functional_passed")
```

- [ ] **Step 2: Implement orchestration helpers and CLI**

Create `scripts/auto_migrate.py`:

```python
from __future__ import annotations

import argparse
import subprocess


def build_full_migrate_command(source: str, *, build_mode: str) -> list[str]:
    return ["python3", "scripts/full_migrate.py", source, "--build-mode", build_mode]


def next_stage_after_functional_check(status: str) -> str:
    if status == "browser_pass":
        return "functional_passed"
    if status == "browser_failed":
        return "functional_failed"
    return "functional_pending"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run AI-assisted LazyCat migration flow.")
    parser.add_argument("source")
    parser.add_argument("--build-mode", choices=["auto", "build", "install", "reinstall", "validate-only"], default="reinstall")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    command = build_full_migrate_command(args.source, build_mode=args.build_mode)
    result = subprocess.run(command, text=True, check=False)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Run tests and commit**

Run:

```bash
pytest tests/test_auto_migrate.py -v
```

Expected: `2 passed`.

Commit:

```bash
git add scripts/auto_migrate.py tests/test_auto_migrate.py
git commit -m "feat: add AI migration orchestrator entrypoint"
```

## Task 9: Publication Gate

**Files:**
- Modify: `scripts/run_build.py`
- Test: `tests/test_publish_gate.py`

- [ ] **Step 1: Add a pure gate function**

Add to `scripts/run_build.py` near report helpers:

```python
def browser_acceptance_allows_publish(app_root: Path) -> tuple[bool, str]:
    acceptance_path = app_root / ".browser-acceptance.json"
    if not acceptance_path.exists():
        return False, f"missing Browser Use acceptance: {acceptance_path}"
    try:
        payload = json.loads(acceptance_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, f"invalid Browser Use acceptance JSON: {exc}"
    if payload.get("status") != "pass":
        return False, "Browser Use acceptance status is not pass"
    if payload.get("blocking_issues"):
        return False, "Browser Use acceptance has blocking issues"
    return True, ""
```

- [ ] **Step 2: Call the gate before appstore publish**

In `scripts/run_build.py`, before:

```python
if publish_to_store and not args.dry_run:
```

insert:

```python
        if publish_to_store:
            allowed, gate_reason = browser_acceptance_allows_publish(repo_dir)
            if not allowed:
                raise RuntimeError(f"publish_to_store blocked: {gate_reason}")
```

- [ ] **Step 3: Add tests**

Create `tests/test_publish_gate.py`:

```python
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.run_build import browser_acceptance_allows_publish


class PublishGateTest(unittest.TestCase):
    def test_blocks_when_acceptance_missing(self) -> None:
        app_root = Path(tempfile.mkdtemp(prefix="publish-gate-test-"))
        allowed, reason = browser_acceptance_allows_publish(app_root)
        self.assertFalse(allowed)
        self.assertIn("missing Browser Use acceptance", reason)

    def test_allows_passing_acceptance(self) -> None:
        app_root = Path(tempfile.mkdtemp(prefix="publish-gate-test-"))
        (app_root / ".browser-acceptance.json").write_text(
            json.dumps({"status": "pass", "blocking_issues": []}) + "\n",
            encoding="utf-8",
        )
        allowed, reason = browser_acceptance_allows_publish(app_root)
        self.assertTrue(allowed)
        self.assertEqual(reason, "")
```

- [ ] **Step 4: Run tests and commit**

Run:

```bash
pytest tests/test_publish_gate.py -v
```

Expected: `2 passed`.

Commit:

```bash
git add scripts/run_build.py tests/test_publish_gate.py
git commit -m "feat: block publishing without Browser Use acceptance"
```

## Task 10: End-to-End Pilot

**Files:**
- Runtime outputs under `apps/<slug>/`
- No code changes unless the pilot exposes bugs

- [ ] **Step 1: Sync developer page status**

Run:

```bash
python3 scripts/status_sync.py
```

Expected:

```text
/Users/lincoln/Develop/GitHub/lzcat/lzcat-apps/registry/status/developer-apps.json
```

- [ ] **Step 2: Scan candidates**

Run:

```bash
python3 scripts/scout.py scan --limit 20
```

Expected:

```text
registry/candidates/latest.json
```

- [ ] **Step 3: Run one explicit migration**

Use a known existing app first:

```bash
python3 scripts/auto_migrate.py microsoft/markitdown --build-mode reinstall
```

Expected:

- `apps/markitdown/` exists
- `dist/markitdown.lpk` exists
- install step either succeeds or reports missing local LazyCat credentials

- [ ] **Step 4: Create Browser Use acceptance plan**

Run:

```bash
python3 scripts/functional_checker.py markitdown --box-domain "$LAZYCAT_BOX_DOMAIN"
```

Expected before Browser Use is recorded: exit code `2`, `.browser-acceptance-plan.json` exists, `.functional-check.json.status == "browser_pending"`.

- [ ] **Step 5: Use Codex Browser Use**

Open `apps/markitdown/.browser-acceptance-plan.json`, then use Browser Use to open the `entry_url`.

Acceptance evidence must include:

- page is not blank
- page is not a LazyCat error page
- primary UI renders
- console/network errors are not blocking
- at least one primary workflow is exercised

- [ ] **Step 6: Record pass or fail**

If pass:

```bash
python3 scripts/record_browser_acceptance.py markitdown \
  --status pass \
  --entry-url "https://markitdown.$LAZYCAT_BOX_DOMAIN" \
  --evidence "Home page and conversion UI rendered successfully in Codex Browser Use."
```

If fail:

```bash
python3 scripts/record_browser_acceptance.py markitdown \
  --status fail \
  --entry-url "https://markitdown.$LAZYCAT_BOX_DOMAIN" \
  --blocking-issue "Describe the blocking functional issue found in Browser Use."
```

- [ ] **Step 7: Re-run functional checker**

Run:

```bash
python3 scripts/functional_checker.py markitdown --box-domain "$LAZYCAT_BOX_DOMAIN"
```

Expected after pass: exit code `0`, `.functional-check.json.status == "pass"`.

- [ ] **Step 8: Verify publish gate**

Run dry-run package flow:

```bash
./scripts/local_build.sh markitdown --functional-check --box-domain="$LAZYCAT_BOX_DOMAIN"
```

Expected: no publish occurs; functional check gate reports pass when Browser Use acceptance is present.

## Rollout Order

1. Implement Tasks 1-3 to get project config, Obscura probe, and developer status sync.
2. Implement Task 4 to port LocalAgent discovery.
3. Implement Tasks 5-7 to make Browser Use acceptance a first-class local gate.
4. Implement Tasks 8-9 to wire orchestration and publishing protection.
5. Run Task 10 with one known app.
6. Only after the pilot passes, add copywriting and publisher convenience scripts.

## Self-Review

- Spec coverage: candidate discovery, Obscura scraping, developer status sync, existing migration flow, Browser Use acceptance, failure feedback, and publish gate are all covered.
- Placeholder scan: no task depends on an undefined file path or unnamed future script.
- Type consistency: `browser_pending`, `browser_failed`, `browser_pass`, `functional_pending`, `functional_failed`, and `functional_passed` are used consistently.
- Scope check: copywriting and automatic final publish are intentionally deferred until functional acceptance works.
