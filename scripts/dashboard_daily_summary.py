#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    from .discord_migration_notifier import DiscordClient
    from .project_config import load_project_config
except ImportError:  # pragma: no cover - direct script execution
    from discord_migration_notifier import DiscordClient
    from project_config import load_project_config


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def state_counts(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    return dict(sorted(Counter(str(item.get(key, "")).strip() or "unknown" for item in items).items()))


def build_top_candidates(candidates: list[dict[str, Any]], *, limit: int = 8) -> list[dict[str, Any]]:
    actionable = [item for item in candidates if str(item.get("status", "")).strip() in {"portable", "needs_review"}]
    ordered = sorted(
        actionable,
        key=lambda item: (-int(item.get("stars_today") or 0), -int(item.get("total_stars") or 0), str(item.get("full_name", "")).lower()),
    )
    return [
        {
            "full_name": str(item.get("full_name", "")).strip(),
            "status": str(item.get("status", "")).strip(),
            "description": str(item.get("description", "")).strip(),
            "stars_today": int(item.get("stars_today") or 0),
            "total_stars": int(item.get("total_stars") or 0),
            "repo_url": str(item.get("repo_url", "")).strip(),
        }
        for item in ordered[:limit]
        if str(item.get("full_name", "")).strip()
    ]


def build_daily_summary(repo_root: Path, *, report_date: str, now: str | None = None) -> dict[str, Any]:
    now = now or utc_now_iso()
    queue = read_json(repo_root / "registry" / "auto-migration" / "queue.json", {"items": []})
    publication = read_json(repo_root / "registry" / "status" / "local-publication-status.json", {"apps": {}})
    local_agent = read_json(repo_root / "registry" / "candidates" / "local-agent-latest.json", {"candidates": []})

    items = [item for item in queue.get("items", []) if isinstance(item, dict)]
    apps = publication.get("apps") if isinstance(publication.get("apps"), dict) else {}
    app_rows = [value for value in apps.values() if isinstance(value, dict)]
    local_candidates = [item for item in local_agent.get("candidates", []) if isinstance(item, dict)]
    waiting = [
        {
            "slug": str(item.get("slug", "")).strip(),
            "source": str(item.get("source", "")).strip(),
            "question": str((item.get("human_request") or {}).get("question", "")).strip()
            if isinstance(item.get("human_request"), dict)
            else "",
        }
        for item in items
        if item.get("state") == "waiting_for_human"
    ]
    failed = [
        {
            "slug": str(item.get("slug", "")).strip(),
            "source": str(item.get("source", "")).strip(),
            "state": str(item.get("state", "")).strip(),
            "last_error": str(item.get("last_error", "")).strip(),
        }
        for item in items
        if str(item.get("state", "")).strip() in {"build_failed", "browser_failed", "codex_failed"}
    ]
    return {
        "date": report_date,
        "generated_at": now,
        "queue": {"total": len(items), "state_counts": state_counts(items, "state")},
        "publication": {"total": len(app_rows), "status_counts": state_counts(app_rows, "status")},
        "local_agent": {"total": len(local_candidates), "status_counts": state_counts(local_candidates, "status")},
        "top_candidates": build_top_candidates(local_candidates),
        "waiting_for_human": waiting,
        "failed_items": failed[:10],
        "reward_opportunities": [
            "完成可上架应用的开发者后台提交",
            "为每个上架应用补齐 Playground 图文攻略",
            "补齐桌面 2 张、手机 3 张网页内截图",
            "把成功经验回写 template 分支提高下一次移植收益",
        ],
    }


def _format_counts(counts: dict[str, int]) -> str:
    if not counts:
        return "无"
    return "，".join(f"{key}: {value}" for key, value in counts.items())


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        f"# LazyCat 自动移植日报 - {summary['date']}",
        "",
        f"生成时间：{summary['generated_at']}",
        "",
        "## 总览",
        "",
        f"- 队列总数：{summary['queue']['total']}（{_format_counts(summary['queue']['state_counts'])}）",
        f"- LocalAgent 候选：{summary['local_agent']['total']}（{_format_counts(summary['local_agent']['status_counts'])}）",
        f"- 已发布跟踪：{summary['publication']['total']}（{_format_counts(summary['publication']['status_counts'])}）",
        "",
        "## 等待我回复",
    ]
    waiting = summary.get("waiting_for_human") or []
    if waiting:
        for item in waiting:
            lines.append(f"- {item['slug'] or item['source']}：{item['question']}")
    else:
        lines.append("- 无")

    lines.extend(["", "## 失败待处理"])
    failed = summary.get("failed_items") or []
    if failed:
        for item in failed:
            lines.append(f"- {item['slug'] or item['source']}：{item['state']} {item['last_error']}".rstrip())
    else:
        lines.append("- 无")

    lines.extend(["", "## 今日优先候选"])
    top_candidates = summary.get("top_candidates") or []
    if top_candidates:
        for item in top_candidates:
            star_text = f"+{item['stars_today']} today / {item['total_stars']} total"
            lines.append(f"- [{item['full_name']}]({item['repo_url']})：{item['status']}，{star_text}")
    else:
        lines.append("- 无")

    lines.extend(["", "## 收益动作"])
    for item in summary.get("reward_opportunities") or []:
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


