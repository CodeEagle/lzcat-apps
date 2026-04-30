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
    description = manifest_description(manifest, "zh") or manifest_description(manifest, "en")

    return f"""# {name} 懒猫微服使用攻略

> 一句话概览：{description or f"{name} 已完成懒猫微服适配，适合在自己的设备上长期运行。"}

## 适合谁

{name} 适合希望把开源应用放到懒猫微服里长期使用的人。它不是一次性的安装记录，而是一篇面向最终用户的上手攻略：先说明适用场景，再带用户完成第一条可验证的真实流程。

如果只是想确认应用能打开，看首页就够了；如果要写公开攻略，需要继续覆盖核心操作、执行中状态、结果页、设置页或进阶能力。

## 开始前先准备

1. 在懒猫微服中安装应用。
2. 打开 `https://{subdomain}.<你的盒子域名>/`。
3. 准备应用核心流程需要的测试数据、示例任务或 provider 配置。
4. 准备一组不含敏感信息的演示数据；后续截图只展示产品界面和示例状态。

## 01 首次打开：先确认主界面

打开应用后，先确认看到的是应用自己的主界面，而不是启动页、空白页、平台错误页或 5xx 错误页。

这一段应配一张干净的主界面截图，截图只保留产品 UI 和无敏感信息的示例状态。

## 02 第一条任务：用一个小目标跑通流程

第一条任务要小，目标要明确，最好能在几分钟内得到结果。写攻略时不要只说“输入内容并点击按钮”，要告诉用户什么样的输入更容易成功。

建议覆盖：

- 输入或创建示例任务。
- 启动执行、转换、生成、分析或同步动作。
- 观察执行中状态，而不只截最终结果。
- 回到列表、看板或历史记录确认任务可追踪。

## 03 结果页：确认产出真的可用

公开攻略需要展示“做完之后用户能得到什么”。如果应用有详情页、日志页、预览页、导出文件或提交记录，这里应该补一张结果截图。

截图说明要写成用户能理解的收益，例如“任务已进入 Done，详情页保留提交号和变更文件”。

## 04 设置与进阶玩法

如果应用有模型、账号、插件、runtime、外部服务或团队协作设置，应单独写一节。只说明设置入口、字段含义和推荐使用方式，不展示密钥、token、私有 URL 或真实账号。

当应用支持多后端或多员工模式时，建议写清楚每个选项适合什么场景，并提醒用户先用小任务试跑。

## 使用心得

- 先用小任务验证配置、权限、持久化目录和结果回写，再交给它处理真实工作。
- 截图要覆盖主界面、执行中、执行结果、详情/日志、设置/进阶能力，而不是只截空状态。
- 把排障信息改写成用户能行动的建议，正文只保留对使用有帮助的结论。

## 常见问题

- 如果页面打不开，先检查应用状态和容器日志。
- 如果页面能打开但主流程失败，先检查应用内错误提示、配置项和后台日志。
- 如果功能需要外部账号、API key 或持久化目录，先在懒猫应用详情中补齐配置再重试。
"""


def screenshot_references(app_root: Path, slug: str) -> list[str]:
    screenshot_sources = [
        (app_root / "copywriting" / "assets", "assets"),
        (app_root / "store" / "screenshots", "../store/screenshots"),
        (app_root / "acceptance", "../acceptance"),
    ]
    screenshots: list[tuple[Path, str]] = []
    for screenshot_dir, relative_prefix in screenshot_sources:
        if screenshot_dir.exists():
            screenshots.extend((path, relative_prefix) for path in sorted(screenshot_dir.glob("*.png")))
    if not screenshots:
        return [f"![应用界面](../acceptance/{slug}-home.png)"]
    return [f"![{path.stem}]({relative_prefix}/{path.name})" for path, relative_prefix in screenshots[:8]]


def build_playground_guide(slug: str, manifest: dict[str, Any], acceptance: dict[str, Any], app_root: Path) -> str:
    name = str(manifest.get("name", slug)).strip() or slug
    homepage = str(manifest.get("homepage", "")).strip()
    description = manifest_description(manifest, "zh") or manifest_description(manifest, "en")
    screenshots = screenshot_references(app_root, slug)
    first_image = screenshots[0]
    extra_images = "\n\n".join(screenshots[1:])

    return f"""# {name} 懒猫微服使用攻略

{first_image}

## 为什么值得装

{description or f"{name} 已经完成懒猫微服移植，适合在自己的设备上长期运行。"}

这个版本把上游项目打包成可以直接安装的懒猫应用，适合想要本地部署、随时打开、少折腾配置的用户。

## 安装后先做这件事

1. 在懒猫应用商店安装 `{name}`。
2. 打开应用入口，等待首页完成加载。
3. 准备一个不含敏感信息的示例输入、测试仓库或演示数据。
4. 跑通第一条核心流程，确认能看到执行进度和最终结果。

{extra_images}

## 上手路线

1. 先看主界面，确认核心导航和主要操作入口。
2. 创建第一条小任务或第一份示例数据。
3. 观察执行中状态，确认用户能理解当前进度。
4. 查看结果、详情、日志或导出物。
5. 再介绍设置、provider、插件、runtime 或高级协作方式。

## 使用心得

- 想把开源工具稳定放进自己的懒猫微服。
- 希望应用、数据和日常入口都留在本地设备。
- 建议稳定复盘主流程，而不是只展示空状态或安装成功。
- 进阶配置应先用小任务验证，避免一开始就接入真实客户数据或私有仓库。

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
