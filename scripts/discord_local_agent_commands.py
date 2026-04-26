#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    from .discord_migration_notifier import DiscordClient, MAX_DISCORD_MESSAGE_LENGTH
    from .local_agent_bridge import write_local_agent_snapshot
    from .migration_workspace import normalize_slug
    from .project_config import load_project_config
except ImportError:  # pragma: no cover - direct script execution
    from discord_migration_notifier import DiscordClient, MAX_DISCORD_MESSAGE_LENGTH
    from local_agent_bridge import write_local_agent_snapshot
    from migration_workspace import normalize_slug
    from project_config import load_project_config


DEFAULT_QUEUE_PATH = "registry/auto-migration/queue.json"
DEFAULT_STATE_PATH = "registry/auto-migration/discord-local-agent-commands.json"
DEFAULT_SNAPSHOT_PATH = "registry/candidates/local-agent-latest.json"


@dataclass(frozen=True)
class LocalAgentCommandConfig:
    repo_root: Path
    local_agent_root: Path = Path("")
    snapshot_path: Path = Path(DEFAULT_SNAPSHOT_PATH)
    queue_path: Path = Path(DEFAULT_QUEUE_PATH)
    state_path: Path = Path(DEFAULT_STATE_PATH)
    guild_id: str = ""
    category_id: str = ""
    channel_prefix: str = "migration"


@dataclass(frozen=True)
class CommandResult:
    status: str
    reply: str


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def command_channel_name(prefix: str) -> str:
    normalized_prefix = normalize_slug(str(prefix).strip()) or "migration"
    return f"{normalized_prefix}-local-agent"


def resolve_path(repo_root: Path, path: Path | str) -> Path:
    value = Path(path).expanduser()
    if value.is_absolute():
        return value
    return repo_root / value


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


def format_counts(items: list[dict[str, Any]], key: str) -> str:
    counts = Counter(str(item.get(key, "")).strip() or "unknown" for item in items if isinstance(item, dict))
    return ", ".join(f"{name}={count}" for name, count in sorted(counts.items())) or "none"


def snapshot_candidates(config: LocalAgentCommandConfig) -> list[dict[str, Any]]:
    payload = read_json(resolve_path(config.repo_root, config.snapshot_path), {"candidates": []})
    candidates = payload.get("candidates")
    return [item for item in candidates if isinstance(item, dict)] if isinstance(candidates, list) else []


def queue_items(config: LocalAgentCommandConfig) -> list[dict[str, Any]]:
    payload = read_json(resolve_path(config.repo_root, config.queue_path), {"items": []})
    items = payload.get("items")
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def local_agent_queue_items(config: LocalAgentCommandConfig) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for item in queue_items(config):
        candidate = item.get("candidate") if isinstance(item.get("candidate"), dict) else {}
        if candidate.get("discovery_source") == "local_agent":
            results.append(item)
    return results


def build_help_reply() -> str:
    return "\n".join(
        [
            "**LocalAgent 指令**",
            "`!la status` 查看 LocalAgent、快照和迁移队列概况",
            "`!la import` 立即刷新 LocalAgent 候选快照",
            "`!la queue [数量]` 查看已进入迁移队列的 LocalAgent 候选",
            "`!la find <关键词>` 在 LocalAgent 快照中搜索候选",
        ]
    )


def build_status_reply(config: LocalAgentCommandConfig) -> str:
    local_agent_root = resolve_path(config.repo_root, config.local_agent_root)
    snapshot = snapshot_candidates(config)
    queue = queue_items(config)
    local_queue = local_agent_queue_items(config)
    return "\n".join(
        [
            "**LocalAgent 状态**",
            f"- 路径：{local_agent_root}",
            f"- 路径存在：{'yes' if local_agent_root.exists() else 'no'}",
            f"- 候选快照：{len(snapshot)}（{format_counts(snapshot, 'status')}）",
            f"- 迁移队列：{len(queue)}（{format_counts(queue, 'state')}）",
            f"- LocalAgent 入队：{len(local_queue)}（{format_counts(local_queue, 'state')}）",
        ]
    )


