"""Migration state I/O for full_migrate.py.

Manages .migration-state.json files that track migration progress,
problems, and verification status for each app.
"""

from __future__ import annotations

import dataclasses
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
STATE_FILENAME = ".migration-state.json"


# ---------------------------------------------------------------------------
# Core (Task 1)
# ---------------------------------------------------------------------------

def new_empty_state(source_input: str) -> dict[str, Any]:
    """Create fresh state dict with schema_version=1, timestamps, empty context/steps/problems/verification."""
    now = datetime.now(timezone.utc).isoformat()
    return {
        "schema_version": SCHEMA_VERSION,
        "source_input": source_input,
        "created_at": now,
        "updated_at": now,
        "context": {},
        "steps": {},
        "problems": [],
        "verification": {},
    }


def save_state(app_dir: Path, state: dict[str, Any]) -> None:
    """Atomically write state (write .tmp then os.replace). Auto-update updated_at."""
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    target = app_dir / STATE_FILENAME
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, target)


def load_state(app_dir: Path) -> dict[str, Any] | None:
    """Read .migration-state.json from app_dir. Return None if not found."""
    target = app_dir / STATE_FILENAME
    if not target.exists():
        return None
    return json.loads(target.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Query (Task 2)
# ---------------------------------------------------------------------------

def get_last_completed_step(state: dict[str, Any]) -> int:
    """Return highest step number where completed=True, or 0."""
    steps = state.get("steps", {})
    completed = [
        int(k)
        for k, v in steps.items()
        if v.get("completed") is True
    ]
    return max(completed) if completed else 0


def should_skip_step(state: dict[str, Any], step: int) -> bool:
    """Return True if step is already completed."""
    step_data = state.get("steps", {}).get(str(step))
    if step_data is None:
        return False
    return step_data.get("completed") is True


def mark_step_completed(
    state: dict[str, Any],
    step: int,
    *,
    conclusion: str,
    **extra: Any,
) -> None:
    """Set steps[str(step)] = {completed: True, completed_at: now, conclusion, ...extra}."""
    state["steps"][str(step)] = {
        "completed": True,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "conclusion": conclusion,
        **extra,
    }


# ---------------------------------------------------------------------------
# Problem Tracking (Task 3)
# ---------------------------------------------------------------------------

def add_problem(
    state: dict[str, Any],
    step: int,
    description: str,
    category: str,
) -> str:
    """Append problem with auto-incremented id (p1, p2, ...). status=open. Return id."""
    problems = state.setdefault("problems", [])
    problem_id = f"p{len(problems) + 1}"
    problems.append({
        "id": problem_id,
        "step": step,
        "description": description,
        "category": category,
        "status": "open",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return problem_id


def resolve_problem(
    state: dict[str, Any],
    problem_id: str,
    resolution: str,
) -> None:
    """Set status=resolved, resolution, resolved_at. Raise ValueError if not found."""
    for problem in state.get("problems", []):
        if problem["id"] == problem_id:
            problem["status"] = "resolved"
            problem["resolution"] = resolution
            problem["resolved_at"] = datetime.now(timezone.utc).isoformat()
            return
    raise ValueError(f"Problem {problem_id} not found")


def get_pending_backports(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Return problems where status=resolved and backport.committed=False."""
    results: list[dict[str, Any]] = []
    for problem in state.get("problems", []):
        if problem.get("status") == "resolved":
            backport = problem.get("backport", {})
            if not backport.get("committed", False):
                results.append(problem)
    return results


def mark_backported(
    state: dict[str, Any],
    problem_id: str,
    target: str,
    description: str,
) -> None:
    """Set status=backported, backport={target, description, committed: True}."""
    for problem in state.get("problems", []):
        if problem["id"] == problem_id:
            problem["status"] = "backported"
            problem["backport"] = {
                "target": target,
                "description": description,
                "committed": True,
            }
            return
    raise ValueError(f"Problem {problem_id} not found")


# ---------------------------------------------------------------------------
# Serialization (Task 4)
# ---------------------------------------------------------------------------

def serialize_path(p: Path | None, repo_root: Path) -> str | None:
    """Convert absolute Path to repo-root-relative string. None -> None."""
    if p is None:
        return None
    try:
        return str(p.relative_to(repo_root))
    except ValueError:
        return str(p)


def serialize_paths(paths: list[Path], repo_root: Path) -> list[str]:
    """Convert list of Paths to relative strings."""
    return [serialize_path(p, repo_root) for p in paths]


def serialize_set(s: set | None) -> list:
    """Convert set to sorted list. None -> []."""
    if s is None:
        return []
    return sorted(s)


def serialize_dataclass(obj: Any) -> dict[str, Any]:
    """Convert dataclass to dict, recursively converting Path to str."""
    if not dataclasses.is_dataclass(obj) or isinstance(obj, type):
        raise TypeError(f"{obj!r} is not a dataclass instance")

    result: dict[str, Any] = {}
    for field in dataclasses.fields(obj):
        value = getattr(obj, field.name)
        result[field.name] = _serialize_value(value)
    return result


def _serialize_value(value: Any) -> Any:
    """Recursively serialize a value, converting Paths and dataclasses."""
    if isinstance(value, Path):
        return str(value)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return serialize_dataclass(value)
    if isinstance(value, dict):
        return {k: _serialize_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize_value(v) for v in value]
    if isinstance(value, set):
        return sorted(_serialize_value(v) for v in value)
    return value


# ---------------------------------------------------------------------------
# Exception + Finder (Task 5)
# ---------------------------------------------------------------------------

class MigrationProblem(Exception):
    """Exception with category and step attributes."""

    def __init__(self, message: str, *, category: str, step: int) -> None:
        super().__init__(message)
        self.category = category
        self.step = step


def find_state_by_source(
    apps_dir: Path,
    source_input: str,
) -> tuple[Path, dict[str, Any]] | None:
    """Scan apps/*/.migration-state.json for matching source_input. Return (app_dir, state) or None."""
    if not apps_dir.is_dir():
        return None
    for child in sorted(apps_dir.iterdir()):
        if not child.is_dir():
            continue
        state = load_state(child)
        if state is not None and state.get("source_input") == source_input:
            return (child, state)
    return None


# ---------------------------------------------------------------------------
# Comparison (Task 6)
# ---------------------------------------------------------------------------

def compare_states(
    baseline: dict[str, Any],
    current: dict[str, Any],
) -> list[dict[str, str]]:
    """Deep-compare two state dicts, ignoring timestamps. Returns list of diffs."""
    ignore_keys = {"created_at", "updated_at", "completed_at", "resolved_at", "schema_version"}
    diffs: list[dict[str, str]] = []

    def _compare(path: str, a: Any, b: Any) -> None:
        if isinstance(a, dict) and isinstance(b, dict):
            all_keys = set(a.keys()) | set(b.keys())
            for k in sorted(all_keys):
                if k in ignore_keys:
                    continue
                sub_path = f"{path}.{k}" if path else k
                _compare(sub_path, a.get(k), b.get(k))
        elif isinstance(a, list) and isinstance(b, list):
            if len(a) != len(b):
                diffs.append({"path": path, "diff_type": "length_mismatch",
                              "detail": f"baseline={len(a)}, current={len(b)}"})
            for i, (ai, bi) in enumerate(zip(a, b)):
                _compare(f"{path}[{i}]", ai, bi)
        elif a != b:
            diffs.append({"path": path, "diff_type": "value_mismatch",
                          "detail": f"baseline={a!r}, current={b!r}"})

    _compare("context", baseline.get("context", {}), current.get("context", {}))
    return diffs
