from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.sync_trigger_build_options import sync_workflow


class SyncTriggerBuildOptionsTest(unittest.TestCase):
    def test_sync_workflow_replaces_choice_options_from_index(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="lzcat-trigger-choice-test-"))
        index_path = temp_dir / "index.json"
        workflow_path = temp_dir / "trigger-build.yml"

        index_path.write_text(
            '{\n  "repos": ["beta.json", "alpha.json"]\n}\n',
            encoding="utf-8",
        )
        workflow_path.write_text(
            "\n".join(
                [
                    "name: Trigger Build",
                    "on:",
                    "  workflow_dispatch:",
                    "    inputs:",
                    "      target_repo:",
                    "        type: choice",
                    "        options:",
                    "          # BEGIN AUTO-GENERATED APP OPTIONS",
                    '          - "all-enabled-apps"',
                    '          - "old-app"',
                    "          # END AUTO-GENERATED APP OPTIONS",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        changed = sync_workflow(index_path=index_path, workflow_path=workflow_path)

        self.assertTrue(changed)
        updated = workflow_path.read_text(encoding="utf-8")
        self.assertIn('"all-enabled-apps"', updated)
        self.assertIn('"alpha"', updated)
        self.assertIn('"beta"', updated)
        self.assertNotIn('"old-app"', updated)


if __name__ == "__main__":
    unittest.main()