def run_import(config: LocalAgentCommandConfig, *, now: str) -> CommandResult:
    local_agent_root = resolve_path(config.repo_root, config.local_agent_root)
    if not local_agent_root.exists():
        return CommandResult("failed", f"LocalAgent 路径不存在：{local_agent_root}")
    snapshot_path = resolve_path(config.repo_root, config.snapshot_path)
    snapshot = write_local_agent_snapshot(local_agent_root, snapshot_path, now=now)
    candidates = snapshot.get("candidates") if isinstance(snapshot.get("candidates"), list) else []
    return CommandResult(
        "imported",
        "\n".join(
            [
                "**LocalAgent 导入完成**",
                f"- 导入 {len(candidates)} 个候选",
                f"- 快照：{snapshot_path}",
                f"- 状态：{format_counts([item for item in candidates if isinstance(item, dict)], 'status')}",
            ]
        ),
    )


def parse_limit(args: list[str], default: int = 5) -> int:
    if not args:
        return default
    try:
        return max(1, min(int(args[0]), 20))
    except ValueError:
        return default


def describe_queue_item(item: dict[str, Any]) -> str:
    source = str(item.get("source") or item.get("id") or "").strip()
    state = str(item.get("state", "")).strip()
    candidate = item.get("candidate") if isinstance(item.get("candidate"), dict) else {}
    description = str(candidate.get("description", "")).strip()
    if len(description) > 90:
        description = description[:87].rstrip() + "..."
    suffix = f" - {description}" if description else ""
    return f"- `{state}` {source}{suffix}"


def build_queue_reply(config: LocalAgentCommandConfig, args: list[str]) -> CommandResult:
    limit = parse_limit(args)
    items = local_agent_queue_items(config)
    if not items:
        return CommandResult("queue", "LocalAgent 还没有候选进入迁移队列。")
    selected = items[:limit]
    return CommandResult(
        "queue",
        "\n".join(["**LocalAgent 迁移队列**", f"- 总数：{len(items)}", *[describe_queue_item(item) for item in selected]]),
    )


def build_find_reply(config: LocalAgentCommandConfig, args: list[str]) -> CommandResult:
    term = " ".join(args).strip().lower()
    if not term:
        return CommandResult("usage", "用法：`!la find <关键词>`")
    matches: list[dict[str, Any]] = []
    for candidate in snapshot_candidates(config):
        haystack = " ".join(
            [
                str(candidate.get("full_name", "")),
                str(candidate.get("repo_url", "")),
                str(candidate.get("description", "")),
                str(candidate.get("status", "")),
            ]
        ).lower()
        if term in haystack:
            matches.append(candidate)
    if not matches:
        return CommandResult("find", f"没有找到包含 `{term}` 的 LocalAgent 候选。")
    lines = ["**LocalAgent 搜索结果**", f"- 关键词：{term}", f"- 命中：{len(matches)}"]
    for candidate in matches[:10]:
        full_name = str(candidate.get("full_name", "")).strip()
        status = str(candidate.get("status", "")).strip()
        description = str(candidate.get("description", "")).strip()
        if len(description) > 80:
            description = description[:77].rstrip() + "..."
        lines.append(f"- `{status}` {full_name}" + (f" - {description}" if description else ""))
    return CommandResult("find", "\n".join(lines))


def parse_command(content: str) -> tuple[str, list[str]] | None:
    parts = content.strip().split()
    if not parts:
        return None
    prefix = parts[0].lower()
    if prefix not in {"!la", "/la"}:
        return None
    command = parts[1].lower() if len(parts) > 1 else "help"
    return command, parts[2:]


