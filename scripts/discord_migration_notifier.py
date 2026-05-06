from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

try:
    from .migration_workspace import migration_branch_name, normalize_slug
except ImportError:  # pragma: no cover - direct script execution
    from migration_workspace import migration_branch_name, normalize_slug


DISCORD_API_BASE = "https://discord.com/api/v10"
DISCORD_GUILD_TEXT_TYPE = 0
MAX_DISCORD_MESSAGE_LENGTH = 2000
MAX_DISCORD_TOPIC_LENGTH = 1024
MAX_DISCORD_CHANNEL_NAME_LENGTH = 100

DiscordTransport = Callable[[str, str, dict[str, object] | None], object]


def split_discord_message(content: str, *, limit: int = MAX_DISCORD_MESSAGE_LENGTH) -> list[str]:
    if not content:
        return []
    chunk_size = max(1, limit)
    return [content[index : index + chunk_size] for index in range(0, len(content), chunk_size)]


def channel_name_for_slug(slug: str, *, prefix: str = "migration") -> str:
    normalized_prefix = normalize_slug(prefix) or "migration"
    slug_value = str(slug).strip().removesuffix(".git").rstrip("/")
    if "/" in slug_value:
        slug_value = slug_value.rsplit("/", 1)[-1]
    normalized_slug = normalize_slug(slug_value)
    channel_name = f"{normalized_prefix}-{normalized_slug}"
    return channel_name[:MAX_DISCORD_CHANNEL_NAME_LENGTH].rstrip("-") or normalized_prefix[:MAX_DISCORD_CHANNEL_NAME_LENGTH]


def _retry_after_seconds(exc: urllib.error.HTTPError) -> float:
    retry_after = str(exc.headers.get("Retry-After", "")).strip()
    try:
        if retry_after:
            return max(0.0, float(retry_after))
    except ValueError:
        pass
    try:
        body = exc.read().decode("utf-8", errors="replace")
        payload = json.loads(body) if body else {}
    except (OSError, json.JSONDecodeError):
        return 1.0
    if isinstance(payload, dict):
        try:
            return max(0.0, float(payload.get("retry_after") or 1.0))
        except (TypeError, ValueError):
            return 1.0
    return 1.0


def _candidate_description(item: dict[str, Any]) -> str:
    candidate = item.get("candidate")
    if not isinstance(candidate, dict):
        return ""
    return str(candidate.get("description") or candidate.get("summary") or "").strip()


def _candidate_repo_url(item: dict[str, Any]) -> str:
    candidate = item.get("candidate")
    if isinstance(candidate, dict):
        repo_url = str(candidate.get("repo_url", "")).strip()
        if repo_url:
            return repo_url
    source = str(item.get("source", "")).strip()
    if "/" in source and "://" not in source:
        return f"https://github.com/{source}"
    return source


def build_progress_message(item: dict[str, Any], *, status: str, now: str) -> str:
    slug = normalize_slug(str(item.get("slug") or item.get("source") or "unknown"))
    source = str(item.get("source", "")).strip() or slug
    repo_url = _candidate_repo_url(item)
    description = _candidate_description(item)
    branch = migration_branch_name(slug)
    last_error = str(item.get("last_error", "")).strip()
    human_request = item.get("human_request") if isinstance(item.get("human_request"), dict) else {}
    human_question = str(human_request.get("question", "")).strip()
    human_options = human_request.get("options") if isinstance(human_request.get("options"), list) else []

    lines = [
        f"**LazyCat AI 自动移植：{slug}**",
        "",
        f"- 上游：{source}",
        f"- 仓库：{repo_url}" if repo_url else "",
        f"- 分支：{branch}",
        f"- 当前状态：{status}",
        f"- 更新时间：{now}",
        f"- 简介：{description}" if description else "",
        f"- 最近错误：{last_error}" if last_error else "",
        "",
        "**需要你回复**" if status == "waiting_for_human" and human_question else "",
        human_question if status == "waiting_for_human" and human_question else "",
        f"可选：{', '.join(str(option) for option in human_options)}"
        if status == "waiting_for_human" and human_options
        else "",
        "",
        "**移植步骤**",
        f"- 发现与过滤：{_step_marker(status, {'ready', 'scaffolded', 'installed', 'browser_pending', 'browser_failed', 'browser_passed', 'copy_ready', 'publish_ready', 'published'})}",
        f"- 独立 worktree 与 {branch}：{_step_marker(status, {'scaffolded', 'installed', 'browser_pending', 'browser_failed', 'browser_passed', 'copy_ready', 'publish_ready', 'published'})}",
        f"- 构建/安装验收：{_step_marker(status, {'installed', 'browser_pending', 'browser_failed', 'browser_passed', 'copy_ready', 'publish_ready', 'published'})}",
        f"- Browser Use 验收：{_step_marker(status, {'browser_passed', 'copy_ready', 'publish_ready', 'published'})}",
        f"- 上架素材：{_step_marker(status, {'copy_ready', 'publish_ready', 'published'})}",
        f"- 最终上架：{_step_marker(status, {'published'})}",
        "",
        "**发布门槛**",
        "- 桌面截图 2 张",
        "- 手机截图 3 张",
        "- Playground 图文攻略",
        "- 原作者/上游项目归属信息",
        "- Browser Use 功能验收记录",
    ]
    content = "\n".join(line for line in lines if line)
    if len(content) <= MAX_DISCORD_MESSAGE_LENGTH:
        return content
    return content[: MAX_DISCORD_MESSAGE_LENGTH - 20].rstrip() + "\n...[truncated]"


