from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.ai_review_log import append_review, iter_reviews


class AIReviewLogTest(unittest.TestCase):
    def test_append_creates_file_and_writes_one_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = append_review(
                root,
                reviewer="discovery",
                slug="demo",
                item_id="github:owner/demo",
                model="claude-sonnet-4-6",
                verdict="migrate",
                score=0.91,
                reason="real self-hosted web app",
                evidence=["has docker-compose", "active maintainers"],
                task_dir="registry/auto-migration/discovery-review-tasks/x",
                returncode=0,
                ts="2026-05-07T01:00:00Z",
            )
            self.assertEqual(path, root / "registry" / "auto-migration" / "ai-reviews.jsonl")
            self.assertTrue(path.exists())
            lines = path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)
            row = json.loads(lines[0])
            self.assertEqual(row["reviewer"], "discovery")
            self.assertEqual(row["slug"], "demo")
            self.assertEqual(row["verdict"], "migrate")
            self.assertEqual(row["score"], 0.91)
            self.assertEqual(row["evidence"], ["has docker-compose", "active maintainers"])

    def test_append_multiple_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for i in range(3):
                append_review(
                    root,
                    reviewer="discovery" if i % 2 == 0 else "verify",
                    slug=f"demo-{i}",
                    verdict="migrate",
                    score=0.5 + 0.1 * i,
                    ts=f"2026-05-07T01:00:0{i}Z",
                )
            log = root / "registry" / "auto-migration" / "ai-reviews.jsonl"
            rows = iter_reviews(log)
            self.assertEqual(len(rows), 3)
            self.assertEqual([r["slug"] for r in rows], ["demo-0", "demo-1", "demo-2"])
            self.assertEqual([r["reviewer"] for r in rows], ["discovery", "verify", "discovery"])

    def test_iter_skips_malformed_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            log.write_text(
                "{\"slug\": \"good\", \"verdict\": \"migrate\"}\n"
                "not-json\n"
                "\n"
                "{\"slug\": \"good2\", \"verdict\": \"skip\"}\n",
                encoding="utf-8",
            )
            rows = iter_reviews(log)
            self.assertEqual([r["slug"] for r in rows], ["good", "good2"])

    def test_score_none_serialised_explicitly(self) -> None:
        # Early-cycle reviews may not yet have a numeric score; the audit
        # row should still be parseable rather than embedding the literal
        # word "None".
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = append_review(
                root,
                reviewer="discovery",
                slug="demo",
                model="claude-sonnet-4-6",
                verdict="needs_human",
                score=None,
                ts="2026-05-07T01:00:00Z",
            )
            row = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
            self.assertIsNone(row["score"])
            self.assertEqual(row["verdict"], "needs_human")

    def test_iter_returns_empty_when_file_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(iter_reviews(Path(tmp) / "missing.jsonl"), [])


if __name__ == "__main__":
    unittest.main()