def handle_command_text(content: str, config: LocalAgentCommandConfig, *, now: str | None = None) -> CommandResult:
    now = now or utc_now_iso()
    parsed = parse_command(content)
    if not parsed:
        return CommandResult("ignored", "")
    command, args = parsed
    if command in {"help", "h", "?"}:
        return CommandResult("help", build_help_reply())
    if command == "status":
        return CommandResult("status", build_status_reply(config))
    if command == "import":
        return run_import(config, now=now)
    if command == "queue":
        return build_queue_reply(config, args)
    if command == "find":
        return build_find_reply(config, args)
    return CommandResult("unknown", f"未知 LocalAgent 指令：`{command}`\n\n{build_help_reply()}")


def truncate_reply(content: str) -> str:
    if len(content) <= MAX_DISCORD_MESSAGE_LENGTH:
        return content
    return content[: MAX_DISCORD_MESSAGE_LENGTH - 20].rstrip() + "\n...[truncated]"


def is_bot_message(message: dict[str, Any]) -> bool:
    author = message.get("author") if isinstance(message.get("author"), dict) else {}
    return bool(author.get("bot"))


def process_local_agent_commands(
    config: LocalAgentCommandConfig,
    client: DiscordClient,
    *,
    now: str | None = None,
) -> list[dict[str, str]]:
    now = now or utc_now_iso()
    if not config.guild_id:
        return []

    channel = client.ensure_text_channel(
        config.guild_id,
        config.category_id,
        command_channel_name(config.channel_prefix),
        topic="LazyCat LocalAgent command channel",
    )
    channel_id = str(channel.get("id", "")).strip()
    if not channel_id:
        raise ValueError("Discord command channel is missing id")

    state_path = resolve_path(config.repo_root, config.state_path)
    state = read_json(state_path, {})
    last_message_id = str(state.get("last_message_id", "")).strip()
    messages = client.list_messages(channel_id, after=last_message_id, limit=20)
    results: list[dict[str, str]] = []
    last_seen = last_message_id

    for message in messages:
        message_id = str(message.get("id", "")).strip()
        if not message_id or is_bot_message(message):
            continue
        last_seen = message_id
        content = str(message.get("content", "")).strip()
        parsed = parse_command(content)
        if not parsed:
            continue
        result = handle_command_text(content, config, now=now)
        if result.reply:
            client.send_message(channel_id, truncate_reply(result.reply))
        results.append({"message_id": message_id, "status": result.status})

    if last_seen != last_message_id:
        state["last_message_id"] = last_seen
        state["last_checked_at"] = now
        state["channel_id"] = channel_id
        write_json(state_path, state)
    return results


def config_from_project(repo_root: Path) -> LocalAgentCommandConfig:
    project_config = load_project_config(repo_root)
    local_agent_root = Path(project_config.local_agent.path).expanduser() if project_config.local_agent.path else Path("")
    if local_agent_root and not local_agent_root.is_absolute():
        local_agent_root = repo_root / local_agent_root
    snapshot_path = Path(project_config.local_agent.snapshot_path).expanduser()
    if not snapshot_path.is_absolute():
        snapshot_path = repo_root / snapshot_path
    return LocalAgentCommandConfig(
        repo_root=repo_root,
        local_agent_root=local_agent_root,
        snapshot_path=snapshot_path,
        queue_path=repo_root / DEFAULT_QUEUE_PATH,
        state_path=repo_root / DEFAULT_STATE_PATH,
        guild_id=project_config.discord.guild_id,
        category_id=project_config.discord.category_id,
        channel_prefix=project_config.discord.channel_prefix,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Process Discord LocalAgent control commands.")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--once", action="store_true", help="Process one polling batch and exit.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    token = os.environ.get("LZCAT_DISCORD_BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("LZCAT_DISCORD_BOT_TOKEN is required")
    config = config_from_project(repo_root)
    results = process_local_agent_commands(config, DiscordClient(token))
    print(json.dumps({"local_agent_commands": results}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
