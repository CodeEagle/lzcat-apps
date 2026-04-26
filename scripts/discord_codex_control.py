#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import time
from collections import Counter
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
DEFAULT_CODEX_MODEL = "gpt-5.5"
DEFAULT_CODEX_FALLBACK_MODEL = "gpt-5.4"
CONTROL_CHANNEL_NAME = "migration-control"
CONTROL_ONLY_SUFFIXES = {"control", "dashboard", "local-agent", "codex-control"}

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
    control = client.ensure_text_channel(
        config.guild_id,
        config.category_id,
        config.control_channel,
        topic="LazyCat Codex control channel",
    )
    items = queue_items(config)
    channels = client.list_guild_channels(config.guild_id)
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


def app_context_text(context: ChannelContext) -> str:
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

    for context in contexts:
        channel_state = channels_state.get(context.channel_id)
        if not isinstance(channel_state, dict):
            channel_state = {}
        last_message_id = str(channel_state.get("last_message_id") or state.get("last_message_id") or "").strip()
        try:
            messages = order_messages(client.list_messages(context.channel_id, after=last_message_id, limit=20))
        except Exception as exc:  # pragma: no cover - exact HTTP exception type varies.
            channel_state["last_error"] = str(exc)
            channel_state["last_checked_at"] = now
            channel_state["channel_name"] = context.channel_name
            channel_state["slug"] = context.slug
            channels_state[context.channel_id] = channel_state
            results.append({"channel_id": context.channel_id, "message_id": "", "status": "channel_read_failed"})
            continue
        last_seen = last_message_id
        for message in messages:
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
            will_run = parsed.kind == "codex" and not (context.scope == "migration" and not context.item)
            send_error = ""
            if will_run:
                try:
                    client.send_message(context.channel_id, truncate_reply(f"收到，正在交给 Codex 处理：{parsed.instruction}"))
                except Exception as exc:  # pragma: no cover - exact HTTP exception type varies.
                    send_error = str(exc)
            result = handle_command(parsed, context, config, runner=runner, now=now, task_id=message_id)
            if result.reply:
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
            results.append(entry)

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

    for context in contexts:
        channel_state = channels_state.get(context.channel_id)
        if not isinstance(channel_state, dict):
            channel_state = {}
        try:
            messages = client.list_messages(context.channel_id, limit=1)
        except Exception as exc:  # pragma: no cover - exact HTTP exception type varies.
            channel_state["last_error"] = str(exc)
            channel_state["last_checked_at"] = now
            channel_state["channel_name"] = context.channel_name
            channel_state["slug"] = context.slug
            channels_state[context.channel_id] = channel_state
            results.append({"channel_id": context.channel_id, "message_id": "", "status": "channel_read_failed"})
            continue
        last_message_id = ""
        if messages:
            last_message_id = str(messages[0].get("id", "")).strip()
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
    interval = max(5.0, float(args.interval_seconds))
    while True:
        results = process_codex_control_commands(config, client)
        print(json.dumps({"checked_at": utc_now_iso(), "codex_control": results}, ensure_ascii=False, sort_keys=True), flush=True)
        time.sleep(interval)


if __name__ == "__main__":
    raise SystemExit(main())
