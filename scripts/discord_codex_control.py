#!/usr/bin/env python3

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import socket
import ssl
import struct
import subprocess
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

try:
    from .discord_migration_notifier import (
        DISCORD_GUILD_TEXT_TYPE,
        MAX_DISCORD_MESSAGE_LENGTH,
        DiscordClient,
    )
    from .migration_workspace import migration_workspace_path, normalize_slug
    from .project_config import load_project_config
except ImportError:  # pragma: no cover - direct script execution
    from discord_migration_notifier import (
        DISCORD_GUILD_TEXT_TYPE,
        MAX_DISCORD_MESSAGE_LENGTH,
        DiscordClient,
    )
    from migration_workspace import migration_workspace_path, normalize_slug
    from project_config import load_project_config


DEFAULT_QUEUE_PATH = "registry/auto-migration/queue.json"
DEFAULT_STATE_PATH = "registry/auto-migration/discord-codex-control.json"
DEFAULT_TASK_ROOT = "registry/auto-migration/codex-control-tasks"
DEFAULT_MANUAL_EXCLUSIONS_PATH = "registry/auto-migration/manual-exclusions.json"
DEFAULT_CODEX_MODEL = "gpt-5.5"
DEFAULT_CODEX_FALLBACK_MODEL = "gpt-5.4"
DISCORD_GATEWAY_HOST = "gateway.discord.gg"
DISCORD_GATEWAY_PATH = "/?v=10&encoding=json"
DISCORD_GATEWAY_GUILDS_INTENT = 1 << 0
DISCORD_GATEWAY_GUILD_MESSAGES_INTENT = 1 << 9
DISCORD_GATEWAY_MESSAGE_CONTENT_INTENT = 1 << 15
ACK_REACTION = "%E2%9C%85"
WORKER_REACTION = "%F0%9F%9A%80"
CONTROL_CHANNEL_NAME = "migration-control"
CONTROL_ONLY_SUFFIXES = {"control", "dashboard", "local-agent", "codex-control"}
DASHBOARD_CHANNEL_NAME = "dashboard"

CodexRunner = Callable[["CodexControlTask"], "CodexControlRunResult"]


@dataclass(frozen=True)
class CodexControlConfig:
    repo_root: Path
    queue_path: Path = Path(DEFAULT_QUEUE_PATH)
    state_path: Path = Path(DEFAULT_STATE_PATH)
    task_root: Path = Path(DEFAULT_TASK_ROOT)
    workspace_root: Path = Path("")
    guild_id: str = ""
    category_id: str = ""
    channel_prefix: str = "migration"
    control_channel: str = CONTROL_CHANNEL_NAME
    bot_user_id: str = ""
    mention_role_ids: tuple[str, ...] = ()
    model: str = DEFAULT_CODEX_MODEL
    execute: bool = True


@dataclass(frozen=True)
class ParsedCommand:
    kind: str
    instruction: str = ""


@dataclass(frozen=True)
class ChannelContext:
    channel_id: str
    channel_name: str
    scope: str
    slug: str = ""
    item: dict[str, Any] | None = None
    workdir: Path = Path("")


@dataclass(frozen=True)
class CommandResult:
    status: str
    reply: str = ""
    delete_channel_id: str = ""


@dataclass(frozen=True)
class CodexControlTask:
    instruction: str
    context: ChannelContext
    config: CodexControlConfig
    task_dir: Path
    prompt: str
    command: list[str]
    now: str


@dataclass(frozen=True)
class CodexControlRunResult:
    status: str
    returncode: int
    summary: str
    task_dir: Path


@dataclass(frozen=True)
class ChannelMessageBatch:
    index: int
    context: ChannelContext
    channel_state: dict[str, Any]
    last_message_id: str
    messages: list[dict[str, Any]]
    error: str = ""


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_path(repo_root: Path, path: Path | str) -> Path:
    value = Path(path).expanduser()
    if value.is_absolute():
        return value
    return repo_root / value


def has_path(value: Path | str) -> bool:
    return str(value).strip() not in {"", "."}


def read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else default


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp_path.replace(path)


def read_text_if_exists(path: Path, *, max_chars: int = 12000) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]


def safe_task_name(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z_.-]+", "-", value).strip("-").lower() or "unknown"


def truncate_reply(content: str) -> str:
    if len(content) <= MAX_DISCORD_MESSAGE_LENGTH:
        return content
    return content[: MAX_DISCORD_MESSAGE_LENGTH - 20].rstrip() + "\n...[truncated]"


def is_bot_message(message: dict[str, Any]) -> bool:
    author = message.get("author") if isinstance(message.get("author"), dict) else {}
    return bool(author.get("bot"))


def message_sort_key(message: dict[str, Any]) -> int:
    message_id = str(message.get("id", "")).strip()
    return int(message_id) if message_id.isdigit() else 0


def order_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if all(str(message.get("id", "")).strip().isdigit() for message in messages):
        return sorted(messages, key=message_sort_key)
    return messages


def queue_items(config: CodexControlConfig) -> list[dict[str, Any]]:
    payload = read_json(resolve_path(config.repo_root, config.queue_path), {"items": []})
    items = payload.get("items")
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def find_queue_item_by_slug(items: list[dict[str, Any]], slug: str) -> dict[str, Any] | None:
    normalized = normalize_slug(slug)
    for item in items:
        item_slug = normalize_slug(str(item.get("slug") or item.get("source") or item.get("id") or ""))
        if item_slug == normalized:
            return item
        source_tail = normalize_slug(str(item.get("source", "")).rsplit("/", 1)[-1])
        if source_tail == normalized:
            return item
    return None


def item_counts(items: list[dict[str, Any]]) -> str:
    counts = Counter(str(item.get("state", "")).strip() or "unknown" for item in items)
    return ", ".join(f"{name}={count}" for name, count in sorted(counts.items())) or "none"


def slug_from_channel_name(channel_name: str, config: CodexControlConfig) -> str:
    normalized_name = normalize_slug(channel_name)
    control_name = normalize_slug(config.control_channel)
    if normalized_name == control_name:
        return ""
    prefix = normalize_slug(config.channel_prefix) or "migration"
    prefix_with_dash = f"{prefix}-"
    if not normalized_name.startswith(prefix_with_dash):
        return ""
    suffix = normalized_name[len(prefix_with_dash) :]
    if suffix in CONTROL_ONLY_SUFFIXES:
        return ""
    return suffix


def dashboard_channel_name() -> str:
    return DASHBOARD_CHANNEL_NAME


