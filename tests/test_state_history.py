"""Tests for ``scripts.state_history`` — per-item history + global JSONL log."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from scripts.state_history import record_state_transition


@pytest.fixture
def isolated_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Run each test against a tmp log file, with no GITHUB_RUN_ID leakage."""
    monkeypatch.delenv("GITHUB_RUN_ID", raising=False)
    return tmp_path / "registry" / "auto-migration" / "state-history.jsonl"


def _read_log(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_first_transition_writes_history_and_log(tmp_path: Path, isolated_log: Path) -> None:
    item: dict[str, Any] = {"id": "github:foo/bar", "slug": "bar"}
    entry = record_state_transition(
        item,
        "discovery_review",
        reason="queued for AI review",
        source="discovery_gate.queue",
        now="2026-05-07T08:00:00Z",
        log_path=Path("registry/auto-migration/state-history.jsonl"),
        log_root=tmp_path,
    )
    assert item["state"] == "discovery_review"
    assert item["updated_at"] == "2026-05-07T08:00:00Z"
    assert item["state_history"] == [entry]
    assert entry == {
        "from": None,
        "to": "discovery_review",
        "reason": "queued for AI review",
        "source": "discovery_gate.queue",
        "ts": "2026-05-07T08:00:00Z",
    }
    log_entries = _read_log(isolated_log)
    assert len(log_entries) == 1
    assert log_entries[0]["slug"] == "bar"
    assert log_entries[0]["id"] == "github:foo/bar"
    assert log_entries[0]["to"] == "discovery_review"


def test_subsequent_transition_appends_history(tmp_path: Path, isolated_log: Path) -> None:
    item: dict[str, Any] = {"id": "github:foo/bar", "slug": "bar", "state": "discovery_review"}
    record_state_transition(
        item,
        "ready",
        reason="AI verdict=migrate score=0.9",
        source="project_board.cmd_sync",
        now="2026-05-07T09:00:00Z",
        log_path=Path("registry/auto-migration/state-history.jsonl"),
        log_root=tmp_path,
    )
    record_state_transition(
        item,
        "scaffolded",
        reason="auto_migrate.scaffold rc=0",
        source="auto_migrate.scaffold",
        now="2026-05-07T09:30:00Z",
        log_path=Path("registry/auto-migration/state-history.jsonl"),
        log_root=tmp_path,
    )
    assert item["state"] == "scaffolded"
    assert [(e["from"], e["to"]) for e in item["state_history"]] == [
        ("discovery_review", "ready"),
        ("ready", "scaffolded"),
    ]
    assert len(_read_log(isolated_log)) == 2


def test_idempotent_repeat_with_same_reason(tmp_path: Path, isolated_log: Path) -> None:
    item: dict[str, Any] = {"id": "github:foo/bar", "slug": "bar", "state": "ready"}
    record_state_transition(
        item,
        "scaffolded",
        reason="auto_migrate.scaffold rc=0",
        source="auto_migrate.scaffold",
        now="2026-05-07T09:00:00Z",
        log_path=Path("registry/auto-migration/state-history.jsonl"),
        log_root=tmp_path,
    )
    # Re-entering the same transition with the same reason should NOT add a
    # second history entry, only refresh updated_at.
    record_state_transition(
        item,
        "scaffolded",
        reason="auto_migrate.scaffold rc=0",
        source="auto_migrate.scaffold",
        now="2026-05-07T09:05:00Z",
        log_path=Path("registry/auto-migration/state-history.jsonl"),
        log_root=tmp_path,
    )
    assert len(item["state_history"]) == 1
    assert item["updated_at"] == "2026-05-07T09:05:00Z"
    # Global log: only 1 entry too (we don't double-log idempotent transitions)
    assert len(_read_log(isolated_log)) == 1


def test_repeat_with_different_reason_creates_new_entry(tmp_path: Path, isolated_log: Path) -> None:
    item: dict[str, Any] = {"id": "github:foo/bar", "slug": "bar", "state": "ready"}
    record_state_transition(
        item, "scaffolded", reason="first reason",  source="x", now="t1",
        log_path=Path("registry/auto-migration/state-history.jsonl"), log_root=tmp_path,
    )
    record_state_transition(
        item, "scaffolded", reason="second reason", source="y", now="t2",
        log_path=Path("registry/auto-migration/state-history.jsonl"), log_root=tmp_path,
    )
    assert len(item["state_history"]) == 2
    assert [e["reason"] for e in item["state_history"]] == ["first reason", "second reason"]
    assert len(_read_log(isolated_log)) == 2


def test_run_id_picked_from_env(tmp_path: Path, isolated_log: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_RUN_ID", "12345")
    item: dict[str, Any] = {"id": "github:foo/bar", "slug": "bar"}
    entry = record_state_transition(
        item, "ready", reason="AI verdict", source="src", now="t",
        log_path=Path("registry/auto-migration/state-history.jsonl"), log_root=tmp_path,
    )
    assert entry["run_id"] == "12345"
    assert _read_log(isolated_log)[0]["run_id"] == "12345"


def test_run_id_explicit_override_beats_env(tmp_path: Path, isolated_log: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_RUN_ID", "1")
    item: dict[str, Any] = {"id": "github:foo/bar", "slug": "bar"}
    entry = record_state_transition(
        item, "ready", reason="r", source="s", now="t", run_id="explicit",
        log_path=Path("registry/auto-migration/state-history.jsonl"), log_root=tmp_path,
    )
    assert entry["run_id"] == "explicit"


def test_corrupted_history_field_recovers(tmp_path: Path) -> None:
    item: dict[str, Any] = {"id": "x", "slug": "y", "state": "ready", "state_history": "not-a-list"}
    record_state_transition(
        item, "scaffolded", reason="r", source="s", now="t", log_path=None,
    )
    assert isinstance(item["state_history"], list)
    assert len(item["state_history"]) == 1


def test_log_path_none_skips_global_log(tmp_path: Path, isolated_log: Path) -> None:
    item: dict[str, Any] = {"id": "x", "slug": "y"}
    record_state_transition(item, "ready", reason="r", source="s", now="t", log_path=None)
    assert not isolated_log.exists()


def test_log_write_failure_does_not_raise(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Log-write IO error must be swallowed — never break a queue cycle."""
    item: dict[str, Any] = {"id": "x", "slug": "y"}

    class _Boom:
        def __truediv__(self, other: Any) -> Path:  # pragma: no cover
            raise OSError("simulated FS hiccup")

    # Force log_path resolution to throw — verifies the except clause works.
    bad_path = Path("registry/auto-migration/state-history.jsonl")
    fake_root = tmp_path / "readonly"
    fake_root.mkdir()
    fake_root.chmod(0o400)  # read-only — write should fail
    try:
        record_state_transition(
            item, "ready", reason="r", source="s", now="t",
            log_path=bad_path, log_root=fake_root,
        )
        # Item was still updated despite log-write failure
        assert item["state"] == "ready"
        assert len(item["state_history"]) == 1
    finally:
        fake_root.chmod(0o700)


def test_prev_state_normalized_to_string_or_none(tmp_path: Path) -> None:
    # state stored as int (corrupted) should not crash; normalized to str
    item: dict[str, Any] = {"id": "x", "slug": "y", "state": 123}
    entry = record_state_transition(
        item, "ready", reason="r", source="s", now="t", log_path=None,
    )
    assert entry["from"] == "123"


def test_strips_whitespace_in_prev_state(tmp_path: Path) -> None:
    item: dict[str, Any] = {"id": "x", "slug": "y", "state": "  ready  "}
    entry = record_state_transition(
        item, "scaffolded", reason="r", source="s", now="t", log_path=None,
    )
    assert entry["from"] == "ready"


def test_returns_existing_entry_on_duplicate(tmp_path: Path) -> None:
    item: dict[str, Any] = {"id": "x", "slug": "y", "state": "ready"}
    first = record_state_transition(
        item, "scaffolded", reason="r", source="s", now="t1", log_path=None,
    )
    second = record_state_transition(
        item, "scaffolded", reason="r", source="s", now="t2", log_path=None,
    )
    assert first is second  # same dict instance returned on duplicate
    assert len(item["state_history"]) == 1