def _step_marker(status: str, completed_states: set[str]) -> str:
    return "[x]" if status in completed_states else "[ ]"


@dataclass(frozen=True)
class DiscordClient:
    token: str
    api_base: str = DISCORD_API_BASE
    transport: DiscordTransport | None = None
    max_retries: int = 2

    def request_json(self, method: str, route: str, payload: dict[str, object] | None = None) -> object:
        if self.transport:
            return self.transport(method, route, payload)

        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self.api_base.rstrip("/") + route,
            data=body,
            method=method,
            headers={
                "Authorization": f"Bot {self.token}",
                "Content-Type": "application/json",
                "User-Agent": "lzcat-auto-migration/1.0",
            },
        )
        attempts = max(1, self.max_retries + 1)
        response_body = b""
        for attempt in range(attempts):
            try:
                with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - Discord API endpoint.
                    response_body = response.read()
                break
            except urllib.error.HTTPError as exc:
                if exc.code != 429 or attempt >= attempts - 1:
                    raise
                time.sleep(min(_retry_after_seconds(exc), 5.0))
        if not response_body:
            return {}
        return json.loads(response_body.decode("utf-8"))

    def list_guild_channels(self, guild_id: str) -> list[dict[str, Any]]:
        response = self.request_json("GET", f"/guilds/{guild_id}/channels")
        if not isinstance(response, list):
            raise ValueError("Discord list guild channels response is not a list")
        return [channel for channel in response if isinstance(channel, dict)]

    def ensure_text_channel(self, guild_id: str, category_id: str, name: str, *, topic: str = "") -> dict[str, Any]:
        for channel in self.list_guild_channels(guild_id):
            if channel.get("type") != DISCORD_GUILD_TEXT_TYPE:
                continue
            if channel.get("name") != name:
                continue
            if category_id and channel.get("parent_id") != category_id:
                continue
            return channel

        payload: dict[str, object] = {"name": name, "type": DISCORD_GUILD_TEXT_TYPE}
        if category_id:
            payload["parent_id"] = category_id
        if topic:
            payload["topic"] = topic[:MAX_DISCORD_TOPIC_LENGTH]
        response = self.request_json("POST", f"/guilds/{guild_id}/channels", payload)
        if not isinstance(response, dict):
            raise ValueError("Discord create guild channel response is not an object")
        return response

    def send_message(
        self,
        channel_id: str,
        content: str,
        *,
        components: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, object] = {"content": content, "allowed_mentions": {"parse": []}}
        if components is not None:
            payload["components"] = components
        response = self.request_json("POST", f"/channels/{channel_id}/messages", payload)
        if not isinstance(response, dict):
            raise ValueError("Discord send message response is not an object")
        return response

    def add_reaction(self, channel_id: str, message_id: str, emoji: str) -> None:
        self.request_json("PUT", f"/channels/{channel_id}/messages/{message_id}/reactions/{emoji}/@me")

    def edit_message(
        self,
        channel_id: str,
        message_id: str,
        content: str,
        *,
        components: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, object] = {"content": content, "allowed_mentions": {"parse": []}}
        if components is not None:
            payload["components"] = components
        response = self.request_json("PATCH", f"/channels/{channel_id}/messages/{message_id}", payload)
        if not isinstance(response, dict):
            raise ValueError("Discord edit message response is not an object")
        return response

    def list_messages(self, channel_id: str, *, after: str = "", limit: int = 20) -> list[dict[str, Any]]:
        query: dict[str, str] = {"limit": str(max(1, min(limit, 100)))}
        if after:
            query["after"] = after
        route = f"/channels/{channel_id}/messages?{urllib.parse.urlencode(query)}"
        response = self.request_json("GET", route)
        if not isinstance(response, list):
            raise ValueError("Discord list messages response is not a list")
        return [message for message in response if isinstance(message, dict)]

    def delete_channel(self, channel_id: str) -> dict[str, Any]:
        response = self.request_json("DELETE", f"/channels/{channel_id}")
        if not isinstance(response, dict):
            raise ValueError("Discord delete channel response is not an object")
        return response

    def bulk_overwrite_guild_application_commands(
        self,
        application_id: str,
        guild_id: str,
        commands: list[dict[str, object]],
    ) -> list[dict[str, Any]]:
        response = self.request_json("PUT", f"/applications/{application_id}/guilds/{guild_id}/commands", commands)  # type: ignore[arg-type]
        if not isinstance(response, list):
            raise ValueError("Discord bulk overwrite guild application commands response is not a list")
        return [command for command in response if isinstance(command, dict)]

    def create_interaction_response(
        self,
        interaction_id: str,
        interaction_token: str,
        payload: dict[str, object],
    ) -> dict[str, Any]:
        response = self.request_json("POST", f"/interactions/{interaction_id}/{interaction_token}/callback", payload)
        if response == {}:
            return {}
        if not isinstance(response, dict):
            raise ValueError("Discord create interaction response is not an object")
        return response

    def create_followup_message(
        self,
        application_id: str,
        interaction_token: str,
        content: str,
    ) -> dict[str, Any]:
        response = self.request_json(
            "POST",
            f"/webhooks/{application_id}/{interaction_token}",
            {"content": content, "allowed_mentions": {"parse": []}},
        )
        if not isinstance(response, dict):
            raise ValueError("Discord create followup message response is not an object")
        return response


