from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.claude_verify_reviewer import (
    build_prompt,
    extract_json,
    normalize_verdict,
    write_review,
)


class _FakeProc:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _make_repo(slug: str, *, with_artifacts: bool = True) -> Path:
    root = Path(tempfile.mkdtemp(prefix="claude-verify-test-"))
    app = root / "apps" / slug
    app.mkdir(parents=True)
    if with_artifacts:
        (app / "lzc-manifest.yml").write_text(
            "package: cloud.lazycat.app.demo\napplication:\n  subdomain: demo\n",
            encoding="utf-8",
        )
        (app / ".functional-check.json").write_text(
            json.dumps(
                {
                    "slug": slug,
                    "browser_acceptance_status": "browser_pass",
                    "entry_url": "https://demo.rx79.heiyu.space",
                }
            ),
            encoding="utf-8",
        )
        (app / ".browser-acceptance-plan.json").write_text(
            json.dumps({"slug": slug, "entry_url": "https://demo.rx79.heiyu.space"}),
            encoding="utf-8",
        )
        (app / "acceptance").mkdir()
        (app / "acceptance" / "web-screenshots.json").write_text(
            json.dumps({"screenshots": [{"path": f"apps/{slug}/acceptance/{slug}-home.png"}]}),
            encoding="utf-8",
        )
    return root


class BuildPromptTest(unittest.TestCase):
    def test_returns_none_when_artifacts_missing(self) -> None:
        root = _make_repo("demo", with_artifacts=False)
        prompt, snapshot = build_prompt(root, "demo")
        self.assertIsNone(prompt)
        self.assertIsNone(snapshot)

    def test_returns_prompt_when_artifacts_present(self) -> None:
        root = _make_repo("demo")
        prompt, snapshot = build_prompt(root, "demo")
        self.assertIsNotNone(prompt)
        self.assertIn("verdict", prompt)
        self.assertIn("blocking_issues", prompt)
        self.assertIn("demo", snapshot["slug"])
        self.assertEqual(snapshot["functional_check"]["browser_acceptance_status"], "browser_pass")


class ExtractJsonTest(unittest.TestCase):
    def test_pure_json_response(self) -> None:
        out = extract_json('{"verdict": "pass", "score": 0.9}')
        self.assertEqual(out["verdict"], "pass")

    def test_json_wrapped_in_text(self) -> None:
        out = extract_json("Here is my verdict: {\"verdict\": \"fail\"} thanks.")
        self.assertEqual(out["verdict"], "fail")

    def test_invalid_returns_none(self) -> None:
        self.assertIsNone(extract_json("no json here"))
        self.assertIsNone(extract_json("{not even close"))


class NormalizeVerdictTest(unittest.TestCase):
    def test_clamps_score_and_defaults_next_action(self) -> None:
        out = normalize_verdict({"verdict": "pass", "score": 1.5, "reasoning": "good"})
        self.assertEqual(out["verdict"], "pass")
        self.assertEqual(out["score"], 1.0)
        self.assertEqual(out["next_action"], "publish")

    def test_rejects_unknown_verdict_default_needs_human(self) -> None:
        out = normalize_verdict({"verdict": "approved", "score": 0.7})
        self.assertEqual(out["verdict"], "needs_human")
        self.assertEqual(out["next_action"], "human_review")

    def test_handles_string_score(self) -> None:
        out = normalize_verdict({"verdict": "fail", "score": "nope"})
        self.assertEqual(out["score"], 0.0)
        self.assertEqual(out["next_action"], "rebuild")

    def test_blocking_issues_coerced_to_list(self) -> None:
        out = normalize_verdict({"verdict": "fail", "blocking_issues": "single string"})
        self.assertEqual(out["blocking_issues"], ["single string"])

    def test_blocking_issues_filters_empty(self) -> None:
        out = normalize_verdict({"verdict": "fail", "blocking_issues": ["", "  ", "real"]})
        self.assertEqual(out["blocking_issues"], ["real"])


class WriteReviewTest(unittest.TestCase):
    def test_write_review_creates_json_file(self) -> None:
        root = _make_repo("demo")
        out_path = write_review(
            root,
            "demo",
            normalize_verdict({"verdict": "pass", "score": 0.92, "reasoning": "ok"}),
            model="claude-sonnet-4-6",
        )
        self.assertTrue(out_path.exists())
        payload = json.loads(out_path.read_text())
        self.assertEqual(payload["verdict"], "pass")
        self.assertEqual(payload["model"], "claude-sonnet-4-6")
        self.assertEqual(payload["slug"], "demo")
        self.assertEqual(payload["schema_version"], 1)


class MainEndToEndTest(unittest.TestCase):
    def test_main_via_argv_writes_file(self) -> None:
        from scripts import claude_verify_reviewer as crv

        root = _make_repo("demo")
        claude_response = json.dumps(
            {
                "verdict": "pass",
                "score": 0.91,
                "reasoning": "ok",
                "blocking_issues": [],
                "next_action": "publish",
            }
        )

        with (
            patch.object(crv.subprocess, "run", return_value=_FakeProc(0, stdout=claude_response)),
            patch.object(sys, "argv", ["claude_verify_reviewer.py", "demo", "--repo-root", str(root)]),
        ):
            rc = crv.main()
        self.assertEqual(rc, 0)
        review_path = root / "apps" / "demo" / ".claude-verify-review.json"
        self.assertTrue(review_path.exists())
        payload = json.loads(review_path.read_text())
        self.assertEqual(payload["verdict"], "pass")

    def test_main_returns_2_on_invalid_json(self) -> None:
        from scripts import claude_verify_reviewer as crv

        root = _make_repo("demo")
        with (
            patch.object(crv.subprocess, "run", return_value=_FakeProc(0, stdout="not json")),
            patch.object(sys, "argv", ["claude_verify_reviewer.py", "demo", "--repo-root", str(root)]),
        ):
            rc = crv.main()
        self.assertEqual(rc, 2)

    def test_main_returns_1_when_no_artifacts(self) -> None:
        from scripts import claude_verify_reviewer as crv

        root = _make_repo("demo", with_artifacts=False)
        with patch.object(sys, "argv", ["claude_verify_reviewer.py", "demo", "--repo-root", str(root)]):
            rc = crv.main()
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
