from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.migration_workspace import (
    build_worktree_command,
    migration_branch_name,
    migration_workspace_path,
)


class MigrationWorkspaceTest(unittest.TestCase):
    def test_migration_branch_name_uses_slug_namespace(self) -> None:
        self.assertEqual(migration_branch_name("PicLaw"), "migration/piclaw")
        self.assertEqual(migration_branch_name("hello_world"), "migration/hello-world")

    def test_workspace_path_is_isolated_per_slug(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="workspace-root-"))

        path = migration_workspace_path(root, "piclaw")

        self.assertEqual(path, root / "migration-piclaw")

    def test_build_worktree_command_creates_new_branch_when_requested(self) -> None:
        repo_root = Path("/repo/lzcat-apps")
        workspace_root = Path("/repo/workspaces")

        command = build_worktree_command(
            repo_root=repo_root,
            workspace_root=workspace_root,
            slug="piclaw",
            template_ref="template",
            create_new=True,
        )

        self.assertEqual(
            command,
            [
                "git",
                "-C",
                "/repo/lzcat-apps",
                "worktree",
                "add",
                "-b",
                "migration/piclaw",
                "/repo/workspaces/migration-piclaw",
                "template",
            ],
        )

    def test_build_worktree_command_uses_existing_branch_by_default(self) -> None:
        # CI flow: the migration branch is forked from template by an
        # earlier workflow step, so the worktree command should just check
        # it out — `git worktree add <path> migration/<slug>`.
        command = build_worktree_command(
            repo_root=Path("/repo/lzcat-apps"),
            workspace_root=Path("/repo/workspaces"),
            slug="piclaw",
            template_ref="template",
        )

        self.assertEqual(
            command,
            [
                "git",
                "-C",
                "/repo/lzcat-apps",
                "worktree",
                "add",
                "/repo/workspaces/migration-piclaw",
                "migration/piclaw",
            ],
        )


if __name__ == "__main__":
    unittest.main()