def build_workdir(config: CodexControlConfig, slug: str, item: dict[str, Any] | None) -> Path:
    if not slug:
        return config.repo_root
    if item:
        workspace_path = str(item.get("workspace_path", "")).strip()
        if workspace_path:
            return resolve_path(config.repo_root, workspace_path)
    workspace_root = resolve_path(config.repo_root, config.workspace_root) if has_path(config.workspace_root) else Path("")
    if has_path(workspace_root):
        candidate = migration_workspace_path(workspace_root, slug)
        if candidate.exists():
            return candidate
    return config.repo_root


def channel_context(channel: dict[str, Any], config: CodexControlConfig, items: list[dict[str, Any]]) -> ChannelContext | None:
    if channel.get("type") != DISCORD_GUILD_TEXT_TYPE:
        return None
    if config.category_id and channel.get("parent_id") != config.category_id:
        return None
    channel_id = str(channel.get("id", "")).strip()
    channel_name = str(channel.get("name", "")).strip()
    if not channel_id or not channel_name:
        return None
    if normalize_slug(channel_name) == normalize_slug(config.control_channel):
        return ChannelContext(channel_id=channel_id, channel_name=channel_name, scope="control", workdir=config.repo_root)
    if normalize_slug(channel_name) == normalize_slug(dashboard_channel_name()):
        return ChannelContext(
            channel_id=channel_id,
            channel_name=channel_name,
            scope="dashboard",
            slug=DASHBOARD_CHANNEL_NAME,
            workdir=config.repo_root,
        )
    slug = slug_from_channel_name(channel_name, config)
    if not slug:
        return None
    item = find_queue_item_by_slug(items, slug)
    return ChannelContext(
        channel_id=channel_id,
        channel_name=channel_name,
        scope="migration",
        slug=slug,
        item=item,
        workdir=build_workdir(config, slug, item),
    )


def discover_channels(config: CodexControlConfig, client: DiscordClient) -> list[ChannelContext]:
    if not config.guild_id:
        return []
    items = queue_items(config)
    channels = client.list_guild_channels(config.guild_id)
    if not any(
        channel.get("type") == DISCORD_GUILD_TEXT_TYPE
        and str(channel.get("name", "")).strip() == config.control_channel
        and (not config.category_id or channel.get("parent_id") == config.category_id)
        for channel in channels
    ):
        control = client.ensure_text_channel(
            config.guild_id,
            config.category_id,
            config.control_channel,
            topic="LazyCat Codex control channel",
        )
        if not any(str(channel.get("id", "")).strip() == str(control.get("id", "")).strip() for channel in channels):
            channels.append(control)
    contexts: list[ChannelContext] = []
    seen: set[str] = set()
    for channel in channels:
        context = channel_context(channel, config, items)
        if not context or context.channel_id in seen:
            continue
        seen.add(context.channel_id)
        contexts.append(context)
    return contexts


def strip_bot_mention(content: str, bot_user_id: str) -> tuple[bool, str]:
    match = re.match(r"^<@!?(\d+)>\s*(.*)$", content.strip(), flags=re.S)
    if not match:
        return False, content.strip()
    mentioned_id = match.group(1)
    if not bot_user_id or mentioned_id != bot_user_id:
        return False, content.strip()
    return True, match.group(2).strip()


def parse_control_command(content: str, *, bot_user_id: str = "") -> ParsedCommand | None:
    mentioned, remainder = strip_bot_mention(content, bot_user_id)
    text = remainder.strip()
    if mentioned:
        if not text or text.lower() in {"help", "h", "?"}:
            return ParsedCommand("help")
        if text.lower() in {"status", "状态"}:
            return ParsedCommand("status")
        return ParsedCommand("codex", text)

    parts = text.split(maxsplit=1)
    if not parts:
        return None
    prefix = parts[0].lower()
    rest = parts[1].strip() if len(parts) > 1 else ""

    if prefix in {"!help", "/help"}:
        return ParsedCommand("help")
    if prefix in {"!status", "/status"}:
        return ParsedCommand("status")
    if prefix in {"!codex", "/codex"}:
        lowered = rest.lower()
        if not rest or lowered in {"help", "h", "?"}:
            return ParsedCommand("help")
        if lowered in {"status", "状态"}:
            return ParsedCommand("status")
        return ParsedCommand("codex", rest)
    if prefix in {"!fix", "/fix"}:
        instruction = rest or "排查并修复当前迁移频道对应项目的失败，跑必要验证，并把结果写清楚。"
        return ParsedCommand("codex", instruction)
    if prefix in {"!retry", "/retry"}:
        instruction = rest or "继续处理当前迁移，优先复现最近失败、修复问题并重跑必要验证。"
        return ParsedCommand("codex", instruction)
    if prefix in {"!filter-close", "/filter-close", "!drop", "/drop"}:
        instruction = rest or "filter_and_cleanup_current_migration"
        return ParsedCommand("filter_cleanup", instruction)
    return None


def strip_role_mention(content: str, role_ids: tuple[str, ...]) -> tuple[bool, str]:
    text = content.strip()
    for role_id in role_ids:
        prefix = f"<@&{role_id}>"
        if text.startswith(prefix):
            return True, text.removeprefix(prefix).strip()
    return False, text


def message_mentions_bot(message: dict[str, Any], bot_user_id: str) -> bool:
    if not bot_user_id:
        return False
    mentions = message.get("mentions") if isinstance(message.get("mentions"), list) else []
    for mention in mentions:
        if isinstance(mention, dict) and str(mention.get("id", "")).strip() == bot_user_id:
            return True
    return False


def message_mentions_role(message: dict[str, Any], role_ids: tuple[str, ...]) -> bool:
    if not role_ids:
        return False
    mention_roles = message.get("mention_roles") if isinstance(message.get("mention_roles"), list) else []
    mentioned = {str(role_id).strip() for role_id in mention_roles}
    return bool(mentioned.intersection(role_ids))


def parse_mention_remainder(remainder: str) -> ParsedCommand:
    text = remainder.strip()
    if not text or text.lower() in {"help", "h", "?"}:
        return ParsedCommand("help")
    if text.lower() in {"status", "状态"}:
        return ParsedCommand("status")
    return ParsedCommand("codex", text)


def parse_control_message(message: dict[str, Any], config: CodexControlConfig) -> ParsedCommand | None:
    content = str(message.get("content", "")).strip()
    role_mentioned, role_remainder = strip_role_mention(content, config.mention_role_ids)
    if role_mentioned:
        return parse_mention_remainder(role_remainder)
    parsed = parse_control_command(content, bot_user_id=config.bot_user_id)
    if parsed:
        return parsed
    if not content and (
        message_mentions_bot(message, config.bot_user_id) or message_mentions_role(message, config.mention_role_ids)
    ):
        return ParsedCommand("content_unavailable")
    return None


