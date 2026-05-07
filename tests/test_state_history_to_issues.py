"""Tests for ``scripts.state_history_to_issues``."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import state_history_to_issues as mod


def _item(slug: str = "demo", **extra: Any) -> dict[str, Any]:
    base = {
        "id": f"github:owner/{slug}",
        "slug": slug,
        "candidate": {
            "repo_url": f"https://github.com/owner/{slug}",
            "description": "demo desc",
        },
        "state_history": [
            {"from": "discovery_review", "to": "ready",
             "reason": "AI verdict=migrate score=0.85",
             "source": "project_board.cmd_sync",
             "ts": "2026-05-07T08:00:00Z",
             "run_id": "12345"},
        ],
    }
    base.update(extra)
    return base


def test_issue_title_format() -> None:
    assert mod.issue_title("demo") == "[migration] demo"


def test_issue_body_includes_slug_upstream_description() -> None:
    body = mod.issue_body(_item("demo"))
    assert "demo" in body
    assert "https://github.com/owner/demo" in body
    assert "demo desc" in body


def test_comment_body_renders_state_change() -> None:
    item = _item()
    body = mod.comment_body(item["state_history"][0], item)
    assert "discovery_review" in body
    assert "ready" in body
    assert "AI verdict=migrate" in body
    assert "project_board.cmd_sync" in body
    assert "2026-05-07T08:00:00Z" in body
    # run_id rendered as link
    assert "run #12345" in body


def test_process_item_skips_when_no_history(tmp_path: Path) -> None:
    item = {"slug": "x"}
    out = mod.process_item("CodeEagle/lzcat-apps", item, dry_run=True)
    assert out == {"slug": "x", "skipped": "no history"}


def test_process_item_skips_when_all_already_posted() -> None:
    item = _item()
    item["state_history_posted_count"] = 1  # equals len(history)
    out = mod.process_item("CodeEagle/lzcat-apps", item, dry_run=True)
    assert out == {"slug": "demo", "skipped": "no new entries"}


def test_process_item_dry_run_with_existing_issue() -> None:
    item = _item()
    item["github_issue_number"] = 42
    out = mod.process_item("CodeEagle/lzcat-apps", item, dry_run=True)
    assert out["slug"] == "demo"
    assert out["would_post_to"] == 42
    assert out["count"] == 1


def test_process_item_creates_issue_and_posts_comments() -> None:
    item = _item()
    # 3 history entries; expect 3 comments
    item["state_history"] = item["state_history"] + [
        {"from": "ready", "to": "scaffolded", "reason": "scaffold rc=0",
         "source": "auto_migrate.scaffold", "ts": "2026-05-07T09:00:00Z"},
        {"from": "scaffolded", "to": "build_failed", "reason": "build rc=1",
         "source": "auto_migrate.build", "ts": "2026-05-07T09:30:00Z"},
    ]
    calls: list[list[str]] = []

    def fake_gh(args, *, input=None):  # noqa: ANN001
        calls.append(args)
        if args[0:2] == ["issue", "list"]:
            return 0, "[]", ""  # not found by search
        if args[0:2] == ["issue", "create"]:
            return 0, "https://github.com/CodeEagle/lzcat-apps/issues/77\n", ""
        if args[0:2] == ["issue", "comment"]:
            return 0, "", ""
        return 0, "", ""

    with patch.object(mod, "_gh", side_effect=fake_gh):
        result = mod.process_item("CodeEagle/lzcat-apps", item, dry_run=False)

    assert result["issue"] == 77
    assert result["posted"] == 3
    assert item["github_issue_number"] == 77
    assert item["state_history_posted_count"] == 3

    # 1 list + 1 create + 3 comment = 5 calls
    assert len(calls) == 5
    assert calls[0][0:2] == ["issue", "list"]
    assert calls[1][0:2] == ["issue", "create"]
    assert calls[2][0:2] == ["issue", "comment"]
    assert calls[3][0:2] == ["issue", "comment"]
    assert calls[4][0:2] == ["issue", "comment"]


def test_process_item_reuses_existing_issue_via_search() -> None:
    item = _item()
    # Item has no github_issue_number — script should find it via search.
    def fake_gh(args, *, input=None):  # noqa: ANN001
        if args[0:2] == ["issue", "list"]:
            payload = [{"number": 99, "title": "[migration] demo"}]
            return 0, json.dumps(payload), ""
        if args[0:2] == ["issue", "comment"]:
            return 0, "", ""
        return 0, "", ""

    with patch.object(mod, "_gh", side_effect=fake_gh):
        result = mod.process_item("CodeEagle/lzcat-apps", item, dry_run=False)

    assert result["issue"] == 99
    assert result["posted"] == 1
    assert item["github_issue_number"] == 99


def test_process_item_only_posts_new_entries() -> None:
    item = _item()
    item["state_history"] = item["state_history"] + [
        {"from": "ready", "to": "scaffolded", "reason": "...",
         "source": "x", "ts": "t2"},
    ]
    item["github_issue_number"] = 11
    item["state_history_posted_count"] = 1  # 1st already posted

    posts: list[str] = []

    def fake_gh(args, *, input=None):  # noqa: ANN001
        if args[0:2] == ["issue", "comment"]:
            posts.append(input or "")
            return 0, "", ""
        return 0, "", ""

    with patch.object(mod, "_gh", side_effect=fake_gh):
        result = mod.process_item("CodeEagle/lzcat-apps", item, dry_run=False)

    assert result["posted"] == 1  # only 1 new
    assert item["state_history_posted_count"] == 2
    # The body should be the SECOND entry's content
    assert "scaffolded" in posts[0]
    assert "discovery_review" not in posts[0]


def test_main_atomic_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify queue.json is updated with new bookkeeping fields after run."""
    queue_path = tmp_path / "registry" / "auto-migration" / "queue.json"
    queue_path.parent.mkdir(parents=True)
    queue = {"items": [_item("demo")]}
    queue_path.write_text(json.dumps(queue), encoding="utf-8")

    def fake_gh(args, *, input=None):  # noqa: ANN001
        if args[0:2] == ["issue", "list"]:
            return 0, "[]", ""
        if args[0:2] == ["issue", "create"]:
            return 0, "https://github.com/CodeEagle/lzcat-apps/issues/100\n", ""
        if args[0:2] == ["issue", "comment"]:
            return 0, "", ""
        if args[0:2] == ["label", "create"]:
            return 0, "", ""
        return 0, "", ""

    monkeypatch.setattr(sys, "argv", [
        "state_history_to_issues",
        "--repo-root", str(tmp_path),
        "--repo", "CodeEagle/lzcat-apps",
        "--queue-path", "registry/auto-migration/queue.json",
    ])
    with patch.object(mod, "_gh", side_effect=fake_gh):
        rc = mod.main()
    assert rc == 0
    after = json.loads(queue_path.read_text(encoding="utf-8"))
    saved = after["items"][0]
    assert saved["github_issue_number"] == 100
    assert saved["state_history_posted_count"] == 1
