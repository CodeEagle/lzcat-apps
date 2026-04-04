from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.collect_targets import should_auto_skip_docker


class CollectTargetsAutoSkipDockerTest(unittest.TestCase):
    def test_auto_skip_enabled_for_icon_only_change(self) -> None:
        repo_root = Path(tempfile.mkdtemp(prefix="lzcat-collect-targets-test-"))
        with patch(
            "scripts.collect_targets.read_changed_files_since_previous_commit",
            return_value=["apps/paperclip/icon.png"],
        ):
            result = should_auto_skip_docker(
                event_name="workflow_dispatch",
                target_repo="paperclip",
                target_version="",
                explicit_skip_docker=False,
                repo_root=repo_root,
            )
        self.assertTrue(result)

    def test_auto_skip_disabled_for_mixed_changes(self) -> None:
        repo_root = Path(tempfile.mkdtemp(prefix="lzcat-collect-targets-test-"))
        with patch(
            "scripts.collect_targets.read_changed_files_since_previous_commit",
            return_value=[
                "apps/paperclip/icon.png",
                "apps/paperclip/Dockerfile",
            ],
        ):
            result = should_auto_skip_docker(
                event_name="workflow_dispatch",
                target_repo="paperclip",
                target_version="",
                explicit_skip_docker=False,
                repo_root=repo_root,
            )
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