def write_daily_summary(repo_root: Path, summary: dict[str, Any]) -> dict[str, Path]:
    dashboard_root = repo_root / "registry" / "dashboard"
    daily_root = dashboard_root / "daily"
    daily_root.mkdir(parents=True, exist_ok=True)
    date = str(summary["date"])
    daily_json = daily_root / f"{date}.json"
    daily_markdown = daily_root / f"{date}.md"
    latest_json = dashboard_root / "latest.json"
    latest_markdown = dashboard_root / "latest.md"
    markdown = render_markdown(summary)
    for path, content in [
        (daily_json, json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n"),
        (latest_json, json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n"),
        (daily_markdown, markdown),
        (latest_markdown, markdown),
    ]:
        temp_path = path.with_suffix(path.suffix + ".tmp")
        temp_path.write_text(content, encoding="utf-8")
        temp_path.replace(path)
    return {"daily_json": daily_json, "daily_markdown": daily_markdown, "latest_json": latest_json, "latest_markdown": latest_markdown}


def publish_dashboard_to_discord(repo_root: Path, markdown: str, *, token: str, guild_id: str, category_id: str, channel_name: str) -> dict[str, str]:
    client = DiscordClient(token)
    channel = client.ensure_text_channel(guild_id, category_id, channel_name, topic="LazyCat auto-migration daily dashboard")
    channel_id = str(channel.get("id", "")).strip()
    state_path = repo_root / "registry" / "dashboard" / "discord-state.json"
    state = read_json(state_path, {})
    message_id = str(state.get("message_id", "")).strip()
    content = markdown[:1980]
    if message_id and state.get("channel_id") == channel_id:
        message = client.edit_message(channel_id, message_id, content)
    else:
        message = client.send_message(channel_id, content)
    next_state = {"channel_id": channel_id, "message_id": str(message.get("id", message_id)).strip()}
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(next_state, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return next_state


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate the LazyCat auto-migration daily dashboard.")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--date", default=datetime.now().astimezone().date().isoformat())
    parser.add_argument("--publish-discord", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    summary = build_daily_summary(repo_root, report_date=args.date)
    paths = write_daily_summary(repo_root, summary)
    if args.publish_discord:
        config = load_project_config(repo_root)
        token = os.environ.get("LZCAT_DISCORD_BOT_TOKEN", "").strip()
        if token and config.discord.enabled and config.discord.guild_id:
            publish_dashboard_to_discord(
                repo_root,
                render_markdown(summary),
                token=token,
                guild_id=config.discord.guild_id,
                category_id=config.discord.category_id,
                channel_name="migration-dashboard",
            )
    print(json.dumps({key: str(value) for key, value in paths.items()}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
