#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import urllib.error
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
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
ACTIONABLE_CANDIDATE_STATUSES = {"portable", "needs_review"}
LOCAL_AGENT_PENDING_STATES = {
    "portable": "local_agent_pending_decision",
    "needs_review": "local_agent_needs_decision",
}
COMPONENT_ACTION_ROW = 1
COMPONENT_BUTTON = 2
BUTTON_PRIMARY = 1
BUTTON_SECONDARY = 2
BUTTON_SUCCESS = 3
BUTTON_DANGER = 4

DECISION_ACTIONS: dict[str, tuple[str, str, str]] = {
    "queue": ("ready", "queued", "已加入待移植队列"),
    "review": ("discovery_review", "review", "已进入发现复核"),
    "defer": ("local_agent_deferred", "deferred", "已暂缓"),
    "exclude": ("filtered_out", "excluded", "已排除"),
}


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
    decision_card_limit: int = 5
    decision_user_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class CommandResult:
    status: str
    reply: str


@dataclass(frozen=True)
class DecisionInteractionResult:
    status: str
    reply: str
    message_content: str = ""
    components: list[dict[str, Any]] | None = None
    ephemeral: bool = False


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def local_agent_candidate_source(candidate: dict[str, Any]) -> str:
    full_name = str(candidate.get("full_name", "")).strip()
    if full_name:
        return full_name
    repo_url = str(candidate.get("repo_url", "")).strip()
    if repo_url:
        return repo_url
    raise ValueError("LocalAgent candidate is missing full_name and repo_url")


def local_agent_candidate_id(candidate: dict[str, Any]) -> str:
    source = local_agent_candidate_source(candidate)
    if "github.com/" in source:
        source = source.rstrip("/").removesuffix(".git").rsplit("github.com/", 1)[-1]
    return f"github:{source.lower()}"


def local_agent_candidate_slug(candidate: dict[str, Any]) -> str:
    repo = str(candidate.get("repo", "")).strip()
    if repo:
        return normalize_slug(repo)
    source = local_agent_candidate_source(candidate).rstrip("/").removesuffix(".git")
    if "/" in source:
        source = source.rsplit("/", 1)[-1]
    return normalize_slug(source)


def decision_token_for_item_id(item_id: str) -> str:
    return hashlib.sha1(item_id.encode("utf-8")).hexdigest()[:16]


def _state_dict(parent: dict[str, Any], key: str) -> dict[str, Any]:
    value = parent.get(key)
    return value if isinstance(value, dict) else {}


def _candidate_status(candidate: dict[str, Any]) -> str:
    return str(candidate.get("status", "")).strip().lower()


def _candidate_repo_url(candidate: dict[str, Any]) -> str:
    repo_url = str(candidate.get("repo_url", "")).strip()
    if repo_url:
        return repo_url
    source = str(candidate.get("full_name", "")).strip()
    if "/" in source and "://" not in source:
        return f"https://github.com/{source}"
    return source


def _candidate_description(candidate: dict[str, Any], *, limit: int = 220) -> str:
    description = str(candidate.get("description", "")).strip()
    if len(description) <= limit:
        return description
    return description[: limit - 3].rstrip() + "..."


def build_decision_card_content(candidate: dict[str, Any], *, decision_text: str = "") -> str:
    source = local_agent_candidate_source(candidate)
    status = _candidate_status(candidate)
    repo_url = _candidate_repo_url(candidate)
    description = _candidate_description(candidate)
    language = str(candidate.get("language", "")).strip()
    stars = int(candidate.get("total_stars") or 0)
    status_reason = str(candidate.get("status_reason", "")).strip()
    decision_hint = "可进入待移植，等待确认。" if status == "portable" else "需要人工决断。"
    lines = [
        f"**LocalAgent 候选：{source}**",
        f"- 状态：{status}",
        f"- 判断：{decision_hint}",
        f"- 仓库：{repo_url}" if repo_url else "",
        f"- 语言：{language}" if language else "",
        f"- Stars：{stars}" if stars else "",
        f"- 简介：{description}" if description else "",
        f"- 原因：{status_reason}" if status_reason else "",
        f"- 决策：{decision_text}" if decision_text else "",
    ]
    return truncate_reply("\n".join(line for line in lines if line))


def _decision_button(label: str, style: int, action: str, token: str, *, disabled: bool) -> dict[str, Any]:
    return {
        "type": COMPONENT_BUTTON,
        "style": style,
        "label": label,
        "custom_id": f"la:{action}:{token}",
        "disabled": disabled,
    }


