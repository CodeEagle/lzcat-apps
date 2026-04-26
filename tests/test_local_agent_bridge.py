from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.local_agent_bridge import build_local_agent_snapshot, write_local_agent_snapshot


class LocalAgentBridgeTest(unittest.TestCase):
    def make_local_agent_root(self) -> Path:
        root = Path(tempfile.mkdtemp(prefix="local-agent-bridge-test-"))
        (root / "data").mkdir(parents=True)
        return root

    def test_build_snapshot_normalizes_projects_and_external_sources(self) -> None:
        root = self.make_local_agent_root()
        (root / "data" / "state.json").write_text(
            json.dumps(
                {
                    "projects": {
                        "owner/demo": {
                            "full_name": "owner/demo",
                            "owner": "owner",
                            "repo": "demo",
                            "repo_url": "https://github.com/owner/demo",
                            "description": "A deployable demo app",
                            "language": "Python",
                            "stars_today": 9,
                            "total_stars": 100,
                            "status": "portable",
                            "status_reason": "No matching app found",
                            "sources": ["github_trending_daily"],
                            "source_labels": ["GitHub Trending Daily"],
                        }
                    }
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (root / "data" / "external_sources.json").write_text(
            json.dumps(
                {
                    "candidates": [
                        {
                            "full_name": "outside/tool",
                            "repo_url": "https://github.com/outside/tool",
                            "description": "Mentioned by a feed",
                            "external_signal": "Mentioned by notable X account",
                            "external_url": "https://x.com/example/status/1",
                        }
                    ]
                }
            )
            + "\n",
            encoding="utf-8",
        )

        snapshot = build_local_agent_snapshot(root, now="2026-04-26T09:30:00Z")

        candidates = snapshot["candidates"]
        self.assertEqual([candidate["full_name"] for candidate in candidates], ["owner/demo", "outside/tool"])
        self.assertEqual(candidates[0]["status"], "portable")
        self.assertEqual(candidates[0]["discovery_source"], "local_agent")
        self.assertEqual(candidates[0]["local_agent"]["origin"], "state.projects")
        self.assertEqual(candidates[1]["status"], "needs_review")
        self.assertEqual(candidates[1]["local_agent"]["origin"], "external_sources")
        self.assertEqual(snapshot["meta"]["source"], "local_agent")
        self.assertEqual(snapshot["meta"]["generated_at"], "2026-04-26T09:30:00Z")

    def test_write_snapshot_creates_parent_directory(self) -> None:
        root = self.make_local_agent_root()
        (root / "data" / "state.json").write_text(json.dumps({"projects": {}}) + "\n", encoding="utf-8")
        output_path = root / "out" / "local-agent-latest.json"

        snapshot = write_local_agent_snapshot(root, output_path, now="2026-04-26T09:30:00Z")

        self.assertTrue(output_path.exists())
        self.assertEqual(json.loads(output_path.read_text(encoding="utf-8")), snapshot)


if __name__ == "__main__":
    unittest.main()
