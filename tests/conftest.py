"""Test-suite scaffolding.

Redirects ``state_history.DEFAULT_LOG_PATH`` to a per-session temp file so
tests that exercise queue.state mutations (via the wired call sites in
discovery_gate / resurrect_filtered / auto_migration_service) don't append
junk into the real ``registry/auto-migration/state-history.jsonl`` checked
into the repo. Without this, running ``pytest tests/`` once contaminates
the audit log with hundreds of mock-slug entries (`demo`, `bar`, `x`, ...).

Tests that explicitly want to verify the global-log behavior pass
``log_path=`` / ``log_root=`` directly to ``record_state_transition`` —
those bypass the redirect and use whatever path they specify.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(autouse=True, scope="session")
def _isolate_state_history_log() -> None:
    """Point DEFAULT_LOG_PATH at a session-scoped temp file.

    Note: Python binds keyword-only argument defaults at function-def
    time, so updating the module's DEFAULT_LOG_PATH attribute is NOT
    enough — we also have to overwrite the bound default on the
    function's ``__kwdefaults__`` dict for the redirect to take effect
    on calls that don't pass log_path explicitly.
    """
    try:
        from scripts import state_history
    except ImportError:
        return
    tmp = Path(tempfile.mkdtemp(prefix="lzcat-test-state-history-"))
    target = tmp / "state-history.jsonl"
    state_history.DEFAULT_LOG_PATH = target
    if state_history.record_state_transition.__kwdefaults__ is not None:
        state_history.record_state_transition.__kwdefaults__["log_path"] = target
    yield
    try:
        if target.exists():
            target.unlink()
        tmp.rmdir()
    except OSError:
        pass
