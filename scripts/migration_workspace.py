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
    create_new: bool = False,
) -> list[str]:
    """Build a `git worktree add` command for the slug's migration branch.

    create_new=True   →  `git worktree add -b migration/<slug> <path> <template_ref>`
                          (legacy local-dev mode; fails if the branch already exists).
    create_new=False  →  `git worktree add <path> migration/<slug>`
                          (CI mode: branch was forked from template ahead of time
                          by the workflow, just check it out into a worktree).
    """
    branch = migration_branch_name(slug)
    workspace = str(migration_workspace_path(workspace_root, slug))
    cmd = ["git", "-C", str(repo_root), "worktree", "add"]
    if create_new:
        cmd.extend(["-b", branch, workspace, template_ref])
    else:
        cmd.extend([workspace, branch])
    return cmd