def build_decision_components(status: str, token: str, *, disabled: bool = False) -> list[dict[str, Any]]:
    if status == "needs_review":
        buttons = [
            _decision_button("交给复核", BUTTON_PRIMARY, "review", token, disabled=disabled),
            _decision_button("直接待移植", BUTTON_SUCCESS, "queue", token, disabled=disabled),
            _decision_button("暂缓", BUTTON_SECONDARY, "defer", token, disabled=disabled),
            _decision_button("排除", BUTTON_DANGER, "exclude", token, disabled=disabled),
        ]
    else:
        buttons = [
            _decision_button("进入待移植", BUTTON_SUCCESS, "queue", token, disabled=disabled),
            _decision_button("需要复核", BUTTON_PRIMARY, "review", token, disabled=disabled),
            _decision_button("暂缓", BUTTON_SECONDARY, "defer", token, disabled=disabled),
            _decision_button("排除", BUTTON_DANGER, "exclude", token, disabled=disabled),
        ]
    return [{"type": COMPONENT_ACTION_ROW, "components": buttons}]


def _queue_item_for_decision(candidate: dict[str, Any], *, state: str, now: str) -> dict[str, Any]:
    return {
        "id": local_agent_candidate_id(candidate),
        "source": local_agent_candidate_source(candidate),
        "slug": local_agent_candidate_slug(candidate),
        "state": state,
        "candidate_status": str(candidate.get("status", "")).strip(),
        "candidate": candidate,
        "attempts": 0,
        "created_at": now,
        "updated_at": now,
    }


def _upsert_queue_item(config: LocalAgentCommandConfig, candidate: dict[str, Any], *, state: str, now: str) -> None:
    queue_path = resolve_path(config.repo_root, config.queue_path)
    queue = read_json(queue_path, {"items": [], "schema_version": 1, "meta": {"created_at": now}})
    items = queue.get("items") if isinstance(queue.get("items"), list) else []
    next_item = _queue_item_for_decision(candidate, state=state, now=now)
    replaced = False
    next_items: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if str(item.get("id", "")).strip() == next_item["id"]:
            merged = dict(item)
            merged.update(next_item)
            next_items.append(merged)
            replaced = True
        else:
            next_items.append(item)
    if not replaced:
        next_items.append(next_item)
    meta = queue.get("meta") if isinstance(queue.get("meta"), dict) else {}
    meta.setdefault("created_at", now)
    meta["updated_at"] = now
    queue["schema_version"] = 1
    queue["meta"] = meta
    queue["items"] = next_items
    write_json(queue_path, queue)


def _candidate_by_item_id(config: LocalAgentCommandConfig, item_id: str) -> dict[str, Any] | None:
    for candidate in snapshot_candidates(config):
        if local_agent_candidate_id(candidate) == item_id:
            return candidate
    return None


def publish_decision_cards(
    config: LocalAgentCommandConfig,
    client: DiscordClient,
    channel_id: str,
    state: dict[str, Any],
) -> int:
    limit = max(0, config.decision_card_limit)
    if limit <= 0:
        return 0
    decision_cards = _state_dict(state, "decision_cards")
    decision_tokens = _state_dict(state, "decision_tokens")
    published = 0
    for candidate in snapshot_candidates(config):
        if published >= limit:
            break
        status = _candidate_status(candidate)
        if status not in ACTIONABLE_CANDIDATE_STATUSES:
            continue
        item_id = local_agent_candidate_id(candidate)
        if item_id in decision_cards:
            continue
        token = decision_token_for_item_id(item_id)
        message = client.send_message(
            channel_id,
            build_decision_card_content(candidate),
            components=build_decision_components(status, token),
        )
        decision_cards[item_id] = {
            "message_id": str(message.get("id", "")).strip(),
            "status": status,
            "token": token,
        }
        decision_tokens[token] = item_id
        published += 1
    if published:
        state["decision_cards"] = decision_cards
        state["decision_tokens"] = decision_tokens
    return published


def _interaction_user_id(interaction: dict[str, Any]) -> str:
    member = interaction.get("member") if isinstance(interaction.get("member"), dict) else {}
    user = member.get("user") if isinstance(member.get("user"), dict) else {}
    return str(user.get("id", "")).strip()


