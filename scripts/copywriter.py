#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

try:
    from .run_build import browser_acceptance_allows_publish
except ImportError:  # pragma: no cover - direct script execution
    from run_build import browser_acceptance_allows_publish


def read_manifest(app_root: Path) -> dict[str, Any]:
    payload = yaml.safe_load((app_root / "lzc-manifest.yml").read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def read_acceptance(app_root: Path) -> dict[str, Any]:
    for path in (app_root / "acceptance" / "browser-use-result.json", app_root / ".browser-acceptance.json"):
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
    return {}


def read_readme_excerpt(app_root: Path) -> str:
    readme_path = app_root / "README.md"
    if not readme_path.exists():
        return ""
    lines = [line.strip() for line in readme_path.read_text(encoding="utf-8").splitlines()]
    useful = [line for line in lines if line and not line.startswith("#")]
    return "\n".join(useful[:12])


def manifest_description(manifest: dict[str, Any], locale: str) -> str:
    locales = manifest.get("locales")
    if isinstance(locales, dict):
        locale_payload = locales.get(locale)
        if isinstance(locale_payload, dict):
            description = str(locale_payload.get("description", "")).strip()
            if description:
                return description
    return str(manifest.get("description", "")).strip()


def acceptance_evidence(acceptance: dict[str, Any]) -> str:
    checks = acceptance.get("checks")
    if isinstance(checks, list):
        for check in checks:
            if isinstance(check, dict):
                evidence = str(check.get("evidence", "")).strip()
                if evidence:
                    return evidence
    return "Codex Browser Use 已确认页面渲染、无阻塞 console/network 错误，并完成主流程验收。"


def build_store_copy(slug: str, manifest: dict[str, Any], acceptance: dict[str, Any], readme_excerpt: str) -> str:
    name = str(manifest.get("name", slug)).strip() or slug
    package = str(manifest.get("package", "")).strip()
    version = str(manifest.get("version", "")).strip()
    homepage = str(manifest.get("homepage", "")).strip()
    description_en = manifest_description(manifest, "en")
    description_zh = manifest_description(manifest, "zh")
    evidence = acceptance_evidence(acceptance)

    return f"""# {name} 上架文案

## 基础信息

- App: {name}
- Slug: `{slug}`
- Package: `{package}`
- Version: `{version}`
- Homepage: {homepage}

## 一句话卖点

{description_zh or description_en or f"{name} 的懒猫微服版本。"}

## 应用商店描述

{description_zh or description_en or f"{name} 已完成懒猫微服适配，可在本地设备中运行。"}

## English Description

{description_en or description_zh or f"{name} packaged for LazyCat."}

## 关键词

`{slug}`, `LazyCat`, `self-hosted`, `自动移植`, `本地部署`

## Browser Use 验收证据

{evidence}

## README 可复用素材

{readme_excerpt or "README 暂无可复用摘要，请补充主流程、配置项和常见问题。"}

## 收益素材清单

- [ ] 应用功能截图：主页、核心操作、成功结果页
- [ ] 1 分钟教程：安装后第一步、核心任务、结果确认
- [ ] 功能亮点：为什么适合懒猫微服、哪些场景能节省时间
- [ ] 验收证据：Browser Use 通过、无阻塞 console/network 错误
- [ ] 上游依据：版本、许可证、主页、关键部署说明
"""


def build_tutorial(slug: str, manifest: dict[str, Any], acceptance: dict[str, Any]) -> str:
    name = str(manifest.get("name", slug)).strip() or slug
    subdomain = str(manifest.get("application", {}).get("subdomain", slug)).strip() if isinstance(manifest.get("application"), dict) else slug
    evidence = acceptance_evidence(acceptance)

    return f"""# {name} 使用教程

## 适用人群

适合希望在懒猫微服中本地运行 `{name}`，并通过浏览器完成核心工作流的用户。

## 安装后第一步

1. 在懒猫微服中安装应用。
2. 打开 `https://{subdomain}.<你的盒子域名>/`。
3. 确认页面不是空白页、平台错误页或 5xx 错误页。

## 核心流程

1. 打开应用首页。
2. 按页面上的主要输入区填写或上传内容。
3. 执行主操作。
4. 确认结果区域出现可用输出。

## 验收记录

{evidence}

## 常见问题

- 如果页面打不开，先检查应用状态和容器日志。
- 如果页面能打开但主流程失败，检查 Browser Use 记录里的 console/network 错误。
- 如果功能需要外部账号、API key 或持久化目录，先在懒猫应用详情中补齐配置再重试。

## 上架收益提示

- 教程应配套截图或短视频，展示“安装后 1 分钟内完成第一件事”。
- 每次迁移完成后都要补齐教程、验收证据和功能亮点，避免只上架一个技术包装。
"""


def screenshot_references(app_root: Path, slug: str) -> list[str]:
    screenshot_dir = app_root / "acceptance"
    screenshots = sorted(screenshot_dir.glob("*.png")) if screenshot_dir.exists() else []
    if not screenshots:
        return [f"![应用界面](../acceptance/{slug}-home.png)"]
    return [f"![{path.stem}](../acceptance/{path.name})" for path in screenshots[:5]]


def build_playground_guide(slug: str, manifest: dict[str, Any], acceptance: dict[str, Any], app_root: Path) -> str:
    name = str(manifest.get("name", slug)).strip() or slug
    homepage = str(manifest.get("homepage", "")).strip()
    description = manifest_description(manifest, "zh") or manifest_description(manifest, "en")
    evidence = acceptance_evidence(acceptance)
    screenshots = screenshot_references(app_root, slug)
    first_image = screenshots[0]
    extra_images = "\n\n".join(screenshots[1:])

    return f"""# 在懒猫微服上使用 {name}

{first_image}

## 为什么值得装

{description or f"{name} 已经完成懒猫微服移植，适合在自己的设备上长期运行。"}

这个版本把上游项目打包成可以直接安装的懒猫应用，适合想要本地部署、随时打开、少折腾配置的用户。

## 安装后先做这件事

1. 在懒猫应用商店安装 `{name}`。
2. 打开应用入口，等待首页完成加载。
3. 按页面主流程输入或上传内容。
4. 看到结果区出现有效输出后，就可以把它加入日常工作流。

{extra_images}

## 我们验证了什么

{evidence}

## 适合这些场景

- 想把开源工具稳定放进自己的懒猫微服。
- 希望应用、数据和日常入口都留在本地设备。
- 需要一个已经经过 Browser Use 验收的可用版本。

## 上游信息

- 项目主页：{homepage}
- 懒猫版本会尽量保持上游能力和原作者信息，不把移植包声明为原创应用。
"""


def build_copywriting_package(repo_root: Path, slug: str) -> dict[str, str]:
    app_root = repo_root / "apps" / slug
    allowed, reason = browser_acceptance_allows_publish(app_root)
    if not allowed:
        raise ValueError(f"copywriting blocked until Browser Use acceptance passes: {reason}")

    manifest = read_manifest(app_root)
    acceptance = read_acceptance(app_root)
    readme_excerpt = read_readme_excerpt(app_root)
    return {
        "store_copy": build_store_copy(slug, manifest, acceptance, readme_excerpt),
        "tutorial": build_tutorial(slug, manifest, acceptance),
        "playground": build_playground_guide(slug, manifest, acceptance, app_root),
    }


def write_copywriting_package(repo_root: Path, slug: str) -> dict[str, Path]:
    app_root = repo_root / "apps" / slug
    output_dir = app_root / "copywriting"
    output_dir.mkdir(parents=True, exist_ok=True)
    package = build_copywriting_package(repo_root, slug)
    store_copy_path = output_dir / "store-copy.md"
    tutorial_path = output_dir / "tutorial.md"
    playground_path = output_dir / "playground.md"
    store_copy_path.write_text(package["store_copy"], encoding="utf-8")
    tutorial_path.write_text(package["tutorial"], encoding="utf-8")
    playground_path.write_text(package["playground"], encoding="utf-8")
    return {"store_copy": store_copy_path, "tutorial": tutorial_path, "playground": playground_path}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate post-acceptance store copy and tutorial drafts.")
    parser.add_argument("slug")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        paths = write_copywriting_package(Path(args.repo_root).resolve(), args.slug)
    except ValueError as exc:
        print(exc)
        return 2
    print(paths["store_copy"])
    print(paths["tutorial"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
