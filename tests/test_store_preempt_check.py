from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import store_preempt_check as spc


def _seed_queue(root: Path, slug: str, *, full_name: str = "owner/demo") -> None:
    p = root / "registry" / "auto-migration" / "queue.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps({
            "schema_version": 1,
            "items": [{
                "id": f"github:{full_name}",
                "slug": slug,
                "source": full_name,
                "state": "ready",
                "candidate": {
                    "owner": full_name.split("/", 1)[0],
                    "repo": full_name.split("/", 1)[1],
                    "full_name": full_name,
                    "repo_url": f"https://github.com/{full_name}",
                    "description": "A demo self-hosted app",
                },
            }],
        }),
        encoding="utf-8",
    )


class StorePreemptCheckTest(unittest.TestCase):
    def test_returns_proceed_when_search_finds_no_hits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_queue(root, "demo")
            with (
                patch.object(spc, "search_lazycat", return_value={
                    "status": "portable",
                    "reason": "no hits",
                    "hits": [],
                    "searches": [],
                    "errors": [],
                }),
                patch.object(sys, "argv", ["x", "demo", "--repo-root", str(root)]),
            ):
                rc = spc.main()
            self.assertEqual(rc, 0)
            log = (root / "registry" / "auto-migration" / "ai-reviews.jsonl").read_text(encoding="utf-8")
            row = json.loads(log.splitlines()[0])
            self.assertEqual(row["reviewer"], "preempt")
            self.assertEqual(row["verdict"], "clear")
            self.assertEqual(row["extra"]["decision"], "proceed")

    def test_returns_abort_on_mechanical_strong_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_queue(root, "demo")
            with (
                patch.object(spc, "search_lazycat", return_value={
                    "status": "already_migrated",
                    "reason": "Strong app-store match found for repository name.",
                    "hits": [{"raw_label": "demo by foo", "detail_url": "https://lazycat.cloud/appstore/detail/x"}],
                    "searches": [],
                    "errors": [],
                }),
                patch.object(sys, "argv", ["x", "demo", "--repo-root", str(root), "--no-ai"]),
            ):
                rc = spc.main()
            self.assertEqual(rc, 3)
            log = (root / "registry" / "auto-migration" / "ai-reviews.jsonl").read_text(encoding="utf-8")
            row = json.loads(log.splitlines()[0])
            self.assertEqual(row["verdict"], "preempted")
            self.assertEqual(row["extra"]["decision"], "abort")

    def test_calls_claude_for_ambiguous_hits_and_aborts_when_yes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_queue(root, "demo")
            with (
                patch.object(spc, "search_lazycat", return_value={
                    "status": "needs_review",
                    "reason": "Possible matches",
                    "hits": [{"raw_label": "Other Demo", "detail_url": "https://lazycat.cloud/appstore/detail/y"}],
                    "searches": [],
                    "errors": [],
                }),
                patch.object(spc, "_claude_says_preempted", return_value=True),
                patch.object(sys, "argv", ["x", "demo", "--repo-root", str(root)]),
            ):
                rc = spc.main()
            self.assertEqual(rc, 3)

    def test_proceeds_when_claude_says_not_preempted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_queue(root, "demo")
            with (
                patch.object(spc, "search_lazycat", return_value={
                    "status": "needs_review",
                    "reason": "Possible matches",
                    "hits": [{"raw_label": "Other Demo", "detail_url": "https://lazycat.cloud/appstore/detail/y"}],
                    "searches": [],
                    "errors": [],
                }),
                patch.object(spc, "_claude_says_preempted", return_value=False),
                patch.object(sys, "argv", ["x", "demo", "--repo-root", str(root)]),
            ):
                rc = spc.main()
            self.assertEqual(rc, 0)

    def test_no_ai_flag_skips_claude_for_ambiguous_hits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_queue(root, "demo")
            with (
                patch.object(spc, "search_lazycat", return_value={
                    "status": "needs_review",
                    "reason": "Possible matches",
                    "hits": [{"raw_label": "Other Demo", "detail_url": "https://lazycat.cloud/appstore/detail/y"}],
                    "searches": [],
                    "errors": [],
                }),
                patch.object(spc, "_claude_says_preempted") as claude_mock,
                patch.object(sys, "argv", ["x", "demo", "--repo-root", str(root), "--no-ai"]),
            ):
                rc = spc.main()
            self.assertEqual(rc, 0)
            claude_mock.assert_not_called()

    def test_returns_1_when_slug_not_in_queue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_queue(root, "other")
            with patch.object(sys, "argv", ["x", "demo", "--repo-root", str(root)]):
                rc = spc.main()
            self.assertEqual(rc, 1)

    def test_returns_1_when_search_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_queue(root, "demo")
            with (
                patch.object(spc, "search_lazycat", side_effect=RuntimeError("boom")),
                patch.object(sys, "argv", ["x", "demo", "--repo-root", str(root)]),
            ):
                rc = spc.main()
            self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