def handle_decision_interaction(
    interaction: dict[str, Any],
    config: LocalAgentCommandConfig,
    *,
    now: str | None = None,
) -> DecisionInteractionResult | None:
    now = now or utc_now_iso()
    data = interaction.get("data") if isinstance(interaction.get("data"), dict) else {}
    custom_id = str(data.get("custom_id", "")).strip()
    if not custom_id.startswith("la:"):
        return None
    parts = custom_id.split(":", 2)
    if len(parts) != 3:
        return DecisionInteractionResult("local_agent_decision_invalid", "无效的 LocalAgent 决策按钮。", ephemeral=True)
    _, action, token = parts
    if action not in DECISION_ACTIONS:
        return DecisionInteractionResult("local_agent_decision_invalid", "未知的 LocalAgent 决策动作。", ephemeral=True)
    user_id = _interaction_user_id(interaction)
    if config.decision_user_ids and user_id not in config.decision_user_ids:
        return DecisionInteractionResult("local_agent_decision_unauthorized", "你没有权限操作这个 LocalAgent 决策。", ephemeral=True)

    state_path = resolve_path(config.repo_root, config.state_path)
    state = read_json(state_path, {})
    item_id = str(_state_dict(state, "decision_tokens").get(token, "")).strip()
    if not item_id:
        return DecisionInteractionResult("local_agent_decision_unknown", "这个 LocalAgent 决策已失效。", ephemeral=True)
    candidate = _candidate_by_item_id(config, item_id)
    if not candidate:
        return DecisionInteractionResult("local_agent_decision_missing_candidate", "找不到对应的 LocalAgent 候选。", ephemeral=True)

    next_state, status_suffix, decision_text = DECISION_ACTIONS[action]
    _upsert_queue_item(config, candidate, state=next_state, now=now)
    decision_cards = _state_dict(state, "decision_cards")
    card = _state_dict(decision_cards, item_id)
    card.update(
        {
            "decision": action,
            "decided_at": now,
            "decided_by": user_id,
            "queue_state": next_state,
        }
    )
    decision_cards[item_id] = card
    state["decision_cards"] = decision_cards
    write_json(state_path, state)

    content = build_decision_card_content(candidate, decision_text=decision_text)
    return DecisionInteractionResult(
        f"local_agent_decision_{status_suffix}",
        decision_text,
        message_content=content,
        components=build_decision_components(_candidate_status(candidate), token, disabled=True),
    )


def ensure_local_agent_channel(config: LocalAgentCommandConfig, client: DiscordClient) -> dict[str, Any]:
    name = command_channel_name(config.channel_prefix)
    channels = client.list_guild_channels(config.guild_id)
    for channel in channels:
        if channel.get("type") == 0 and channel.get("name") == name and channel.get("parent_id") == config.category_id:
            return channel
    for channel in channels:
        if channel.get("type") == 0 and channel.get("name") == name:
            return channel
    try:
        return client.ensure_text_channel(
            config.guild_id,
            config.category_id,
            name,
            topic="LazyCat LocalAgent command channel",
        )
    except urllib.error.HTTPError as exc:
        if not config.category_id or exc.code != 400:
            raise
        return client.ensure_text_channel(
            config.guild_id,
            "",
            name,
            topic="LazyCat LocalAgent command channel",
        )


def snapshot_signature(config: LocalAgentCommandConfig) -> str:
    path = resolve_path(config.repo_root, config.snapshot_path)
    if not path.exists():
        return ""
    stat = path.stat()
    return f"{stat.st_mtime_ns}:{stat.st_size}"


def maybe_publish_snapshot_report(
    config: LocalAgentCommandConfig,
    client: DiscordClient,
    channel_id: str,
    state: dict[str, Any],
) -> bool:
    signature = snapshot_signature(config)
    if not signature or state.get("last_snapshot_signature") == signature:
        return False
    client.send_message(channel_id, truncate_reply(build_status_reply(config)))
    state["last_snapshot_signature"] = signature
    return True


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

    channel = ensure_local_agent_channel(config, client)
    channel_id = str(channel.get("id", "")).strip()
    if not channel_id:
        raise ValueError("Discord command channel is missing id")

    state_path = resolve_path(config.repo_root, config.state_path)
    state = read_json(state_path, {})
    state_changed = False
    results: list[dict[str, str]] = []
    if maybe_publish_snapshot_report(config, client, channel_id, state):
        results.append({"message_id": "", "status": "local_agent_reported"})
        state_changed = True
    decision_card_count = publish_decision_cards(config, client, channel_id, state)
    if decision_card_count:
        results.append(
            {
                "message_id": "",
                "status": "local_agent_decision_cards_reported",
                "count": str(decision_card_count),
            }
        )
        state_changed = True
    last_message_id = str(state.get("last_message_id", "")).strip()
    messages = client.list_messages(channel_id, after=last_message_id, limit=20)
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
        state_changed = True
    if state.get("channel_id") != channel_id:
        state["channel_id"] = channel_id
        state_changed = True
    if state_changed:
        state["last_checked_at"] = now
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
    parser.add_argument("--daemon", action="store_true", help="Continuously process LocalAgent reports and commands.")
    parser.add_argument("--interval-seconds", type=float, default=300.0, help="Polling interval when running as a daemon.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    token = os.environ.get("LZCAT_DISCORD_BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("LZCAT_DISCORD_BOT_TOKEN is required")
    config = config_from_project(repo_root)
    client = DiscordClient(token)
    if args.daemon:
        interval = max(15.0, float(args.interval_seconds))
        while True:
            results = process_local_agent_commands(config, client)
            print(json.dumps({"checked_at": utc_now_iso(), "local_agent_commands": results}, ensure_ascii=False, sort_keys=True), flush=True)
            time.sleep(interval)
    results = process_local_agent_commands(config, client)
    print(json.dumps({"local_agent_commands": results}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