def build_help_reply() -> str:
    return "\n".join(
        [
            "**Codex 控制指令**",
            "`!status` 查看当前频道绑定的迁移项目和 worktree",
            "`!codex <需求>` 让 Codex 在当前频道上下文中执行任务",
            "`!fix <问题>` 针对当前迁移项目排查修复",
            "`!retry` 让 Codex 接着当前失败继续处理",
            "`!filter-close` 把当前 repo 加入过滤名单并清理频道/worktree/branch/痕迹",
            "`@Bot <需求>` 也可以直接唤起 Codex",
        ]
    )


def build_content_unavailable_reply() -> str:
    return "\n".join(
        [
            "**我收到了 @，但 Discord 没把正文传给我。**",
            "这通常是 bot 没开启 Message Content Intent，或者你 @ 到的是 role 但正文被 API 隐藏了。",
            "现在我只能确认你唤起了我，不能知道要交给 Codex 的具体任务。",
            "",
            "处理方式：到 Discord Developer Portal 给 `Codex-Agent-Cat` 开启 `Message Content Intent`，然后重新发 `!fix <问题>` 或 `@Codex-Agent-Cat <需求>`。",
        ]
    )


def build_status_reply(context: ChannelContext, config: CodexControlConfig) -> str:
    items = queue_items(config)
    if context.scope == "control":
        active = [item for item in items if str(item.get("state", "")).strip() not in {"filtered_out", "excluded", "published"}]
        return "\n".join(
            [
                "**Codex 控制台状态**",
                f"- repo：{config.repo_root}",
                f"- 队列：{len(items)}（{item_counts(items)}）",
                f"- 活跃候选：{len(active)}",
                f"- 任务目录：{resolve_path(config.repo_root, config.task_root)}",
                f"- 默认模型：{config.model}",
            ]
        )
    if context.scope == "dashboard":
        latest = read_json(config.repo_root / "registry" / "dashboard" / "latest.json", {})
        generated_at = str(latest.get("generated_at", "")).strip() or "(未生成)"
        queue = latest.get("queue") if isinstance(latest.get("queue"), dict) else {}
        local_agent = latest.get("local_agent") if isinstance(latest.get("local_agent"), dict) else {}
        publication = latest.get("publication") if isinstance(latest.get("publication"), dict) else {}
        waiting = latest.get("waiting_for_human") if isinstance(latest.get("waiting_for_human"), list) else []
        failed = latest.get("failed_items") if isinstance(latest.get("failed_items"), list) else []
        top_candidates = latest.get("top_candidates") if isinstance(latest.get("top_candidates"), list) else []
        return "\n".join(
            [
                "**Codex Dashboard 状态**",
                f"- repo：{config.repo_root}",
                f"- 最新日报：{generated_at}",
                f"- 队列：{queue.get('total', 0)}（{_format_count_dict(queue.get('state_counts'))}）",
                f"- LocalAgent 候选：{local_agent.get('total', 0)}（{_format_count_dict(local_agent.get('status_counts'))}）",
                f"- 已发布跟踪：{publication.get('total', 0)}（{_format_count_dict(publication.get('status_counts'))}）",
                f"- 等待回复：{len(waiting)}",
                f"- 失败待处理：{len(failed)}",
                f"- 今日优先候选：{len(top_candidates)}",
                f"- 任务目录：{resolve_path(config.repo_root, config.task_root)}",
            ]
        )

    item = context.item or {}
    source = str(item.get("source", "")).strip() or "(queue 未找到)"
    state = str(item.get("state", "")).strip() or "(unknown)"
    branch = f"migration/{context.slug}" if context.slug else "(unknown)"
    workdir = context.workdir if context.workdir else config.repo_root
    return "\n".join(
        [
            f"**Codex 频道状态：{context.slug or context.channel_name}**",
            f"- 上游：{source}",
            f"- 队列状态：{state}",
            f"- 分支：{branch}",
            f"- worktree：{workdir}",
            f"- worktree 存在：{'yes' if workdir.exists() else 'no'}",
            f"- 任务目录：{resolve_path(config.repo_root, config.task_root)}",
        ]
    )


def _format_count_dict(value: Any) -> str:
    if not isinstance(value, dict) or not value:
        return "none"
    return ", ".join(f"{key}={value[key]}" for key in sorted(value))


def manual_exclusions_path(config: CodexControlConfig) -> Path:
    return config.repo_root / DEFAULT_MANUAL_EXCLUSIONS_PATH


def build_manual_exclusion_entry(item: dict[str, Any], *, now: str) -> dict[str, str]:
    candidate = item.get("candidate") if isinstance(item.get("candidate"), dict) else {}
    exclusion = candidate.get("exclusion") if isinstance(candidate.get("exclusion"), dict) else {}
    full_name = str(candidate.get("full_name") or item.get("source") or "").strip()
    reason = (
        str(exclusion.get("reason") or candidate.get("status_reason") or item.get("last_error") or "").strip()
        or "Repository manually excluded from migration."
    )
    matched_keyword = (
        str(exclusion.get("matched_keyword") or exclusion.get("label") or item.get("filtered_reason") or "").strip()
        or "manual_filter_cleanup"
    )
    return {
        "added_at": now,
        "full_name": full_name,
        "matched_keyword": matched_keyword,
        "reason": reason,
    }


def append_manual_exclusion(config: CodexControlConfig, item: dict[str, Any], *, now: str) -> dict[str, str]:
    path = manual_exclusions_path(config)
    payload = read_json(path, {"schema_version": 1, "repos": []})
    repos = payload.get("repos")
    if not isinstance(repos, list):
        repos = []
    entry = build_manual_exclusion_entry(item, now=now)
    full_name = entry["full_name"].lower()
    updated = False
    for existing in repos:
        if not isinstance(existing, dict):
            continue
        if str(existing.get("full_name", "")).strip().lower() != full_name:
            continue
        existing.update(entry)
        updated = True
        break
    if not updated:
        repos.append(entry)
    payload["schema_version"] = 1
    payload["repos"] = sorted(
        [repo for repo in repos if isinstance(repo, dict)],
        key=lambda repo: str(repo.get("full_name", "")).lower(),
    )
    write_json(path, payload)
    return entry


def update_queue_item_for_cleanup(config: CodexControlConfig, context: ChannelContext, *, now: str, note: str) -> None:
    queue_path = resolve_path(config.repo_root, config.queue_path)
    payload = read_json(queue_path, {"schema_version": 1, "items": []})
    items = payload.get("items")
    if not isinstance(items, list):
        items = []
        payload["items"] = items
    target_id = str((context.item or {}).get("id", "")).strip()
    target_slug = normalize_slug(context.slug)
    for item in items:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id", "")).strip()
        item_slug = normalize_slug(str(item.get("slug") or item.get("source") or item.get("id") or ""))
        if target_id and item_id != target_id and item_slug != target_slug:
            continue
        item["state"] = "filtered_out"
        item["candidate_status"] = "excluded"
        item["filtered_reason"] = "manual_filter_cleanup"
        item["last_error"] = note
        item["updated_at"] = now
        item["ops_note"] = note
        item.pop("human_request", None)
        item.pop("human_response", None)
        item.pop("discord", None)
        break
    write_json(queue_path, payload)


