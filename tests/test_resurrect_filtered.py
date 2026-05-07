"""Tests for ``scripts.resurrect_filtered.reset_item``."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.resurrect_filtered import reset_item, should_reset


def _make_filtered_item(*, filtered_reason: str = "ai_discovery_skip", status_reason: str = "") -> dict[str, Any]:
    return {
        "id": "github:owner/demo",
        "slug": "demo",
        "source": "owner/demo",
        "state": "filtered_out",
        "candidate": {"full_name": "owner/demo", "repo_url": "https://github.com/owner/demo",
                      "status_reason": status_reason},
        "filtered_reason": filtered_reason,
        "last_error": "stale error message",
        "discovery_review": {
            "score": 0.12,
            "reason": "old prompt thought this was a naked framework",
            "evidence": ["Description says 'framework'", "10 stars"],
            "reviewed_at": "2026-05-06T05:51:36Z",
            "status": "skip",
            "verdict": "skip",
            "last_status": "completed",
            "last_returncode": 0,
            "last_run_at": "2026-05-06T05:51:36Z",
            "codex_attempts": 1,
        },
    }


def test_reset_item_flips_state_to_discovery_review() -> None:
    item = _make_filtered_item()
    reset_item(item, now="2026-05-07T07:34:19Z")
    assert item["state"] == "discovery_review"
    assert item["candidate_status"] == "needs_review"


def test_reset_item_clears_old_verdict_payload() -> None:
    """The old prompt's score/reason/evidence/reviewed_at must be cleared
    so the resurrected item doesn't masquerade as freshly-scored under the
    new prompt. ai-reviews.jsonl + state_history retain the old verdict
    for audit; no need to keep a second copy on the queue item.
    """
    item = _make_filtered_item()
    reset_item(item, now="2026-05-07T07:34:19Z")
    review = item["discovery_review"]
    assert "score" not in review
    assert "reason" not in review
    assert "evidence" not in review
    assert "reviewed_at" not in review
    assert "verdict" not in review
    assert "last_status" not in review
    assert review["status"] == "pending"
    assert review["codex_attempts"] == 0


def test_reset_item_writes_audit_fields() -> None:
    item = _make_filtered_item(filtered_reason="ai_discovery_skip")
    reset_item(item, now="2026-05-07T07:34:19Z")
    assert item["resurrected_at"] == "2026-05-07T07:34:19Z"
    assert item["resurrected_from_reason"] == "ai_discovery_skip"
    assert "filtered_reason" not in item
    assert "last_error" not in item


def test_reset_item_appends_state_history_entry() -> None:
    """Reset must record the transition via state_history helper so the
    Last State Change board field reflects the resurrection."""
    item = _make_filtered_item()
    reset_item(item, now="2026-05-07T07:34:19Z")
    history = item.get("state_history")
    assert isinstance(history, list) and history
    last = history[-1]
    assert last["from"] == "filtered_out"
    assert last["to"] == "discovery_review"
    assert "ai_discovery_skip" in last["reason"]
    assert last["source"] == "resurrect_filtered"


def test_should_reset_matches_ai_discovery_skip() -> None:
    item = _make_filtered_item(filtered_reason="ai_discovery_skip")
    matched, reason = should_reset(item)
    assert matched is True
    assert reason == "ai_discovery_skip"


def test_should_reset_skips_already_migrated_by_other() -> None:
    item = _make_filtered_item(filtered_reason="candidate_already_migrated_by_other")
    matched, _ = should_reset(item)
    assert matched is False


def test_should_reset_does_not_touch_non_commercial_license() -> None:
    """Items filtered for license reasons are policy decisions, not
    quality calls — they must NOT be resurrected when the AI prompt
    loosens.
    """
    item = _make_filtered_item(filtered_reason="non_commercial_license")
    matched, _ = should_reset(item)
    assert matched is False
