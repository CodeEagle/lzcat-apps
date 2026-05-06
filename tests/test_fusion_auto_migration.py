from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.fusion_auto_migration import (
    FusionAutoMigrationConfig,
    build_launchd_plist,
    build_service_command,
    default_workspace_root,
)


class FusionAutoMigrationTest(unittest.TestCase):
    def test_build_service_command_enables_7x24_fusion_pipeline(self) -> None:
        repo_root = Path(tempfile.mkdtemp(prefix="fusion-auto-migration-test-"))
        command = build_service_command(
            FusionAutoMigrationConfig(
                repo_root=repo_root,
                box_domain="rx79.heiyu.space",
                interval_seconds=600,
                disable_local_agent=True,
            )
        )

        self.assertIn("--daemon", command)
        self.assertIn("--enable-build-install", command)
        self.assertIn("--functional-check", command)
        self.assertIn("--enable-codex-worker", command)
        self.assertIn("--resume", command)
        self.assertEqual(command[command.index("--box-domain") + 1], "rx79.heiyu.space")
        self.assertEqual(command[command.index("--workspace-root") + 1], str(default_workspace_root(repo_root)))
        self.assertIn("--disable-local-agent", command)

    def test_build_service_command_can_render_once_dry_run(self) -> None:
        repo_root = Path(tempfile.mkdtemp(prefix="fusion-auto-migration-test-"))
        command = build_service_command(FusionAutoMigrationConfig(repo_root=repo_root, once=True, dry_run=True))

        self.assertIn("--once", command)
        self.assertNotIn("--daemon", command)
        self.assertIn("--dry-run", command)

    def test_build_launchd_plist_keeps_daemon_alive(self) -> None:
        repo_root = Path(tempfile.mkdtemp(prefix="fusion-auto-migration-test-"))
        command = build_service_command(FusionAutoMigrationConfig(repo_root=repo_root))
        plist = build_launchd_plist(
            label="cloud.lazycat.auto-migration",
            repo_root=repo_root,
            command=command,
            stdout_path=repo_root / "registry" / "auto-migration" / "logs" / "launchd.out.log",
            stderr_path=repo_root / "registry" / "auto-migration" / "logs" / "launchd.err.log",
        )

        self.assertTrue(plist["RunAtLoad"])
        self.assertTrue(plist["KeepAlive"])
        self.assertEqual(plist["ProgramArguments"], command)
        self.assertEqual(plist["WorkingDirectory"], str(repo_root))


if __name__ == "__main__":
    unittest.main()
