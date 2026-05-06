from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from scripts import run_build


class RunBuildGitTargetBranchTest(unittest.TestCase):
    def test_prefers_pull_request_head_branch(self) -> None:
        branch = run_build.resolve_git_target_branch(
            {
                "GITHUB_HEAD_REF": "codex/from-pr",
                "GITHUB_REF_NAME": "123/merge",
            },
            Path("/repo"),
        )

        self.assertEqual(branch, "codex/from-pr")

    def test_uses_workflow_ref_name_for_branch_dispatch(self) -> None:
        branch = run_build.resolve_git_target_branch(
            {"GITHUB_REF_NAME": "codex/codex-web-lazycat"},
            Path("/repo"),
        )

        self.assertEqual(branch, "codex/codex-web-lazycat")

    def test_parses_full_github_branch_ref(self) -> None:
        branch = run_build.resolve_git_target_branch(
            {"GITHUB_REF": "refs/heads/codex/codex-web-lazycat"},
            Path("/repo"),
        )

        self.assertEqual(branch, "codex/codex-web-lazycat")

    def test_falls_back_to_current_checkout_branch(self) -> None:
        with mock.patch.object(run_build, "sh", return_value="codex/local-branch") as sh_mock:
            branch = run_build.resolve_git_target_branch({}, Path("/repo"))

        self.assertEqual(branch, "codex/local-branch")
        sh_mock.assert_called_once_with(
            ["git", "branch", "--show-current"],
            cwd=Path("/repo"),
            env={},
            check=False,
        )


if __name__ == "__main__":
    unittest.main()
