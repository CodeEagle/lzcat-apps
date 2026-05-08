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


# ---------------------------------------------------------------------------
# Tests for the extended artifact mirror (discovery_review, codex,
# last_error, ai-reviews.jsonl).
# ---------------------------------------------------------------------------


def test_discovery_review_comment_body_renders_verdict_and_evidence() -> None:
    body = mod.discovery_review_comment_body({
        "status": "migrate",
        "reviewer": "claude",
        "score": 0.85,
        "reviewed_at": "2026-05-07T10:00:00Z",
        "reason": "self-hosted Rust runtime",
        "evidence": ["agent_host/", "Cargo.toml + run.sh"],
        "prompt": "Re-evaluate this candidate ...",
    })
    assert "migrate" in body
    assert "0.85" in body
    assert "claude" in body
    assert "2026-05-07T10:00:00Z" in body
    assert "self-hosted Rust runtime" in body
    assert "agent_host/" in body
    assert "Re-evaluate this candidate" in body


def test_codex_run_comment_body_renders_status_rc_taskdir() -> None:
    item = {"slug": "demo", "last_error": "build broke: missing Dockerfile"}
    body = mod.codex_run_comment_body({
        "attempts": 2,
        "last_returncode": 1,
        "last_run_at": "2026-05-06T17:42:53Z",
        "last_status": "codex_failed",
        "last_task_dir": "/tmp/codex-tasks/abc",
        "session_id": "sess-1",
    }, item)
    assert "codex_failed" in body
    assert "rc=`1`" in body
    assert "attempt `2`" in body
    assert "2026-05-06T17:42:53Z" in body
    assert "/tmp/codex-tasks/abc" in body
    assert "sess-1" in body
    assert "build broke" in body  # last_error inlined when rc != 0


def test_last_error_comment_body_fences_error() -> None:
    body = mod.last_error_comment_body({
        "state": "build_failed",
        "updated_at": "2026-05-07T11:00:00Z",
        "last_error": "RuntimeError: docker push timed out",
    })
    assert "build_failed" in body
    assert "2026-05-07T11:00:00Z" in body
    assert "```" in body
    assert "docker push timed out" in body


def test_ai_review_comment_body_renders_all_fields() -> None:
    body = mod.ai_review_comment_body({
        "reviewer": "discovery",
        "verdict": "skip",
        "score": 0.04,
        "ts": "2026-05-07T05:51:36Z",
        "model": "claude-sonnet-4-6",
        "reason": "static GitHub Pages site",
        "evidence": ["no Docker", "static frontend only"],
        "task_dir": "/tmp/disc/abc",
        "returncode": 0,
    })
    assert "discovery" in body
    assert "skip" in body
    assert "0.04" in body
    assert "claude-sonnet-4-6" in body
    assert "2026-05-07T05:51:36Z" in body
    assert "static GitHub Pages site" in body
    assert "no Docker" in body
    assert "/tmp/disc/abc" in body


def test_load_ai_reviews_by_slug_groups_and_sorts(tmp_path: Path) -> None:
    p = tmp_path / "ai-reviews.jsonl"
    p.write_text(
        json.dumps({"slug": "a", "ts": "2026-05-07T02:00:00Z", "reviewer": "discovery"}) + "\n"
        + json.dumps({"slug": "a", "ts": "2026-05-07T01:00:00Z", "reviewer": "discovery"}) + "\n"
        + json.dumps({"slug": "b", "ts": "2026-05-06T00:00:00Z", "reviewer": "verify"}) + "\n"
        + "\n"  # blank line tolerated
        + "not-json\n"  # bad line tolerated
        + json.dumps({"ts": "x", "reviewer": "discovery"}) + "\n",  # missing slug skipped
        encoding="utf-8",
    )
    idx = mod.load_ai_reviews_by_slug(p)
    assert set(idx.keys()) == {"a", "b"}
    assert [e["ts"] for e in idx["a"]] == [
        "2026-05-07T01:00:00Z", "2026-05-07T02:00:00Z",
    ]


def test_load_ai_reviews_by_slug_missing_file_returns_empty(tmp_path: Path) -> None:
    assert mod.load_ai_reviews_by_slug(tmp_path / "does-not-exist.jsonl") == {}


def test_process_item_posts_discovery_review_once_and_marks_posted() -> None:
    item = {
        "slug": "demo",
        "id": "github:owner/demo",
        "candidate": {"repo_url": "https://github.com/owner/demo"},
        "discovery_review": {
            "status": "migrate",
            "score": 0.9,
            "reviewer": "claude",
            "reviewed_at": "2026-05-07T10:00:00Z",
            "reason": "deployable runtime",
            "evidence": ["Cargo.toml", "run.sh"],
        },
        "github_issue_number": 5,
    }
    posts: list[str] = []

    def fake_gh(args, *, input=None):  # noqa: ANN001
        if args[0:2] == ["issue", "comment"]:
            posts.append(input or "")
            return 0, "", ""
        return 0, "", ""

    with patch.object(mod, "_gh", side_effect=fake_gh):
        result = mod.process_item("CodeEagle/lzcat-apps", item, dry_run=False)
    assert result["posted"] == 1
    assert result["kinds"] == {"discovery_review": 1}
    assert item["discovery_review_posted_at"] == "2026-05-07T10:00:00Z"
    assert "Discovery Review" in posts[0]
    assert "deployable runtime" in posts[0]

    # Re-running posts nothing — idempotent.
    posts.clear()
    with patch.object(mod, "_gh", side_effect=fake_gh):
        again = mod.process_item("CodeEagle/lzcat-apps", item, dry_run=False)
    assert again == {"slug": "demo", "skipped": "no new entries"}
    assert posts == []


