#!/usr/bin/env python3

from __future__ import annotations

import re
from pathlib import Path


def normalize_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    return re.sub(r"-{2,}", "-", slug).strip("-") or "unknown"


def migration_branch_name(slug: str) -> str:
    return f"migration/{normalize_slug(slug)}"


def migration_workspace_path(workspace_root: Path, slug: str) -> Path:
    return workspace_root / f"migration-{normalize_slug(slug)}"


def build_worktree_command(
    *,
    repo_root: Path,
    workspace_root: Path,
    slug: str,
    template_ref: str = "template",
) -> list[str]:
    return [
        "git",
        "-C",
        str(repo_root),
        "worktree",
        "add",
        "-b",
        migration_branch_name(slug),
        str(migration_workspace_path(workspace_root, slug)),
        template_ref,
    ]
