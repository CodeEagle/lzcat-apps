#!/usr/bin/env python3
"""Awaiting-Human SLA reminder — surfaces stuck Project items.

For every active Project item whose Status field is "Awaiting-Human" and whose
Last Run date is missing or older than the SLA window (default 24h), emit a
markdown summary. With --publish-discord, post that summary to the
project-config.json `codex_control.control_channel` (default `migration-control`)
in the Discord guild from `discord.guild_id`.

Pure logic (filtering, summary rendering) is exposed for unit tests; the network
layer is a thin wrapper around the existing DiscordClient + project_board
helpers, which already have their own coverage.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parent))

from project_board import (  # noqa: E402  (sibling-script import)
    _item_field_map,
    list_project_items,
    load_cache,
)


DEFAULT_SLA_HOURS = 24


def _parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            return datetime.fromisoformat(text[:-1]).replace(tzinfo=timezone.utc)
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def stale_awaiting_human(
    items: Iterable[dict[str, Any]],
    *,
    now: datetime,
    sla_hours: int = DEFAULT_SLA_HOURS,
) -> list[dict[str, Any]]:
    """Return Awaiting-Human items whose Last Run is missing or older than SLA."""
    cutoff = now - timedelta(hours=sla_hours)
    out: list[dict[str, Any]] = []
    for item in items:
        if item.get("isArchived"):
            continue
        flat = _item_field_map(item)
        status = flat.get("Status")
        status_name = status.get("name") if isinstance(status, dict) else status
        if status_name != "Awaiting-Human":
            continue
        last_run_raw = flat.get("Last Run")
        last_run = _parse_iso(str(last_run_raw)) if last_run_raw else None
        if last_run is None or last_run <= cutoff:
            out.append(
                {
                    "slug": str(flat.get("Slug") or "").strip(),
                    "upstream": flat.get("Upstream") or "",
                    "branch": flat.get("Branch") or "",
                    "pr": flat.get("PR") or "",
                    "last_run": last_run.isoformat() if last_run else "",
                    "stale_hours": (
                        round((now - last_run).total_seconds() / 3600, 1) if last_run else None
                    ),
                }
            )
    out.sort(key=lambda x: (x["last_run"] or "", x["slug"]))
    return out


def render_markdown(stale: list[dict[str, Any]], *, sla_hours: int) -> str:
    if not stale:
        return f":white_check_mark: No Awaiting-Human items stuck > {sla_hours}h."
    lines = [f":hourglass: **{len(stale)} Awaiting-Human items stuck > {sla_hours}h**", ""]
    for item in stale:
        slug = item["slug"] or "(unknown)"
        bits = [f"`{slug}`"]
        if item["stale_hours"] is not None:
            bits.append(f"{item['stale_hours']}h since Last Run")
        else:
            bits.append("no Last Run recorded")
        if item["upstream"]:
            bits.append(str(item["upstream"]))
        if item["pr"]:
            bits.append(f"PR: {item['pr']}")
        lines.append("- " + " — ".join(bits))
    return "\n".join(lines)


def _publish_discord(message: str) -> None:
    """Best-effort post to the migration-control channel."""
    try:
        from discord_migration_notifier import DiscordClient
        from project_config import load_project_config
    except ImportError as exc:
        raise RuntimeError(f"Discord helpers unavailable: {exc}") from exc

    repo_root = Path(__file__).resolve().parents[1]
    config = load_project_config(repo_root)
    token = os.environ.get("LZCAT_DISCORD_BOT_TOKEN", "").strip()
    guild_id = (config.discord.guild_id or "").strip()
    category_id = (config.discord.category_id or "").strip()
    channel_name = (config.codex_control.control_channel or "migration-control").strip()
    if not (token and guild_id and category_id):
        raise RuntimeError(
            "LZCAT_DISCORD_BOT_TOKEN / discord.guild_id / discord.category_id required for --publish-discord"
        )
    client = DiscordClient(token=token)
    channel = client.ensure_text_channel(guild_id, category_id, channel_name)
    client.send_message(channel_id=str(channel["id"]), content=message)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    p.add_argument("--sla-hours", type=int, default=DEFAULT_SLA_HOURS)
    p.add_argument("--publish-discord", action="store_true")
    p.add_argument("--now", default="", help="Override current time (ISO 8601, mostly for testing)")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    cache = load_cache(repo_root)
    project = cache.get("project") or {}
    project_id = project.get("project_id")
    if not project_id:
        print("Project not bootstrapped — run `project_board.py bootstrap` first.", file=sys.stderr)
        return 2

    now = _parse_iso(args.now) or datetime.now(timezone.utc)
    items = list_project_items(project_id)
    stale = stale_awaiting_human(items, now=now, sla_hours=args.sla_hours)
    message = render_markdown(stale, sla_hours=args.sla_hours)
    print(message)

    if args.publish_discord and stale:
        try:
            _publish_discord(message)
        except RuntimeError as exc:
            # Discord may be intentionally unconfigured (e.g. user said "skip
            # Discord"). Surface the reason but don't fail the workflow — the
            # markdown report is already on stdout for the operator to see.
            print(f"sla_reminder: Discord publish skipped — {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