def test_process_item_posts_codex_run_once() -> None:
    item = {
        "slug": "demo",
        "candidate": {"repo_url": "https://github.com/owner/demo"},
        "codex": {
            "attempts": 1,
            "last_returncode": 1,
            "last_run_at": "2026-05-06T17:42:53Z",
            "last_status": "codex_failed",
            "last_task_dir": "/tmp/codex-tasks/abc",
        },
        "github_issue_number": 7,
    }
    posts: list[str] = []

    def fake_gh(args, *, input=None):  # noqa: ANN001
        if args[0:2] == ["issue", "comment"]:
            posts.append(input or "")
            return 0, "", ""
        return 0, "", ""

    with patch.object(mod, "_gh", side_effect=fake_gh):
        result = mod.process_item("CodeEagle/lzcat-apps", item, dry_run=False)
    assert result["posted"] == 1
    assert result["kinds"] == {"codex_run": 1}
    assert item["codex_run_posted_at"] == "2026-05-06T17:42:53Z"
    assert "Codex Run" in posts[0]
    assert "codex_failed" in posts[0]


def test_process_item_posts_last_error_only_when_changed() -> None:
    item = {
        "slug": "demo",
        "candidate": {"repo_url": "https://github.com/owner/demo"},
        "state": "build_failed",
        "updated_at": "2026-05-07T11:00:00Z",
        "last_error": "boom v1",
        "github_issue_number": 9,
    }
    posts: list[str] = []

    def fake_gh(args, *, input=None):  # noqa: ANN001
        if args[0:2] == ["issue", "comment"]:
            posts.append(input or "")
            return 0, "", ""
        return 0, "", ""

    with patch.object(mod, "_gh", side_effect=fake_gh):
        first = mod.process_item("CodeEagle/lzcat-apps", item, dry_run=False)
    assert first["posted"] == 1
    assert "last_error_posted_hash" in item
    assert "boom v1" in posts[0]

    # Same error — no new comment.
    posts.clear()
    with patch.object(mod, "_gh", side_effect=fake_gh):
        again = mod.process_item("CodeEagle/lzcat-apps", item, dry_run=False)
    assert again == {"slug": "demo", "skipped": "no new entries"}
    assert posts == []

    # Error changes — posts again, marker rotates.
    item["last_error"] = "boom v2 (new failure)"
    item["updated_at"] = "2026-05-07T12:00:00Z"
    with patch.object(mod, "_gh", side_effect=fake_gh):
        third = mod.process_item("CodeEagle/lzcat-apps", item, dry_run=False)
    assert third["posted"] == 1
    assert any("boom v2" in p for p in posts)


def test_process_item_posts_ai_reviews_with_count_marker() -> None:
    reviews = [
        {"reviewer": "discovery", "verdict": "skip", "score": 0.1,
         "ts": "2026-05-06T01:00:00Z", "reason": "framework only", "evidence": []},
        {"reviewer": "discovery", "verdict": "migrate", "score": 0.85,
         "ts": "2026-05-07T02:00:00Z", "reason": "deployable runtime", "evidence": ["run.sh"]},
    ]
    item = {
        "slug": "demo",
        "candidate": {"repo_url": "https://github.com/owner/demo"},
        "github_issue_number": 11,
    }
    posts: list[str] = []

    def fake_gh(args, *, input=None):  # noqa: ANN001
        if args[0:2] == ["issue", "comment"]:
            posts.append(input or "")
            return 0, "", ""
        return 0, "", ""

    with patch.object(mod, "_gh", side_effect=fake_gh):
        result = mod.process_item(
            "CodeEagle/lzcat-apps", item, dry_run=False,
            ai_reviews_for_slug=reviews,
        )
    assert result["posted"] == 2
    assert result["kinds"] == {"ai_review": 2}
    assert item["ai_reviews_posted_count"] == 2
    # Earlier review posted first (chronological).
    assert "framework only" in posts[0]
    assert "deployable runtime" in posts[1]

    # Re-run posts nothing.
    posts.clear()
    with patch.object(mod, "_gh", side_effect=fake_gh):
        again = mod.process_item(
            "CodeEagle/lzcat-apps", item, dry_run=False,
            ai_reviews_for_slug=reviews,
        )
    assert again == {"slug": "demo", "skipped": "no new entries"}