def cleanup_workspace_and_branch(config: CodexControlConfig, context: ChannelContext) -> list[str]:
    actions: list[str] = []
    workdir = context.workdir
    if workdir and workdir != config.repo_root and workdir.exists():
        result = subprocess.run(
            ["git", "-C", str(config.repo_root), "worktree", "remove", "--force", str(workdir)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError((result.stderr or result.stdout or "").strip() or f"git worktree remove failed: {workdir}")
        actions.append(f"worktree_removed:{workdir}")
    if workdir and workdir.exists():
        shutil.rmtree(workdir, ignore_errors=True)
        if not workdir.exists():
            actions.append(f"workspace_deleted:{workdir}")

    branch = f"migration/{normalize_slug(context.slug)}" if context.slug else ""
    if branch:
        result = subprocess.run(
            ["git", "-C", str(config.repo_root), "branch", "--list", branch],
            capture_output=True,
            text=True,
            check=False,
        )
        if branch in (result.stdout or ""):
            delete_result = subprocess.run(
                ["git", "-C", str(config.repo_root), "branch", "-D", branch],
                capture_output=True,
                text=True,
                check=False,
            )
            if delete_result.returncode != 0:
                raise RuntimeError((delete_result.stderr or delete_result.stdout or "").strip() or f"git branch -D failed: {branch}")
            actions.append(f"branch_deleted:{branch}")
    return actions


def cleanup_migration_artifacts(config: CodexControlConfig, context: ChannelContext) -> list[str]:
    removed: list[str] = []
    slug = normalize_slug(context.slug)
    roots = [
        resolve_path(config.repo_root, config.task_root),
        config.repo_root / "registry" / "auto-migration" / "codex-tasks",
        config.repo_root / "registry" / "auto-migration" / "discovery-review-tasks",
        config.repo_root / "registry" / "auto-migration" / "notifications",
    ]
    for root in roots:
        if not root.exists():
            continue
        for path in root.iterdir():
            if slug not in path.name:
                continue
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink(missing_ok=True)
            removed.append(str(path))
    return removed


def cleanup_channel_state(config: CodexControlConfig, context: ChannelContext) -> None:
    state_path = resolve_path(config.repo_root, config.state_path)
    state = read_json(state_path, {})
    channels = state.get("channels")
    if not isinstance(channels, dict):
        channels = {}
    channels.pop(context.channel_id, None)
    state["channels"] = channels
    write_json(state_path, state)


def run_filter_cleanup(context: ChannelContext, config: CodexControlConfig, client: DiscordClient, *, now: str) -> CommandResult:
    if context.scope != "migration" or not context.item:
        return CommandResult("missing_queue_item", "这个命令只能在绑定了 queue 项目的 migration 频道里使用。")
    entry = append_manual_exclusion(config, context.item, now=now)
    note = f"manual_filter_cleanup:{entry['matched_keyword']}:{entry['reason']}"
    update_queue_item_for_cleanup(config, context, now=now, note=note)
    cleanup_migration_artifacts(config, context)
    cleanup_workspace_and_branch(config, context)
    cleanup_channel_state(config, context)
    client.delete_channel(context.channel_id)
    return CommandResult("filtered_cleaned", "", delete_channel_id=context.channel_id)


def app_context_text(context: ChannelContext) -> str:
    if context.scope == "dashboard":
        latest = read_text_if_exists(context.workdir / "registry" / "dashboard" / "latest.md", max_chars=12000)
        if not latest:
            return ""
        return f"""Latest dashboard summary:
```markdown
{latest}
```"""
    if not context.slug or not context.workdir:
        return ""
    app_dir = context.workdir / "apps" / context.slug
    state = read_text_if_exists(app_dir / ".migration-state.json", max_chars=10000)
    functional = read_text_if_exists(app_dir / ".functional-check.json", max_chars=5000)
    if not state and not functional:
        return ""
    return f"""App migration state:
```json
{state or "{}"}
```

Functional check:
```json
{functional or "{}"}
```"""


def build_codex_prompt(task: CodexControlTask) -> str:
    context = task.context
    item_json = json.dumps(context.item or {}, ensure_ascii=False, indent=2, sort_keys=True)
    return f"""You are the always-on Codex control worker for the LazyCat lzcat-apps migration workflow.

Operator instruction from Discord:
{task.instruction}

Channel context:
- channel: #{context.channel_name} ({context.channel_id})
- scope: {context.scope}
- slug: {context.slug or "(global control)"}
- repo_root: {task.config.repo_root}
- workdir: {context.workdir}
- queue_path: {resolve_path(task.config.repo_root, task.config.queue_path)}
- workspace_root: {resolve_path(task.config.repo_root, task.config.workspace_root) if has_path(task.config.workspace_root) else "(not configured)"}

Queue item:
```json
{item_json}
```

Operating rules:
- Work in `workdir` when it exists. For migration channels this should be the `migration/<slug>` worktree.
- Keep the `template` branch clean: reusable migration-platform improvements can be proposed there later, but do not move app products into template.
- Do not submit, publish, or click final LazyCat developer-console review actions.
- Do not revert unrelated user, daemon, or generated changes.
- If the request requires user choice, credentials, legal/license judgement, final publish approval, or browser interaction you cannot complete, stop and write a clear question in the final message.
- If changing queue state is appropriate, update the queue JSON at `queue_path` with a concise machine-readable note.
- Run narrow verification for code changes and include exact commands/results in the final summary.
- Keep the final message concise because it will be posted back to Discord.

{app_context_text(context)}
"""


def build_codex_command(task: CodexControlTask) -> list[str]:
    last_message_path = task.task_dir / "last-message.md"
    return [
        "codex",
        "--ask-for-approval",
        "never",
        "exec",
        "-C",
        str(task.context.workdir or task.config.repo_root),
        "--model",
        task.config.model,
        "--sandbox",
        "danger-full-access",
        "--output-last-message",
        str(last_message_path),
        "-",
    ]


def model_requires_newer_codex(output: str) -> bool:
    return "requires a newer version of Codex" in output


def fallback_model() -> str:
    return os.environ.get("LZCAT_CODEX_FALLBACK_MODEL", DEFAULT_CODEX_FALLBACK_MODEL).strip()


def command_with_model(command: list[str], model: str) -> list[str]:
    updated = list(command)
    if "--model" in updated:
        updated[updated.index("--model") + 1] = model
    else:
        updated.extend(["--model", model])
    return updated


def write_task_bundle(task: CodexControlTask) -> None:
    task.task_dir.mkdir(parents=True, exist_ok=True)
    (task.task_dir / "prompt.md").write_text(task.prompt, encoding="utf-8")
    (task.task_dir / "task.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "created_at": task.now,
                "instruction": task.instruction,
                "channel": {
                    "id": task.context.channel_id,
                    "name": task.context.channel_name,
                    "scope": task.context.scope,
                    "slug": task.context.slug,
                },
                "workdir": str(task.context.workdir),
                "queue_path": str(resolve_path(task.config.repo_root, task.config.queue_path)),
                "item": task.context.item or {},
                "command": task.command,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def run_codex_control_task(task: CodexControlTask) -> CodexControlRunResult:
    write_task_bundle(task)
    if not task.config.execute:
        return CodexControlRunResult("prepared", 0, "已生成 Codex 任务包，未执行。", task.task_dir)

    stdout_path = task.task_dir / "codex.stdout.log"
    stderr_path = task.task_dir / "codex.stderr.log"
    result = subprocess.run(task.command, input=task.prompt, text=True, capture_output=True, check=False)
    stdout_chunks = [result.stdout or ""]
    stderr_chunks = [result.stderr or ""]
    fallback_used: dict[str, Any] | None = None
    combined = f"{result.stdout or ''}\n{result.stderr or ''}"
    fallback = fallback_model()
    if result.returncode != 0 and fallback and fallback != task.config.model and model_requires_newer_codex(combined):
        fallback_command = command_with_model(task.command, fallback)
        fallback_result = subprocess.run(fallback_command, input=task.prompt, text=True, capture_output=True, check=False)
        stdout_chunks.append(f"\n\n--- retry with {fallback} ---\n{fallback_result.stdout or ''}")
        stderr_chunks.append(f"\n\n--- retry with {fallback} ---\n{fallback_result.stderr or ''}")
        fallback_used = {
            "from_model": task.config.model,
            "to_model": fallback,
            "original_returncode": result.returncode,
            "returncode": fallback_result.returncode,
        }
        result = fallback_result

    stdout_path.write_text("".join(stdout_chunks), encoding="utf-8")
    stderr_path.write_text("".join(stderr_chunks), encoding="utf-8")
    if fallback_used:
        (task.task_dir / "model-fallback.json").write_text(
            json.dumps(fallback_used, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    last_message = read_text_if_exists(task.task_dir / "last-message.md", max_chars=1600).strip()
    if not last_message:
        last_message = read_text_if_exists(stdout_path, max_chars=1000).strip()
    if not last_message:
        last_message = read_text_if_exists(stderr_path, max_chars=1000).strip()
    status = "completed" if result.returncode == 0 else "failed"
    summary = last_message or "(Codex 没有输出最终消息)"
    return CodexControlRunResult(status, result.returncode, summary, task.task_dir)


def build_task(
    instruction: str,
    context: ChannelContext,
    config: CodexControlConfig,
    *,
    now: str,
    task_id: str = "",
) -> CodexControlTask:
    slug_or_scope = context.slug or context.scope or "control"
    channel_part = safe_task_name(context.channel_name or context.channel_id)
    message_part = safe_task_name(task_id or now.replace(":", "").replace("-", ""))
    task_dir = resolve_path(config.repo_root, config.task_root) / f"{message_part}-{channel_part}-{safe_task_name(slug_or_scope)}"
    placeholder = CodexControlTask(
        instruction=instruction,
        context=context,
        config=config,
        task_dir=task_dir,
        prompt="",
        command=[],
        now=now,
    )
    prompt = build_codex_prompt(placeholder)
    task = CodexControlTask(
        instruction=instruction,
        context=context,
        config=config,
        task_dir=task_dir,
        prompt=prompt,
        command=[],
        now=now,
    )
    return CodexControlTask(
        instruction=instruction,
        context=context,
        config=config,
        task_dir=task_dir,
        prompt=prompt,
        command=build_codex_command(task),
        now=now,
    )


def format_codex_result_reply(result: CodexControlRunResult, context: ChannelContext) -> str:
    title = "完成" if result.returncode == 0 else "失败"
    lines = [
        f"**Codex 任务{title}**",
        f"- 频道：#{context.channel_name}",
        f"- 项目：{context.slug or 'global'}",
        f"- returncode：{result.returncode}",
        f"- 任务目录：{result.task_dir}",
        "",
        result.summary.strip(),
    ]
    return truncate_reply("\n".join(line for line in lines if line))


def handle_command(
    parsed: ParsedCommand,
    context: ChannelContext,
    config: CodexControlConfig,
    *,
    client: DiscordClient | None = None,
    runner: CodexRunner = run_codex_control_task,
    now: str | None = None,
    task_id: str = "",
) -> CommandResult:
    now = now or utc_now_iso()
    if parsed.kind == "help":
        return CommandResult("help", build_help_reply())
    if parsed.kind == "content_unavailable":
        return CommandResult("content_unavailable", build_content_unavailable_reply())
    if parsed.kind == "status":
        return CommandResult("status", build_status_reply(context, config))
    if parsed.kind == "filter_cleanup":
        if client is None:
            return CommandResult("failed", "Discord client is required for cleanup commands.")
        return run_filter_cleanup(context, config, client, now=now)
    if parsed.kind != "codex":
        return CommandResult("ignored", "")
    if context.scope == "migration" and not context.item:
        return CommandResult(
            "missing_queue_item",
            f"当前频道看起来是 `{context.slug}`，但 queue.json 里没有对应项目。先确认这个频道是否已经上架/过滤，或者用 `!codex <明确任务>` 在 control 频道执行全局排查。",
        )
    task = build_task(parsed.instruction, context, config, now=now, task_id=task_id)
    result = runner(task)
    return CommandResult(result.status, format_codex_result_reply(result, context))


def gateway_intents() -> int:
    return (
        DISCORD_GATEWAY_GUILDS_INTENT
        | DISCORD_GATEWAY_GUILD_MESSAGES_INTENT
        | DISCORD_GATEWAY_MESSAGE_CONTENT_INTENT
    )


def build_gateway_identify_payload(token: str) -> dict[str, Any]:
    return {
        "op": 2,
        "d": {
            "token": token,
            "intents": gateway_intents(),
            "properties": {
                "os": sys.platform,
                "browser": "lzcat-codex-control",
                "device": "lzcat-codex-control",
            },
        },
    }


def handle_gateway_message_create(
    config: CodexControlConfig,
    client: DiscordClient,
    contexts_by_channel_id: dict[str, ChannelContext],
    message: dict[str, Any],
    *,
    runner: CodexRunner = run_codex_control_task,
    now: str | None = None,
) -> dict[str, str]:
    channel_id = str(message.get("channel_id", "")).strip()
    message_id = str(message.get("id", "")).strip()
    if not channel_id or not message_id:
        return {"channel_id": channel_id, "message_id": message_id, "status": "ignored"}
    context = contexts_by_channel_id.get(channel_id)
    if not context:
        return {"channel_id": channel_id, "message_id": message_id, "status": "unknown_channel"}
    if is_bot_message(message):
        return {"channel_id": channel_id, "message_id": message_id, "status": "bot_ignored"}
    parsed = parse_control_message(message, config)
    if not parsed:
        return {"channel_id": channel_id, "message_id": message_id, "status": "ignored"}

    reaction_error = ""
    send_error = ""
    try:
        client.add_reaction(channel_id, message_id, ACK_REACTION)
    except Exception as exc:  # pragma: no cover - exact HTTP exception type varies.
        reaction_error = str(exc)

    will_run = parsed.kind == "codex" and not (context.scope == "migration" and not context.item)
    if will_run:
        try:
            client.add_reaction(channel_id, message_id, WORKER_REACTION)
        except Exception as exc:  # pragma: no cover - exact HTTP exception type varies.
            reaction_error = str(exc)

    result = handle_command(parsed, context, config, runner=runner, now=now, task_id=message_id)
    if result.reply:
        try:
            client.send_message(channel_id, truncate_reply(result.reply))
        except Exception as exc:  # pragma: no cover - exact HTTP exception type varies.
            send_error = str(exc)

    entry = {"channel_id": channel_id, "message_id": message_id, "status": result.status}
    if send_error:
        entry["status"] = f"{result.status}_reply_failed"
        entry["reply_error"] = send_error
    if reaction_error:
        entry["reaction_error"] = reaction_error
    return entry


def fetch_channel_message_batches(
    contexts: list[ChannelContext],
    channels_state: dict[str, Any],
    client: DiscordClient,
    *,
    limit: int,
    fallback_last_message_id: str = "",
) -> list[ChannelMessageBatch]:
    if not contexts:
        return []

    def fetch(index: int, context: ChannelContext) -> ChannelMessageBatch:
        channel_state = channels_state.get(context.channel_id)
        if not isinstance(channel_state, dict):
            channel_state = {}
        last_message_id = str(channel_state.get("last_message_id") or fallback_last_message_id or "").strip()
        try:
            messages = order_messages(client.list_messages(context.channel_id, after=last_message_id, limit=limit))
        except Exception as exc:  # pragma: no cover - exact HTTP exception type varies.
            return ChannelMessageBatch(index, context, channel_state, last_message_id, [], error=str(exc))
        return ChannelMessageBatch(index, context, channel_state, last_message_id, messages)

    max_workers = min(8, max(1, len(contexts)))
    batches: list[ChannelMessageBatch] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(fetch, index, context) for index, context in enumerate(contexts)]
        for future in as_completed(futures):
            batches.append(future.result())
    return sorted(batches, key=lambda batch: batch.index)


def websocket_accept_value(key: str) -> str:
    digest = hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")).digest()
    return base64.b64encode(digest).decode("ascii")


def open_gateway_socket(*, timeout: float = 30.0) -> ssl.SSLSocket:
    raw = socket.create_connection((DISCORD_GATEWAY_HOST, 443), timeout=timeout)
    secure = ssl.create_default_context().wrap_socket(raw, server_hostname=DISCORD_GATEWAY_HOST)
    key = base64.b64encode(os.urandom(16)).decode("ascii")
    request = "\r\n".join(
        [
            f"GET {DISCORD_GATEWAY_PATH} HTTP/1.1",
            f"Host: {DISCORD_GATEWAY_HOST}",
            "Upgrade: websocket",
            "Connection: Upgrade",
            f"Sec-WebSocket-Key: {key}",
            "Sec-WebSocket-Version: 13",
            "User-Agent: lzcat-codex-control/1.0",
            "",
            "",
        ]
    )
    secure.sendall(request.encode("ascii"))
    response = b""
    while b"\r\n\r\n" not in response:
        chunk = secure.recv(4096)
        if not chunk:
            raise ConnectionError("Discord Gateway closed during WebSocket handshake")
        response += chunk
        if len(response) > 32768:
            raise ConnectionError("Discord Gateway handshake response is too large")
    header = response.split(b"\r\n\r\n", 1)[0].decode("iso-8859-1", errors="replace")
    lines = header.split("\r\n")
    if not lines or " 101 " not in lines[0]:
        raise ConnectionError(f"Discord Gateway WebSocket handshake failed: {lines[0] if lines else header}")
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if ":" not in line:
            continue
        name, value = line.split(":", 1)
        headers[name.strip().lower()] = value.strip()
    if headers.get("sec-websocket-accept") != websocket_accept_value(key):
        raise ConnectionError("Discord Gateway WebSocket accept header did not match")
    secure.settimeout(1.0)
    return secure


def build_websocket_frame(payload: bytes, *, opcode: int = 1) -> bytes:
    first = 0x80 | (opcode & 0x0F)
    length = len(payload)
    mask_key = os.urandom(4)
    if length < 126:
        header = struct.pack("!BB", first, 0x80 | length)
    elif length <= 0xFFFF:
        header = struct.pack("!BBH", first, 0x80 | 126, length)
    else:
        header = struct.pack("!BBQ", first, 0x80 | 127, length)
    masked = bytes(byte ^ mask_key[index % 4] for index, byte in enumerate(payload))
    return header + mask_key + masked


def _recv_exact(sock: ssl.SSLSocket, length: int) -> bytes:
    chunks: list[bytes] = []
    remaining = length
    while remaining:
        chunk = sock.recv(remaining)
        if not chunk:
            raise ConnectionError("Discord Gateway WebSocket closed")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def read_websocket_frame(sock: ssl.SSLSocket) -> tuple[bool, int, bytes]:
    header = _recv_exact(sock, 2)
    first, second = header
    fin = bool(first & 0x80)
    opcode = first & 0x0F
    masked = bool(second & 0x80)
    length = second & 0x7F
    if length == 126:
        length = struct.unpack("!H", _recv_exact(sock, 2))[0]
    elif length == 127:
        length = struct.unpack("!Q", _recv_exact(sock, 8))[0]
    mask_key = _recv_exact(sock, 4) if masked else b""
    payload = _recv_exact(sock, length) if length else b""
    if masked:
        payload = bytes(byte ^ mask_key[index % 4] for index, byte in enumerate(payload))
    return fin, opcode, payload


def read_gateway_payload(sock: ssl.SSLSocket) -> dict[str, Any] | None:
    fragments: list[bytes] = []
    message_opcode = 0
    while True:
        fin, opcode, payload = read_websocket_frame(sock)
        if opcode == 8:
            raise ConnectionError("Discord Gateway sent close frame")
        if opcode == 9:
            sock.sendall(build_websocket_frame(payload, opcode=10))
            continue
        if opcode == 10:
            continue
        if opcode in {1, 2}:
            message_opcode = opcode
            fragments = [payload]
        elif opcode == 0:
            fragments.append(payload)
        else:
            continue
        if not fin:
            continue
        if message_opcode != 1:
            return None
        text = b"".join(fragments).decode("utf-8")
        payload_obj = json.loads(text)
        return payload_obj if isinstance(payload_obj, dict) else None


def send_gateway_payload(sock: ssl.SSLSocket, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    sock.sendall(build_websocket_frame(body))


def build_context_map(config: CodexControlConfig, client: DiscordClient) -> dict[str, ChannelContext]:
    return {context.channel_id: context for context in discover_channels(config, client)}


def run_gateway_control(
    config: CodexControlConfig,
    client: DiscordClient,
    *,
    token: str,
    runner: CodexRunner = run_codex_control_task,
    max_workers: int = 8,
) -> None:
    contexts_by_channel_id = build_context_map(config, client)
    with ThreadPoolExecutor(max_workers=max(1, max_workers)) as executor:
        while True:
            try:
                sock = open_gateway_socket()
                next_heartbeat = float("inf")
                heartbeat_interval = 30.0
                last_sequence: int | None = None
                last_context_refresh = time.monotonic()
                print(
                    json.dumps(
                        {
                            "checked_at": utc_now_iso(),
                            "gateway": "connected",
                            "contexts": len(contexts_by_channel_id),
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    flush=True,
                )
                with sock:
                    while True:
                        now_monotonic = time.monotonic()
                        if now_monotonic >= next_heartbeat:
                            send_gateway_payload(sock, {"op": 1, "d": last_sequence})
                            next_heartbeat = now_monotonic + heartbeat_interval
                        if now_monotonic - last_context_refresh > 300:
                            contexts_by_channel_id = build_context_map(config, client)
                            last_context_refresh = now_monotonic
                        try:
                            gateway_payload = read_gateway_payload(sock)
                        except socket.timeout:
                            continue
                        if not gateway_payload:
                            continue
                        sequence = gateway_payload.get("s")
                        if isinstance(sequence, int):
                            last_sequence = sequence
                        op = gateway_payload.get("op")
                        data = gateway_payload.get("d") if isinstance(gateway_payload.get("d"), dict) else {}
                        event_type = str(gateway_payload.get("t") or "")
                        if op == 10:
                            heartbeat_interval = max(1.0, float(data.get("heartbeat_interval", 30000)) / 1000.0)
                            next_heartbeat = time.monotonic() + heartbeat_interval
                            send_gateway_payload(sock, build_gateway_identify_payload(token))
                            continue
                        if op == 1:
                            send_gateway_payload(sock, {"op": 1, "d": last_sequence})
                            continue
                        if op in {7, 9}:
                            raise ConnectionError(f"Discord Gateway requested reconnect: op={op}")
                        if event_type in {"READY", "GUILD_CREATE", "CHANNEL_CREATE", "CHANNEL_UPDATE", "CHANNEL_DELETE"}:
                            contexts_by_channel_id = build_context_map(config, client)
                            last_context_refresh = time.monotonic()
                            continue
                        if event_type != "MESSAGE_CREATE":
                            continue
                        channel_id = str(data.get("channel_id", "")).strip()
                        if channel_id not in contexts_by_channel_id:
                            contexts_by_channel_id = build_context_map(config, client)
                        executor.submit(
                            _handle_gateway_message_and_log,
                            config,
                            client,
                            dict(contexts_by_channel_id),
                            data,
                            runner,
                        )
            except Exception as exc:  # pragma: no cover - live network behavior.
                print(
                    json.dumps(
                        {"checked_at": utc_now_iso(), "gateway": "reconnect", "error": str(exc)},
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    flush=True,
                )
                time.sleep(5)


def _handle_gateway_message_and_log(
    config: CodexControlConfig,
    client: DiscordClient,
    contexts_by_channel_id: dict[str, ChannelContext],
    message: dict[str, Any],
    runner: CodexRunner,
) -> None:
    result = handle_gateway_message_create(
        config,
        client,
        contexts_by_channel_id,
        message,
        runner=runner,
        now=utc_now_iso(),
    )
    if result.get("status") not in {"ignored", "bot_ignored", "unknown_channel"}:
        print(json.dumps({"checked_at": utc_now_iso(), "gateway_message": result}, ensure_ascii=False, sort_keys=True), flush=True)


def process_codex_control_commands(
    config: CodexControlConfig,
    client: DiscordClient,
    *,
    runner: CodexRunner = run_codex_control_task,
    now: str | None = None,
) -> list[dict[str, str]]:
    now = now or utc_now_iso()
    state_path = resolve_path(config.repo_root, config.state_path)
    state = read_json(state_path, {})
    try:
        contexts = discover_channels(config, client)
    except Exception as exc:  # pragma: no cover - exact HTTP exception type varies.
        state["last_error"] = str(exc)
        state["last_checked_at"] = now
        write_json(state_path, state)
        return [{"channel_id": "", "message_id": "", "status": "guild_read_failed"}]
    if not contexts:
        return []

    channels_state = state.get("channels")
    if not isinstance(channels_state, dict):
        channels_state = {}
    results: list[dict[str, str]] = []
    batches = fetch_channel_message_batches(
        contexts,
        channels_state,
        client,
        limit=20,
        fallback_last_message_id=str(state.get("last_message_id") or "").strip(),
    )

    for batch in batches:
        context = batch.context
        channel_state = batch.channel_state
        last_message_id = batch.last_message_id
        channel_deleted = False
        if batch.error:
            channel_state["last_error"] = batch.error
            channel_state["last_checked_at"] = now
            channel_state["channel_name"] = context.channel_name
            channel_state["slug"] = context.slug
            channels_state[context.channel_id] = channel_state
            results.append({"channel_id": context.channel_id, "message_id": "", "status": "channel_read_failed"})
            continue
        last_seen = last_message_id
        for message in batch.messages:
            message_id = str(message.get("id", "")).strip()
            if not message_id:
                continue
            if is_bot_message(message):
                last_seen = message_id
                continue
            last_seen = message_id
            parsed = parse_control_message(message, config)
            if not parsed:
                continue
            reaction_error = ""
            try:
                client.add_reaction(context.channel_id, message_id, ACK_REACTION)
            except Exception as exc:  # pragma: no cover - exact HTTP exception type varies.
                reaction_error = str(exc)
            is_action_command = parsed.kind in {"codex", "filter_cleanup"}
            will_run = is_action_command and not (context.scope == "migration" and not context.item)
            send_error = ""
            if will_run:
                try:
                    client.add_reaction(context.channel_id, message_id, WORKER_REACTION)
                except Exception as exc:  # pragma: no cover - exact HTTP exception type varies.
                    reaction_error = str(exc)
                if parsed.kind == "filter_cleanup":
                    try:
                        client.send_message(context.channel_id, "收到，正在把当前 repo 加入过滤名单并清理频道、worktree、branch。完成后这个频道会被关闭。")
                    except Exception as exc:  # pragma: no cover - exact HTTP exception type varies.
                        send_error = str(exc)
            result = handle_command(parsed, context, config, client=client, runner=runner, now=now, task_id=message_id)
            if result.reply and not result.delete_channel_id:
                try:
                    client.send_message(context.channel_id, truncate_reply(result.reply))
                except Exception as exc:  # pragma: no cover - exact HTTP exception type varies.
                    send_error = str(exc)
            status = result.status
            entry = {"channel_id": context.channel_id, "message_id": message_id, "status": status}
            if send_error:
                status = f"{status}_reply_failed"
                entry["status"] = status
                entry["reply_error"] = send_error
                channel_state["last_error"] = send_error
            if reaction_error:
                entry["reaction_error"] = reaction_error
                channel_state["last_error"] = reaction_error
            results.append(entry)
            if result.delete_channel_id == context.channel_id:
                channels_state.pop(context.channel_id, None)
                channel_deleted = True
                break

        if channel_deleted:
            continue

        if last_seen != last_message_id:
            channel_state["last_message_id"] = last_seen
            channel_state["last_checked_at"] = now
            channel_state["channel_name"] = context.channel_name
            channel_state["slug"] = context.slug
            channels_state[context.channel_id] = channel_state

    state["channels"] = channels_state
    state["last_checked_at"] = now
    write_json(state_path, state)
    return results


def mark_existing_messages_seen(
    config: CodexControlConfig,
    client: DiscordClient,
    *,
    now: str | None = None,
) -> list[dict[str, str]]:
    now = now or utc_now_iso()
    state_path = resolve_path(config.repo_root, config.state_path)
    state = read_json(state_path, {})
    try:
        contexts = discover_channels(config, client)
    except Exception as exc:  # pragma: no cover - exact HTTP exception type varies.
        state["last_error"] = str(exc)
        state["last_checked_at"] = now
        write_json(state_path, state)
        return [{"channel_id": "", "message_id": "", "status": "guild_read_failed"}]
    channels_state = state.get("channels")
    if not isinstance(channels_state, dict):
        channels_state = {}
    results: list[dict[str, str]] = []
    batches = fetch_channel_message_batches(contexts, channels_state, client, limit=1)

    for batch in batches:
        context = batch.context
        channel_state = batch.channel_state
        if batch.error:
            channel_state["last_error"] = batch.error
            channel_state["last_checked_at"] = now
            channel_state["channel_name"] = context.channel_name
            channel_state["slug"] = context.slug
            channels_state[context.channel_id] = channel_state
            results.append({"channel_id": context.channel_id, "message_id": "", "status": "channel_read_failed"})
            continue
        last_message_id = ""
        if batch.messages:
            last_message_id = str(batch.messages[0].get("id", "")).strip()
        channel_state["last_message_id"] = last_message_id
        channel_state["last_checked_at"] = now
        channel_state["channel_name"] = context.channel_name
        channel_state["slug"] = context.slug
        channels_state[context.channel_id] = channel_state
        results.append({"channel_id": context.channel_id, "message_id": last_message_id, "status": "marked_seen"})

    state["channels"] = channels_state
    state["last_checked_at"] = now
    state["initialized_at"] = state.get("initialized_at") or now
    write_json(state_path, state)
    return results


def config_from_project(repo_root: Path, *, execute: bool = True) -> CodexControlConfig:
    project_config = load_project_config(repo_root)
    workspace_root = Path(project_config.migration.workspace_root).expanduser() if project_config.migration.workspace_root else Path("")
    if has_path(workspace_root) and not workspace_root.is_absolute():
        workspace_root = repo_root / workspace_root
    state_path = Path(project_config.codex_control.state_path).expanduser()
    if not state_path.is_absolute():
        state_path = repo_root / state_path
    task_root = Path(project_config.codex_control.task_root).expanduser()
    if not task_root.is_absolute():
        task_root = repo_root / task_root
    return CodexControlConfig(
        repo_root=repo_root,
        queue_path=repo_root / DEFAULT_QUEUE_PATH,
        state_path=state_path,
        task_root=task_root,
        workspace_root=workspace_root,
        guild_id=project_config.discord.guild_id,
        category_id=project_config.discord.category_id,
        channel_prefix=project_config.discord.channel_prefix,
        control_channel=project_config.codex_control.control_channel,
        bot_user_id=project_config.codex_control.bot_user_id,
        mention_role_ids=project_config.codex_control.mention_role_ids,
        model=project_config.codex_control.model or project_config.migration.codex_worker_model,
        execute=execute,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Process Discord commands that spawn Codex control tasks.")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument(
        "--transport",
        choices=("gateway", "polling"),
        default="gateway",
        help="Use Discord Gateway WebSocket by default; polling is kept as a fallback.",
    )
    parser.add_argument("--once", action="store_true", help="Process one polling batch and exit.")
    parser.add_argument("--mark-seen", action="store_true", help="Initialize state from current channel messages without running commands.")
    parser.add_argument("--interval-seconds", type=float, default=15.0, help="Polling interval when running as a daemon.")
    parser.add_argument("--no-execute", action="store_true", help="Write task bundles but do not run Codex.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    token = os.environ.get("LZCAT_CODEX_DISCORD_BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("LZCAT_CODEX_DISCORD_BOT_TOKEN is required for the dedicated Codex control bot")
    config = config_from_project(repo_root, execute=not args.no_execute)
    if not config.guild_id:
        raise SystemExit("discord.guild_id is required in project-config.json")
    client = DiscordClient(token)
    if args.mark_seen:
        results = mark_existing_messages_seen(config, client)
        print(json.dumps({"codex_control": results}, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.once:
        results = process_codex_control_commands(config, client)
        print(json.dumps({"codex_control": results}, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.transport == "gateway":
        run_gateway_control(config, client, token=token)
        return 0
    interval = max(5.0, float(args.interval_seconds))
    while True:
        results = process_codex_control_commands(config, client)
        print(json.dumps({"checked_at": utc_now_iso(), "codex_control": results}, ensure_ascii=False, sort_keys=True), flush=True)
        time.sleep(interval)


if __name__ == "__main__":
    raise SystemExit(main())
