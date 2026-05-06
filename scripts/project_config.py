from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class LazyCatConfig:
    developer_apps_url: str = ""
    developer_id: str = ""
    status_sync_enabled: bool = False
    status_sync_source: str = ""


@dataclass(frozen=True)
class MigrationConfig:
    template_branch: str = "template"
    workspace_root: str = ""
    codex_worker_model: str = "claude-sonnet-4-6"
    desktop_screenshots_required: int = 2
    mobile_screenshots_required: int = 3
    playground_required: bool = True


@dataclass(frozen=True)
class DiscordConfig:
    enabled: bool = False
    guild_id: str = ""
    category_id: str = ""
    channel_prefix: str = "migration"


@dataclass(frozen=True)
class LocalAgentConfig:
    enabled: bool = False
    path: str = ""
    snapshot_path: str = "registry/candidates/local-agent-latest.json"


@dataclass(frozen=True)
class CodexControlConfig:
    enabled: bool = False
    control_channel: str = "migration-control"
    state_path: str = "registry/auto-migration/discord-codex-control.json"
    task_root: str = "registry/auto-migration/codex-control-tasks"
    model: str = "claude-sonnet-4-6"
    dashboard_model: str = "claude-sonnet-4-6"
    dashboard_reasoning_effort: str = "xhigh"
    dashboard_session_max_input_tokens: int = 500000
    bot_user_id: str = ""
    mention_role_ids: tuple[str, ...] = ()
    cti_home: str = ""
    secret_admin_channel_id: str = ""
    secret_admin_user_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProjectConfig:
    lazycat: LazyCatConfig
    migration: MigrationConfig
    discord: DiscordConfig
    local_agent: LocalAgentConfig
    codex_control: CodexControlConfig


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _as_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else default


def _as_str_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip())


def load_project_config(repo_root: Path) -> ProjectConfig:
    path = repo_root / "project-config.json"
    if not path.exists():
        return ProjectConfig(
            lazycat=LazyCatConfig(),
            migration=MigrationConfig(),
            discord=DiscordConfig(),
            local_agent=LocalAgentConfig(),
            codex_control=CodexControlConfig(),
        )

    payload = json.loads(path.read_text(encoding="utf-8"))
    lazycat = payload.get("lazycat", {}) if isinstance(payload, dict) else {}
    status_sync = lazycat.get("status_sync", {}) if isinstance(lazycat, dict) else {}
    migration = payload.get("migration", {}) if isinstance(payload, dict) else {}
    discord = payload.get("discord", {}) if isinstance(payload, dict) else {}
    local_agent = payload.get("local_agent", {}) if isinstance(payload, dict) else {}
    codex_control = payload.get("codex_control", {}) if isinstance(payload, dict) else {}

    return ProjectConfig(
        lazycat=LazyCatConfig(
            developer_apps_url=str(lazycat.get("developer_apps_url", "")).strip(),
            developer_id=str(lazycat.get("developer_id", "")).strip(),
            status_sync_enabled=_as_bool(status_sync.get("enabled"), False),
            status_sync_source=str(status_sync.get("source", "")).strip(),
        ),
        migration=MigrationConfig(
            template_branch=str(migration.get("template_branch", "template")).strip() or "template",
            workspace_root=str(migration.get("workspace_root", "")).strip(),
            codex_worker_model=str(migration.get("codex_worker_model", "claude-sonnet-4-6")).strip() or "claude-sonnet-4-6",
            desktop_screenshots_required=_as_int(migration.get("desktop_screenshots_required"), 2),
            mobile_screenshots_required=_as_int(migration.get("mobile_screenshots_required"), 3),
            playground_required=_as_bool(migration.get("playground_required"), True),
        ),
        discord=DiscordConfig(
            enabled=_as_bool(discord.get("enabled"), False),
            guild_id=str(discord.get("guild_id", "")).strip(),
            category_id=str(discord.get("category_id", "")).strip(),
            channel_prefix=str(discord.get("channel_prefix", "migration")).strip() or "migration",
        ),
        local_agent=LocalAgentConfig(
            enabled=_as_bool(local_agent.get("enabled"), False),
            path=str(local_agent.get("path", "")).strip(),
            snapshot_path=str(local_agent.get("snapshot_path", "registry/candidates/local-agent-latest.json")).strip()
            or "registry/candidates/local-agent-latest.json",
        ),
        codex_control=CodexControlConfig(
            enabled=_as_bool(codex_control.get("enabled"), False),
            control_channel=str(codex_control.get("control_channel", "migration-control")).strip() or "migration-control",
            state_path=str(
                codex_control.get("state_path", "registry/auto-migration/discord-codex-control.json")
            ).strip()
            or "registry/auto-migration/discord-codex-control.json",
            task_root=str(codex_control.get("task_root", "registry/auto-migration/codex-control-tasks")).strip()
            or "registry/auto-migration/codex-control-tasks",
            model=str(codex_control.get("model", "claude-sonnet-4-6")).strip() or "claude-sonnet-4-6",
            dashboard_model=str(codex_control.get("dashboard_model", "claude-sonnet-4-6")).strip() or "claude-sonnet-4-6",
            dashboard_reasoning_effort=str(codex_control.get("dashboard_reasoning_effort", "xhigh")).strip()
            or "xhigh",
            dashboard_session_max_input_tokens=_as_int(
                codex_control.get("dashboard_session_max_input_tokens"),
                500000,
            ),
            bot_user_id=str(codex_control.get("bot_user_id", "")).strip(),
            mention_role_ids=_as_str_tuple(codex_control.get("mention_role_ids")),
            cti_home=str(codex_control.get("cti_home", "")).strip(),
            secret_admin_channel_id=str(codex_control.get("secret_admin_channel_id", "")).strip(),
            secret_admin_user_ids=_as_str_tuple(codex_control.get("secret_admin_user_ids")),
        ),
    )
