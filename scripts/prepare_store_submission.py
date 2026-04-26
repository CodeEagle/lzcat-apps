#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import zipfile
from pathlib import Path
from typing import Any

import yaml

try:
    from .project_config import load_project_config
    from .run_build import browser_acceptance_allows_publish
except ImportError:  # pragma: no cover - direct script execution
    from project_config import load_project_config
    from run_build import browser_acceptance_allows_publish


def read_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_lpk_manifest(lpk_path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(lpk_path) as archive:
        with archive.open("manifest.yml") as handle:
            payload = yaml.safe_load(handle.read().decode("utf-8"))
    return payload if isinstance(payload, dict) else {}


def section(markdown: str, title: str) -> str:
    pattern = re.compile(rf"^##\s+{re.escape(title)}\s*$", re.MULTILINE)
    match = pattern.search(markdown)
    if not match:
        return ""
    next_match = re.search(r"^##\s+", markdown[match.end() :], re.MULTILINE)
    end = match.end() + next_match.start() if next_match else len(markdown)
    return markdown[match.end() : end].strip()


def parse_keywords(markdown: str) -> list[str]:
    keyword_block = section(markdown, "关键词")
    return [item.strip() for item in re.findall(r"`([^`]+)`", keyword_block) if item.strip()]


def first_nonempty_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("- "):
            return stripped
    return ""


def relative_to_repo(repo_root: Path, path: Path) -> str:
    return str(path.resolve().relative_to(repo_root.resolve()))


def copy_asset(source: Path, output_dir: Path, filename: str | None = None) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    dest = output_dir / (filename or source.name)
    shutil.copy2(source, dest)
    return dest


def validate_web_screenshots(repo_root: Path, app_root: Path, screenshot_paths: list[Path]) -> Path:
    metadata_path = app_root / "acceptance" / "web-screenshots.json"
    if not metadata_path.exists():
        raise RuntimeError(
            "store screenshots must be captured from the web page content area; "
            "run scripts/capture_web_screenshot.py before preparing submission materials"
        )
    metadata = read_json(metadata_path)
    if metadata.get("capture_method") != "playwright_page_screenshot":
        raise RuntimeError("web screenshot metadata has an unsupported capture_method")
    records = metadata.get("screenshots", [])
    if not isinstance(records, list):
        raise RuntimeError("web screenshot metadata screenshots must be a list")
    recorded_paths = {
        str(item.get("path", "")).strip()
        for item in records
        if isinstance(item, dict)
    }
    expected_paths = {relative_to_repo(repo_root, path) for path in screenshot_paths}
    missing = sorted(expected_paths - recorded_paths)
    if missing:
        raise RuntimeError(
            "acceptance screenshots are missing web-page capture metadata: "
            + ", ".join(missing)
        )
    return metadata_path


def build_submission(repo_root: Path, slug: str, developer_url: str, output_dir: Path) -> dict[str, Any]:
    app_root = repo_root / "apps" / slug
    if not app_root.exists():
        raise FileNotFoundError(f"app dir not found: {app_root}")

    allowed, reason = browser_acceptance_allows_publish(app_root)
    if not allowed:
        raise RuntimeError(f"store submission blocked until Browser Use acceptance passes: {reason}")

    manifest = read_yaml(app_root / "lzc-manifest.yml")
    lpk_path = repo_root / "dist" / f"{slug}.lpk"
    if not lpk_path.exists():
        raise FileNotFoundError(f"verified lpk not found: {lpk_path}")
    lpk_manifest = inspect_lpk_manifest(lpk_path)

    package = str(manifest.get("package", "")).strip()
    version = str(manifest.get("version", "")).strip()
    if package != str(lpk_manifest.get("package", "")).strip():
        raise RuntimeError("lpk manifest package does not match app manifest")
    if version != str(lpk_manifest.get("version", "")).strip():
        raise RuntimeError("lpk manifest version does not match app manifest")

    icon_path = app_root / "icon.png"
    if not icon_path.exists():
        raise FileNotFoundError(f"icon not found: {icon_path}")

    screenshot_paths = sorted((app_root / "acceptance").glob("*.png"))
    if not screenshot_paths:
        raise FileNotFoundError(f"no acceptance screenshots found under {app_root / 'acceptance'}")
    web_screenshot_metadata_path = validate_web_screenshots(repo_root, app_root, screenshot_paths)
    materialized_assets_dir = output_dir / "assets"
    materialized_icon_path = copy_asset(icon_path, materialized_assets_dir, "icon.png")
    materialized_screenshot_paths = [
        copy_asset(path, materialized_assets_dir / "screenshots") for path in screenshot_paths
    ]

    store_copy_path = app_root / "copywriting" / "store-copy.md"
    tutorial_path = app_root / "copywriting" / "tutorial.md"
    if not store_copy_path.exists():
        raise FileNotFoundError(f"store copy not found: {store_copy_path}")
    if not tutorial_path.exists():
        raise FileNotFoundError(f"tutorial not found: {tutorial_path}")
    store_copy = store_copy_path.read_text(encoding="utf-8")

    acceptance_path = app_root / "acceptance" / "browser-use-result.json"
    acceptance = read_json(acceptance_path) if acceptance_path.exists() else {}

    title = str(manifest.get("name", slug)).strip() or slug
    zh_locale = manifest.get("locales", {}).get("zh", {}) if isinstance(manifest.get("locales"), dict) else {}
    en_locale = manifest.get("locales", {}).get("en", {}) if isinstance(manifest.get("locales"), dict) else {}

    return {
        "schema_version": 1,
        "slug": slug,
        "developer_apps_url": developer_url,
        "package": package,
        "name": title,
        "version": version,
        "homepage": str(manifest.get("homepage", "")).strip(),
        "license": str(manifest.get("license", "")).strip(),
        "short_description": first_nonempty_line(section(store_copy, "一句话卖点")),
        "description_zh": str(zh_locale.get("description", manifest.get("description", ""))).strip(),
        "description_en": str(en_locale.get("description", manifest.get("description", ""))).strip(),
        "store_description": section(store_copy, "应用商店描述"),
        "english_description": section(store_copy, "English Description"),
        "keywords": parse_keywords(store_copy),
        "lpk": {
            "path": relative_to_repo(repo_root, lpk_path),
            "sha256": file_sha256(lpk_path),
            "size_bytes": lpk_path.stat().st_size,
            "manifest": {
                "name": str(lpk_manifest.get("name", "")).strip(),
                "package": str(lpk_manifest.get("package", "")).strip(),
                "version": str(lpk_manifest.get("version", "")).strip(),
            },
        },
        "assets": {
            "icon": relative_to_repo(repo_root, materialized_icon_path),
            "screenshots": [relative_to_repo(repo_root, path) for path in materialized_screenshot_paths],
            "source_icon": relative_to_repo(repo_root, icon_path),
            "source_screenshots": [relative_to_repo(repo_root, path) for path in screenshot_paths],
            "web_screenshot_metadata": relative_to_repo(repo_root, web_screenshot_metadata_path),
            "store_copy": relative_to_repo(repo_root, store_copy_path),
            "tutorial": relative_to_repo(repo_root, tutorial_path),
        },
        "browser_acceptance": {
            "status": str(acceptance.get("status", "")).strip(),
            "result_path": relative_to_repo(repo_root, acceptance_path) if acceptance_path.exists() else "",
            "evidence": (
                acceptance.get("checks", [{}])[0].get("evidence", "")
                if isinstance(acceptance.get("checks"), list) and acceptance.get("checks")
                else ""
            ),
        },
        "submission_steps": [
            "Open the configured LazyCat developer apps page.",
            "Create a new app entry.",
            "Fill name, package id, version, descriptions, keywords, homepage, and license from this JSON.",
            "Upload icon and screenshots from assets.",
            "Upload the verified LPK from lpk.path.",
            "Stop before the final create/submit/publish action and ask for confirmation.",
        ],
    }


def write_checklist(repo_root: Path, output_dir: Path, submission: dict[str, Any]) -> Path:
    checklist_path = output_dir / "checklist.md"
    screenshots = "\n".join(f"- `{item}`" for item in submission["assets"]["screenshots"])
    keywords = ", ".join(submission["keywords"])
    checklist = f"""# {submission["name"]} LazyCat 上架提交清单

## 开发者入口

- Developer Apps: {submission["developer_apps_url"]}

## 应用资料

- Name: {submission["name"]}
- Package: `{submission["package"]}`
- Version: `{submission["version"]}`
- Homepage: {submission["homepage"]}
- License: {submission["license"]}
- Keywords: {keywords}

## 需要上传的文件

- LPK: `{submission["lpk"]["path"]}`
- LPK sha256: `{submission["lpk"]["sha256"]}`
- Icon: `{submission["assets"]["icon"]}`
- Screenshots:
{screenshots}
- Web screenshot metadata: `{submission["assets"]["web_screenshot_metadata"]}`

## 文案来源

- Store copy: `{submission["assets"]["store_copy"]}`
- Tutorial: `{submission["assets"]["tutorial"]}`

## 验收门禁

- Browser Use status: `{submission["browser_acceptance"]["status"]}`
- Browser Use result: `{submission["browser_acceptance"]["result_path"]}`

## 浏览器提交流程

1. 打开开发者入口。
2. 新建 App。
3. 填写应用名、包名、版本、简介、详情、关键词、主页和许可证。
4. 上传图标、截图和已验证 LPK。
5. 停在最终创建/提交/发布按钮前，等待用户确认。
6. 用户确认后再提交，并记录后台返回的状态或详情页链接。
"""
    checklist_path.write_text(checklist, encoding="utf-8")
    return checklist_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare LazyCat App Store submission materials for a verified app.")
    parser.add_argument("slug")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--developer-url", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    config = load_project_config(repo_root)
    developer_url = args.developer_url.strip() or config.lazycat.developer_apps_url
    if not developer_url:
        raise SystemExit("developer url is required; set project-config.json lazycat.developer_apps_url or pass --developer-url")

    output_dir = repo_root / "apps" / args.slug / "store-submission"
    output_dir.mkdir(parents=True, exist_ok=True)
    submission = build_submission(repo_root, args.slug, developer_url, output_dir)

    submission_path = output_dir / "submission.json"
    submission_path.write_text(json.dumps(submission, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    checklist_path = write_checklist(repo_root, output_dir, submission)
    print(submission_path)
    print(checklist_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
