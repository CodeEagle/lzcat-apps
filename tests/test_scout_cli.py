from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.scout import build_payload, write_candidate_files


class ScoutCliTest(unittest.TestCase):
    def test_write_candidate_files_updates_latest_and_dated_snapshot(self) -> None:
        repo_root = Path(tempfile.mkdtemp(prefix="scout-cli-test-"))
        payload = {
            "meta": {"generated_at": "2026-04-25T00:00:00Z", "candidate_count": 1},
            "candidates": [{"full_name": "owner/demo", "status": "portable"}],
        }

        paths = write_candidate_files(repo_root, payload)

        self.assertEqual(paths["latest"], repo_root / "registry" / "candidates" / "latest.json")
        self.assertEqual(paths["dated"], repo_root / "registry" / "candidates" / "2026-04-25.json")
        self.assertEqual(json.loads(paths["latest"].read_text(encoding="utf-8")), payload)
        self.assertEqual(json.loads(paths["dated"].read_text(encoding="utf-8")), payload)

    def test_build_payload_reports_counts(self) -> None:
        candidates = [
            {"full_name": "owner/demo", "status": "portable"},
            {"full_name": "owner/sdk", "status": "excluded"},
        ]

        payload = build_payload(candidates, generated_at="2026-04-25T00:00:00Z")

        self.assertEqual(payload["meta"]["candidate_count"], 2)
        self.assertEqual(payload["meta"]["portable_count"], 1)
        self.assertEqual(payload["meta"]["excluded_count"], 1)


if __name__ == "__main__":
    unittest.main()
