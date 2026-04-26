#!/usr/bin/env python3

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright


def relative_to_repo(repo_root: Path, path: Path) -> str:
    return str(path.resolve().relative_to(repo_root.resolve()))


def parse_viewport(value: str) -> tuple[int, int]:
    try:
        width_text, height_text = value.lower().split("x", 1)
        width = int(width_text)
        height = int(height_text)
    except Exception as exc:
        raise argparse.ArgumentTypeError("viewport must look like 1280x800") from exc
    if width < 320 or height < 320:
        raise argparse.ArgumentTypeError("viewport width and height must both be at least 320")
    return width, height


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def write_metadata(
    repo_root: Path,
    app_root: Path,
    screenshot_path: Path,
    url: str,
    viewport: tuple[int, int],
    full_page: bool,
) -> Path:
    metadata_path = app_root / "acceptance" / "web-screenshots.json"
    payload = read_json(metadata_path)
    payload["schema_version"] = 1
    payload["capture_method"] = "playwright_page_screenshot"
    screenshots = [
        item for item in payload.get("screenshots", [])
        if isinstance(item, dict) and item.get("path") != relative_to_repo(repo_root, screenshot_path)
    ]
    screenshots.append(
        {
            "path": relative_to_repo(repo_root, screenshot_path),
            "url": url,
            "viewport": {
                "width": viewport[0],
                "height": viewport[1],
            },
            "full_page": full_page,
            "captured_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    payload["screenshots"] = sorted(screenshots, key=lambda item: str(item.get("path", "")))
    metadata_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return metadata_path


async def capture(args: argparse.Namespace) -> tuple[Path, Path]:
    repo_root = Path(args.repo_root).resolve()
    app_root = repo_root / "apps" / args.slug
    if not app_root.exists():
        raise FileNotFoundError(f"app dir not found: {app_root}")

    output_path = Path(args.output) if args.output else app_root / "acceptance" / f"{args.slug}-home.png"
    if not output_path.is_absolute():
        output_path = repo_root / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)

    viewport = args.viewport
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        page = await browser.new_page(
            viewport={"width": viewport[0], "height": viewport[1]},
            ignore_https_errors=True,
        )
        await page.goto(args.url, wait_until="domcontentloaded", timeout=args.timeout_ms)
        if args.wait_text:
            await page.get_by_text(args.wait_text, exact=False).first.wait_for(
                state="visible",
                timeout=args.timeout_ms,
            )
        else:
            await page.locator("body").wait_for(state="visible", timeout=args.timeout_ms)

        if args.dismiss_text:
            dismiss = page.get_by_role("button", name=args.dismiss_text)
            if await dismiss.count():
                await dismiss.first.click(timeout=5000)

        await page.screenshot(path=str(output_path), full_page=args.full_page)
        await browser.close()

    metadata_path = write_metadata(repo_root, app_root, output_path, args.url, viewport, args.full_page)
    return output_path, metadata_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture a web-page-only screenshot for LazyCat store assets.")
    parser.add_argument("slug")
    parser.add_argument("--url", required=True)
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--output", default="")
    parser.add_argument("--viewport", type=parse_viewport, default=(1280, 800))
    parser.add_argument("--wait-text", default="")
    parser.add_argument("--dismiss-text", default="Dismiss")
    parser.add_argument("--timeout-ms", type=int, default=60000)
    parser.add_argument("--full-page", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    screenshot_path, metadata_path = asyncio.run(capture(args))
    print(screenshot_path)
    print(metadata_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
