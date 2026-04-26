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

    def test_build_worktree_command_starts_from_template_branch(self) -> None:
        repo_root = Path("/repo/lzcat-apps")
        workspace_root = Path("/repo/workspaces")

        command = build_worktree_command(
            repo_root=repo_root,
            workspace_root=workspace_root,
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
                "-b",
                "migration/piclaw",
                "/repo/workspaces/migration-piclaw",
                "template",
            ],
        )


if __name__ == "__main__":
    unittest.main()
