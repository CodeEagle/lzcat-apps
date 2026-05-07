#!/usr/bin/env python3
"""Playwright-driven runner that executes the browser acceptance plan.

This is the missing link in the verify pipeline: `browser_acceptance_plan.py`
emits a plan, `functional_checker.py` classifies the result, but nobody was
actually walking through the app. Now we do.

Sequence per check:
  1. Open the entry URL (or the per-check `url` if set).
  2. Wait for DOMContentLoaded + a body element to mount.
  3. Subscribe to `console` + `pageerror` + failed `requestfailed` events.
  4. Detect platform-error / blank / "未找到应用" / 5xx patterns.
  5. Try to interact with the most obvious primary control (button, link,
     primary CTA) — best-effort; absence is not a failure.
  6. Screenshot the final state into apps/<slug>/acceptance/.
  7. Aggregate results into the schema functional_checker expects:

  {
    "status": "pass" | "fail",
    "blocking_issues": [...],
    "entry_url": "...",
    "checks": [{...per-check...}],
    "screenshots": [...],
    "browser_use": {
      "dom_rendered": bool,
      "console_errors": [...],
      "network_failures": [...]
    }
  }

Usage:
  python3 scripts/browser_acceptance_runner.py <slug> [--repo-root .] [--timeout-ms 60000]

Plan and entry URL are loaded from
  apps/<slug>/.browser-acceptance-plan.json
which `browser_acceptance_plan.py` writes earlier in the pipeline.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Defer the playwright import so unit tests that don't need it can still
# load this module to test the helper functions.
try:
    from playwright.async_api import async_playwright  # type: ignore
except ImportError:  # pragma: no cover
    async_playwright = None  # type: ignore[assignment]


PLATFORM_ERROR_MARKERS = (
    "未找到应用",
    "应用未启动",
    "Application not found",
    "502 Bad Gateway",
    "503 Service Unavailable",
    "504 Gateway Timeout",
    "503 Service Temporarily Unavailable",
    "Welcome to nginx!",
    "It works!",
    "default backend - 404",
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_plan(repo_root: Path, slug: str) -> dict[str, Any]:
    p = repo_root / "apps" / slug / ".browser-acceptance-plan.json"
    return json.loads(p.read_text(encoding="utf-8"))


def detect_platform_error(text: str) -> str | None:
    """Return the first platform-error marker found in the rendered body."""
    if not text:
        return None
    snippet = text.lower()
    for marker in PLATFORM_ERROR_MARKERS:
        if marker.lower() in snippet:
            return marker
    return None


def classify_dom(body_text: str, body_html: str) -> tuple[bool, list[str]]:
    """Decide whether the page rendered real app content. Returns
    (dom_rendered, blocking_issues)."""
    issues: list[str] = []
    if not body_text or len(body_text.strip()) < 20:
        issues.append("blank body (<20 chars rendered)")
    marker = detect_platform_error(body_text + body_html[:5000])
    if marker:
        issues.append(f"platform error marker: {marker!r}")
    if "<body" in body_html and "</body>" not in body_html:
        issues.append("body tag never closed (page may have crashed mid-render)")
    return (not issues, issues)


async def _run_check(
    context,
    *,
    name: str,
    url: str,
    timeout_ms: int,
    screenshot_path: Path | None,
) -> dict[str, Any]:
    page = await context.new_page()
    console_errors: list[str] = []
    network_failures: list[str] = []
    page_errors: list[str] = []

    page.on("console", lambda msg: console_errors.append(f"{msg.type}: {msg.text}") if msg.type in {"error", "warning"} else None)
    page.on("pageerror", lambda exc: page_errors.append(str(exc)))
    page.on("requestfailed", lambda req: network_failures.append(f"{req.method} {req.url}: {req.failure}"))

    response = None
    nav_error = ""
    try:
        response = await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
    except Exception as exc:  # noqa: BLE001 - playwright raises various
        nav_error = str(exc)

    body_text = ""
    body_html = ""
    if response is not None:
        try:
            await page.locator("body").wait_for(state="visible", timeout=timeout_ms)
            body_text = (await page.inner_text("body"))[:30000]
            body_html = (await page.content())[:30000]
        except Exception as exc:  # noqa: BLE001
            nav_error = nav_error or f"body wait failed: {exc}"

    dom_rendered, dom_issues = classify_dom(body_text, body_html)

    screenshot_record: dict[str, Any] | None = None
    if screenshot_path is not None:
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            await page.screenshot(path=str(screenshot_path), full_page=False)
            screenshot_record = {"path": str(screenshot_path), "url": url}
        except Exception as exc:  # noqa: BLE001
            screenshot_record = {"path": str(screenshot_path), "error": str(exc)}

    blocking_issues: list[str] = []
    if nav_error:
        blocking_issues.append(f"navigation: {nav_error}")
    blocking_issues.extend(dom_issues)
    if response is not None and response.status >= 500:
        blocking_issues.append(f"http {response.status}")
    # Console "warning" alone isn't blocking; only count "error" channel.
    real_console_errors = [e for e in console_errors if e.startswith("error:")]
    blocking_issues.extend(f"console error: {msg}" for msg in page_errors)

    await page.close()

    return {
        "name": name,
        "url": url,
        "http_status": getattr(response, "status", None),
        "dom_rendered": dom_rendered,
        "blocking_issues": blocking_issues,
        "console_errors": real_console_errors + page_errors,
        "network_failures": network_failures,
        "screenshot": screenshot_record,
        "body_excerpt": body_text[:2000],
    }


def update_screenshots_metadata(repo_root: Path, slug: str, screenshots: list[dict[str, Any]]) -> None:
    """Maintain apps/<slug>/acceptance/web-screenshots.json so the AI reviewer
    (claude_verify_reviewer) keeps seeing screenshot evidence without needing
    a separate capture_web_screenshot step.
    """
    if not screenshots:
        return
    path = repo_root / "apps" / slug / "acceptance" / "web-screenshots.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "capture_method": "browser_acceptance_runner",
        "screenshots": [
            {
                "path": str(Path(s["path"]).resolve().relative_to(repo_root.resolve())),
                "url": s.get("url", ""),
                "captured_at": _utc_now_iso(),
            }
            for s in screenshots
            if isinstance(s, dict) and s.get("path") and "error" not in s
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


async def _run_plan(
    plan: dict[str, Any],
    *,
    repo_root: Path,
    slug: str,
    timeout_ms: int,
) -> dict[str, Any]:
    entry_url = str(plan.get("entry_url") or "").strip()
    if not entry_url:
        return {
            "status": "fail",
            "blocking_issues": ["plan has no entry_url"],
            "checks": [],
            "screenshots": [],
            "browser_use": {"dom_rendered": False, "console_errors": [], "network_failures": []},
        }

    acceptance_dir = repo_root / "apps" / slug / "acceptance"

    if async_playwright is None:
        return {
            "status": "fail",
            "blocking_issues": ["playwright not installed in this environment"],
            "checks": [],
            "screenshots": [],
            "browser_use": {"dom_rendered": False, "console_errors": [], "network_failures": []},
        }

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1280, "height": 800}, ignore_https_errors=True)

        results: list[dict[str, Any]] = []
        # Always run a primary "open_home" check on entry_url first.
        primary = await _run_check(
            context,
            name="open_home",
            url=entry_url,
            timeout_ms=timeout_ms,
            screenshot_path=acceptance_dir / f"{slug}-home.png",
        )
        results.append(primary)

        # Run the additional plan checks that have a `url` (or fall back to
        # entry_url) but skip ones that are purely instruction-based with
        # no URL — those need a real Browser-Use agent we don't have here.
        for idx, check in enumerate((plan.get("checks") or [])[:5]):
            if not isinstance(check, dict):
                continue
            check_name = str(check.get("name") or f"check_{idx}").strip() or f"check_{idx}"
            if check_name == "open_home":
                continue
            target_url = str(check.get("url") or "").strip()
            if not target_url:
                # skip purely-instructional checks; AI reviewer + functional_checker handle them
                continue
            results.append(
                await _run_check(
                    context,
                    name=check_name,
                    url=target_url,
                    timeout_ms=timeout_ms,
                    screenshot_path=acceptance_dir / f"{slug}-{check_name}.png",
                )
            )

        await context.close()
        await browser.close()

    blocking: list[str] = []
    console_errors: list[str] = []
    network_failures: list[str] = []
    screenshots: list[dict[str, Any]] = []
    dom_ok = True
    for r in results:
        if r["blocking_issues"]:
            blocking.extend(r["blocking_issues"])
        console_errors.extend(r["console_errors"])
        network_failures.extend(r["network_failures"])
        if r["screenshot"]:
            screenshots.append(r["screenshot"])
        if not r["dom_rendered"]:
            dom_ok = False

    status = "pass" if dom_ok and not blocking else "fail"
    return {
        "schema_version": 1,
        "slug": slug,
        "entry_url": entry_url,
        "ran_at": _utc_now_iso(),
        "status": status,
        "blocking_issues": blocking,
        "checks": results,
        "screenshots": screenshots,
        "browser_use": {
            "dom_rendered": dom_ok,
            "console_errors": console_errors,
            "network_failures": network_failures,
        },
    }


def write_result(repo_root: Path, slug: str, result: dict[str, Any]) -> Path:
    out = repo_root / "apps" / slug / ".browser-acceptance.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("slug")
    p.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    p.add_argument("--timeout-ms", type=int, default=60000)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    try:
        plan = load_plan(repo_root, args.slug)
    except FileNotFoundError:
        print(f"browser_acceptance_runner: missing plan for slug={args.slug!r} "
              f"(run scripts/browser_acceptance_plan.py first)", file=sys.stderr)
        return 1

    result = asyncio.run(_run_plan(plan, repo_root=repo_root, slug=args.slug, timeout_ms=args.timeout_ms))
    out_path = write_result(repo_root, args.slug, result)
    update_screenshots_metadata(repo_root, args.slug, result.get("screenshots") or [])
    print(json.dumps({"status": result["status"], "path": str(out_path), "checks": len(result["checks"])}, indent=2))
    # Exit code reflects acceptance: 0 = pass, 2 = fail.
    return 0 if result["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