def test_process_item_mixes_kinds_in_chronological_order() -> None:
    item = {
        "slug": "demo",
        "candidate": {"repo_url": "https://github.com/owner/demo"},
        "github_issue_number": 13,
        "state_history": [
            {"from": "ready", "to": "scaffolded", "reason": "scaffolded",
             "source": "auto_migrate.scaffold", "ts": "2026-05-07T03:00:00Z"},
        ],
        "discovery_review": {
            "status": "migrate", "score": 0.85, "reviewer": "claude",
            "reviewed_at": "2026-05-07T01:00:00Z",
            "reason": "deployable", "evidence": [],
        },
        "codex": {
            "attempts": 1, "last_returncode": 0, "last_run_at": "2026-05-07T02:00:00Z",
            "last_status": "ready", "last_task_dir": "/tmp/x",
        },
    }
    reviews = [
        {"reviewer": "discovery", "verdict": "migrate", "score": 0.85,
         "ts": "2026-05-07T00:30:00Z", "reason": "evidence ok", "evidence": []},
    ]
    posts: list[str] = []

    def fake_gh(args, *, input=None):  # noqa: ANN001
        if args[0:2] == ["issue", "comment"]:
            posts.append(input or "")
            return 0, "", ""
        return 0, "", ""

    with patch.object(mod, "_gh", side_effect=fake_gh):
        result = mod.process_item(
            "CodeEagle/lzcat-apps", item, dry_run=False,
            ai_reviews_for_slug=reviews,
        )
    assert result["posted"] == 4
    assert result["kinds"] == {
        "ai_review": 1,
        "discovery_review": 1,
        "codex_run": 1,
        "state_history": 1,
    }
    # Chronological: ai_review (00:30) → discovery_review (01:00) →
    # codex_run (02:00) → state_history (03:00).
    assert "AI Review" in posts[0]
    assert "Discovery Review" in posts[1]
    assert "Codex Run" in posts[2]
    assert "scaffolded" in posts[3]
    # All markers persisted.
    assert item["state_history_posted_count"] == 1
    assert item["discovery_review_posted_at"] == "2026-05-07T01:00:00Z"
    assert item["codex_run_posted_at"] == "2026-05-07T02:00:00Z"
    assert item["ai_reviews_posted_count"] == 1


def test_process_item_no_artifacts_skips_with_no_history_message() -> None:
    item = {"slug": "empty"}
    out = mod.process_item("CodeEagle/lzcat-apps", item, dry_run=True)
    assert out == {"slug": "empty", "skipped": "no history"}


def test_main_picks_up_items_without_state_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Items that only have discovery_review / codex / last_error / ai-reviews
    must still get an issue and comments — historically only state_history
    was mirrored, which left ~99% of the queue without an issue."""
    queue_path = tmp_path / "registry" / "auto-migration" / "queue.json"
    queue_path.parent.mkdir(parents=True)
    item = {
        "slug": "no-history-but-reviewed",
        "id": "github:owner/no-history-but-reviewed",
        "candidate": {"repo_url": "https://github.com/owner/no-history-but-reviewed"},
        "discovery_review": {
            "status": "skip", "score": 0.04, "reviewer": "claude",
            "reviewed_at": "2026-05-07T05:00:00Z",
            "reason": "static site only", "evidence": ["no Docker"],
        },
    }
    queue = {"items": [item]}
    queue_path.write_text(json.dumps(queue), encoding="utf-8")

    ai_path = tmp_path / "registry" / "auto-migration" / "ai-reviews.jsonl"
    ai_path.write_text(
        json.dumps({
            "slug": "no-history-but-reviewed", "ts": "2026-05-07T04:00:00Z",
            "reviewer": "discovery", "verdict": "skip", "score": 0.04,
            "reason": "static site only", "evidence": ["no Docker"],
        }) + "\n",
        encoding="utf-8",
    )

    posts: list[str] = []

    def fake_gh(args, *, input=None):  # noqa: ANN001
        if args[0:2] == ["issue", "list"]:
            return 0, "[]", ""
        if args[0:2] == ["issue", "create"]:
            return 0, "https://github.com/CodeEagle/lzcat-apps/issues/200\n", ""
        if args[0:2] == ["issue", "comment"]:
            posts.append(input or "")
            return 0, "", ""
        if args[0:2] == ["label", "create"]:
            return 0, "", ""
        return 0, "", ""

    monkeypatch.setattr(sys, "argv", [
        "state_history_to_issues",
        "--repo-root", str(tmp_path),
        "--repo", "CodeEagle/lzcat-apps",
        "--queue-path", "registry/auto-migration/queue.json",
        "--ai-reviews-path", "registry/auto-migration/ai-reviews.jsonl",
    ])
    with patch.object(mod, "_gh", side_effect=fake_gh):
        rc = mod.main()
    assert rc == 0
    after = json.loads(queue_path.read_text(encoding="utf-8"))
    saved = after["items"][0]
    assert saved["github_issue_number"] == 200
    assert saved["discovery_review_posted_at"] == "2026-05-07T05:00:00Z"
    assert saved["ai_reviews_posted_count"] == 1
    # ai_review (04:00) posted before discovery_review (05:00).
    assert len(posts) == 2
    assert "AI Review" in posts[0]
    assert "Discovery Review" in posts[1]
