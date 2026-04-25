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
class ProjectConfig:
    lazycat: LazyCatConfig


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def load_project_config(repo_root: Path) -> ProjectConfig:
    path = repo_root / "project-config.json"
    if not path.exists():
        return ProjectConfig(lazycat=LazyCatConfig())

    payload = json.loads(path.read_text(encoding="utf-8"))
    lazycat = payload.get("lazycat", {}) if isinstance(payload, dict) else {}
    status_sync = lazycat.get("status_sync", {}) if isinstance(lazycat, dict) else {}

    return ProjectConfig(
        lazycat=LazyCatConfig(
            developer_apps_url=str(lazycat.get("developer_apps_url", "")).strip(),
            developer_id=str(lazycat.get("developer_id", "")).strip(),
            status_sync_enabled=_as_bool(status_sync.get("enabled"), False),
            status_sync_source=str(status_sync.get("source", "")).strip(),
        )
    )
