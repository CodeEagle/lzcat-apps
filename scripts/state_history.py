"""Per-item + global state-transition audit for queue.json items.

Every site that mutates ``item["state"]`` should call ``record_state_transition``
instead of the bare assignment. The helper:

  1. Updates ``item["state"]`` and ``item["updated_at"]``.
  2. Appends a structured entry to ``item["state_history"]`` (creates the list
     if missing). Entry shape::

         {"from": <prev_state | null>, "to": <new_state>,
          "reason": <human-readable>, "source": <call-site label>,
          "ts": <UTC iso>, "run_id": <GITHUB_RUN_ID if set>}

  3. Best-effort appends ``{slug, id, **entry}`` to a global JSONL log at
     ``registry/auto-migration/state-history.jsonl`` (or whatever ``log_path``
     resolves to under ``log_root``). FS errors are swallowed so a log-write
     hiccup never breaks an otherwise-correct cycle.

The helper is idempotent on (from, to, reason) — re-entering the same
transition with the same reason refreshes ``updated_at`` but does not
duplicate the history entry.
"""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_LOG_PATH = Path("registry/auto-migration/state-history.jsonl")


def utc_now_iso() -> str:
    """UTC timestamp matching the format used elsewhere in the repo."""
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def record_state_transition(
    item: dict[str, Any],
    new_state: str,
    *,
    reason: str,
    source: str,
    now: str | None = None,
    run_id: str | None = None,
    log_path: Path | None = DEFAULT_LOG_PATH,
    log_root: Path | None = None,
) -> dict[str, Any]:
    """Mutate ``item`` to ``new_state`` and append a history entry.

    Args:
        item: queue item dict (mutated in-place).
        new_state: target state name.
        reason: human-readable explanation surfaced in audit log + UI.
        source: call-site label (e.g. ``"discovery_gate.filter"``) so it's
            obvious which code path drove the transition.
        now: optional UTC iso timestamp; defaults to ``utc_now_iso()``.
        run_id: optional override for the GitHub Actions run id; falls back to
            ``GITHUB_RUN_ID`` env var.
        log_path: path of the global JSONL log relative to ``log_root``
            (or absolute). Pass ``None`` to skip global logging.
        log_root: prefix for relative ``log_path``; defaults to current dir.

    Returns:
        The entry that ended up in ``item["state_history"]`` (the new one or
        the existing duplicate). Useful for tests.
    """
    prev_state = item.get("state")
    if prev_state is not None:
        prev_state = str(prev_state).strip() or None

    ts = now or utc_now_iso()
    rid = run_id if run_id is not None else (os.environ.get("GITHUB_RUN_ID") or None)

    history = item.setdefault("state_history", [])
    if not isinstance(history, list):  # corrupted upstream — reset
        history = []
        item["state_history"] = history

    # Idempotent guard: when item is already at the target state and the
    # last history entry already records this exact reason, skip the
    # append (callers like update_item_state may re-enter the same state
    # across cycle iterations and we don't want each attempt to spam the
    # audit log). A re-entry with a *different* reason still appends —
    # that's a meaningful annotation (e.g. cycle 1 = "build_failed: nft
    # missing", cycle 2 = "build_failed: real upstream error").
    last = history[-1] if history and isinstance(history[-1], dict) else None
    if (
        prev_state == new_state
        and last is not None
        and last.get("to") == new_state
        and last.get("reason") == reason
    ):
        item["updated_at"] = ts
        return last  # type: ignore[return-value]

    entry: dict[str, Any] = {
        "from": prev_state,
        "to": new_state,
        "reason": reason,
        "source": source,
        "ts": ts,
    }
    if rid:
        entry["run_id"] = rid

    history.append(entry)
    item["state"] = new_state
    item["updated_at"] = ts

    if log_path is not None:
        target = log_path if log_path.is_absolute() else (log_root or Path(".")) / log_path
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            line = json.dumps(
                {"slug": item.get("slug"), "id": item.get("id"), **entry},
                ensure_ascii=False,
            )
            with target.open("a", encoding="utf-8") as fp:
                fp.write(line + "\n")
        except OSError:
            # Best-effort: log-write failure must not abort the cycle.
            pass

    return entry
