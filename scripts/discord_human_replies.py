from __future__ import annotations

from typing import Any

try:
    from .discord_migration_notifier import DiscordClient
except ImportError:  # pragma: no cover - direct script execution
    from discord_migration_notifier import DiscordClient


def _queue_items(queue: dict[str, Any]) -> list[dict[str, Any]]:
    items = queue.get("items")
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _author_is_bot(message: dict[str, Any]) -> bool:
    author = message.get("author")
    return isinstance(author, dict) and bool(author.get("bot"))


def _first_human_message(messages: list[dict[str, Any]]) -> dict[str, Any] | None:
    for message in messages:
        if not isinstance(message, dict) or _author_is_bot(message):
            continue
        content = str(message.get("content", "")).strip()
        message_id = str(message.get("id", "")).strip()
        if content and message_id:
            return message
    return None


def _message_author(message: dict[str, Any]) -> dict[str, str]:
    author = message.get("author")
    if not isinstance(author, dict):
        return {"author_id": "", "author_username": ""}
    return {
        "author_id": str(author.get("id", "")).strip(),
        "author_username": str(author.get("username") or author.get("global_name") or "").strip(),
    }


def _acknowledge_reply(client: DiscordClient, channel_id: str) -> str:
    message = client.send_message(channel_id, "已收到，我会继续让 Codex 处理。")
    return str(message.get("id", "")).strip()


def apply_human_replies(queue: dict[str, Any], client: DiscordClient, *, now: str) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    for item in _queue_items(queue):
        if item.get("state") != "waiting_for_human":
            continue
        if not isinstance(item.get("human_request"), dict):
            continue
        if isinstance(item.get("human_response"), dict):
            continue

        discord = item.get("discord") if isinstance(item.get("discord"), dict) else {}
        channel_id = str(discord.get("channel_id", "")).strip()
        if not channel_id:
            continue
        after = str(discord.get("last_human_message_id") or discord.get("message_id") or "").strip()
        messages = client.list_messages(channel_id, after=after, limit=20)
        message = _first_human_message(messages)
        if not message:
            continue

        message_id = str(message.get("id", "")).strip()
        author = _message_author(message)
        item["human_response"] = {
            "content": str(message.get("content", "")).strip(),
            "message_id": message_id,
            "channel_id": channel_id,
            "received_at": now,
            **author,
        }
        discord["last_human_message_id"] = message_id
        discord["last_human_checked_at"] = now
        ack_id = _acknowledge_reply(client, channel_id)
        if ack_id:
            discord["last_human_ack_message_id"] = ack_id
        item["discord"] = discord
        item["updated_at"] = now
        results.append({"id": str(item.get("id", "")).strip(), "status": "human_response_received", "message_id": message_id})
    return results