@dataclass(frozen=True)
class MigrationDiscordNotifier:
    client: DiscordClient
    guild_id: str
    category_id: str = ""
    channel_prefix: str = "migration"

    def publish_update(self, item: dict[str, Any], *, status: str, now: str) -> dict[str, Any]:
        slug = normalize_slug(str(item.get("slug") or item.get("source") or "unknown"))
        channel_name = channel_name_for_slug(slug, prefix=self.channel_prefix)
        source = str(item.get("source", "")).strip() or slug
        channel = self.client.ensure_text_channel(
            self.guild_id,
            self.category_id,
            channel_name,
            topic=f"LazyCat migration: {source}"[:MAX_DISCORD_TOPIC_LENGTH],
        )
        channel_id = str(channel.get("id", "")).strip()
        if not channel_id:
            raise ValueError("Discord channel response is missing id")

        content = build_progress_message(item, status=status, now=now)
        discord_state = item.get("discord") if isinstance(item.get("discord"), dict) else {}
        message_id = str(discord_state.get("message_id", "")).strip()
        existing_channel_id = str(discord_state.get("channel_id", "")).strip()
        if message_id and existing_channel_id == channel_id:
            try:
                message = self.client.edit_message(channel_id, message_id, content)
            except urllib.error.HTTPError as exc:
                if exc.code not in {403, 404}:
                    raise
                message = self.client.send_message(channel_id, content)
        else:
            message = self.client.send_message(channel_id, content)

        next_state = {
            "channel_id": channel_id,
            "message_id": str(message.get("id", message_id)).strip(),
            "last_status": status,
            "last_update_at": now,
        }
        item["discord"] = next_state
        return next_state
