# Migration Structured State Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `full_migrate.py` produce deterministic, reproducible migration output by persisting structured state to `.migration-state.json` at each step, with support for breakpoint resume, problem tracking, and from-scratch verification.

**Architecture:** New `migration_state.py` module handles all state I/O (load/save/query). The existing `full_migrate.py` main() is refactored to read/write state at each step boundary. A `MigrationProblem` exception class enables structured problem capture. CLI gains `--resume`, `--resume-from N`, and `--verify` flags.

**Tech Stack:** Python 3.10+, standard library only (json, pathlib, dataclasses), unittest for tests.

**Spec:** `docs/superpowers/specs/2026-04-09-migration-structured-state-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `scripts/migration_state.py` | Create | State I/O layer: load, save, query, problem tracking, serialization helpers |
| `scripts/full_migrate.py` | Modify | Integrate state layer: write context at each step, support resume/verify |
| `tests/test_migration_state.py` | Create | Unit tests for state I/O layer |
| `tests/test_full_migrate.py` | Modify | Add integration tests for resume and state output |

---

## Task 1: State I/O Module — Core Functions

**Files:**
- Create: `scripts/migration_state.py`
- Create: `tests/test_migration_state.py`

- [ ] **Step 1: Write failing test for `new_empty_state()`**

```python
# tests/test_migration_state.py
import json
import os
import tempfile
import unittest
from pathlib import Path

# Allow importing from scripts/
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import migration_state as ms


class NewEmptyStateTest(unittest.TestCase):
    def test_creates_state_with_schema_version_and_source(self):
        state = ms.new_empty_state("owner/repo")
        self.assertEqual(state["schema_version"], 1)
        self.assertEqual(state["source_input"], "owner/repo")
        self.assertIn("created_at", state)
        self.assertIn("context", state)
        self.assertIn("steps", state)
        self.assertIsInstance(state["problems"], list)
        self.assertEqual(len(state["problems"]), 0)
        self.assertEqual(state["steps"], {})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_migration_state.py::NewEmptyStateTest -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'migration_state'`

- [ ] **Step 3: Implement `new_empty_state()`**

```python
# scripts/migration_state.py
"""Migration state I/O layer for full_migrate.py.

Manages .migration-state.json: load, save, query, problem tracking.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
STATE_FILENAME = ".migration-state.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_empty_state(source_input: str) -> dict[str, Any]:
    """Create a fresh empty state dict."""
    now = _now_iso()
    return {
        "schema_version": SCHEMA_VERSION,
        "created_at": now,
        "updated_at": now,
        "source_input": source_input,
        "context": {},
        "steps": {},
        "problems": [],
        "verification": {},
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_migration_state.py::NewEmptyStateTest -v`
Expected: PASS

- [ ] **Step 5: Write failing tests for `save_state()` and `load_state()`**

```python
# Append to tests/test_migration_state.py

class SaveLoadStateTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.app_dir = Path(self.tmpdir) / "apps" / "myapp"
        self.app_dir.mkdir(parents=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_save_creates_file_and_load_reads_it(self):
        state = ms.new_empty_state("owner/repo")
        state["context"]["source"] = {"kind": "github_repo"}
        ms.save_state(self.app_dir, state)
        state_path = self.app_dir / ms.STATE_FILENAME
        self.assertTrue(state_path.exists())
        loaded = ms.load_state(self.app_dir)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["context"]["source"]["kind"], "github_repo")

    def test_load_returns_none_when_no_file(self):
        empty_dir = Path(self.tmpdir) / "apps" / "noapp"
        empty_dir.mkdir(parents=True)
        self.assertIsNone(ms.load_state(empty_dir))

    def test_save_updates_updated_at(self):
        state = ms.new_empty_state("owner/repo")
        original_updated = state["updated_at"]
        # Force a small time difference
        import time
        time.sleep(0.01)
        ms.save_state(self.app_dir, state)
        loaded = ms.load_state(self.app_dir)
        self.assertGreaterEqual(loaded["updated_at"], original_updated)

    def test_save_is_atomic_via_tmp_rename(self):
        state = ms.new_empty_state("owner/repo")
        ms.save_state(self.app_dir, state)
        # No .tmp file should remain
        tmp_files = list(self.app_dir.glob("*.tmp"))
        self.assertEqual(len(tmp_files), 0)
```

- [ ] **Step 6: Implement `save_state()` and `load_state()`**

```python
# Append to scripts/migration_state.py

def save_state(app_dir: Path, state: dict[str, Any]) -> None:
    """Atomically write state to .migration-state.json (write .tmp then rename)."""
    state["updated_at"] = _now_iso()
    state_path = app_dir / STATE_FILENAME
    tmp_path = state_path.with_suffix(".json.tmp")
    tmp_path.write_text(
        json.dumps(state, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    os.replace(str(tmp_path), str(state_path))


def load_state(app_dir: Path) -> dict[str, Any] | None:
    """Read existing state file. Returns None if not found."""
    state_path = app_dir / STATE_FILENAME
    if not state_path.exists():
        return None
    return json.loads(state_path.read_text(encoding="utf-8"))
```

- [ ] **Step 7: Run all tests**

Run: `python3 -m pytest tests/test_migration_state.py -v`
Expected: All PASS

- [ ] **Step 8: Commit**

```bash
git add scripts/migration_state.py tests/test_migration_state.py
git commit -m "feat: add migration_state module with new/save/load"
```

---

## Task 2: State Query Functions

**Files:**
- Modify: `scripts/migration_state.py`
- Modify: `tests/test_migration_state.py`

- [ ] **Step 1: Write failing tests for query functions**

```python
# Append to tests/test_migration_state.py

class StepQueryTest(unittest.TestCase):
    def test_get_last_completed_step_returns_highest(self):
        state = ms.new_empty_state("x")
        state["steps"]["1"] = {"completed": True}
        state["steps"]["2"] = {"completed": True}
        state["steps"]["3"] = {"completed": False}
        self.assertEqual(ms.get_last_completed_step(state), 2)

    def test_get_last_completed_step_returns_zero_when_none(self):
        state = ms.new_empty_state("x")
        self.assertEqual(ms.get_last_completed_step(state), 0)

    def test_should_skip_step_true_when_completed(self):
        state = ms.new_empty_state("x")
        state["steps"]["3"] = {"completed": True}
        self.assertTrue(ms.should_skip_step(state, 3))

    def test_should_skip_step_false_when_not_completed(self):
        state = ms.new_empty_state("x")
        state["steps"]["3"] = {"completed": False}
        self.assertFalse(ms.should_skip_step(state, 3))

    def test_should_skip_step_false_when_missing(self):
        state = ms.new_empty_state("x")
        self.assertFalse(ms.should_skip_step(state, 5))

    def test_mark_step_completed(self):
        state = ms.new_empty_state("x")
        ms.mark_step_completed(state, 4, conclusion="Done")
        self.assertTrue(state["steps"]["4"]["completed"])
        self.assertEqual(state["steps"]["4"]["conclusion"], "Done")
        self.assertIn("completed_at", state["steps"]["4"])

    def test_mark_step_completed_with_extra_data(self):
        state = ms.new_empty_state("x")
        ms.mark_step_completed(state, 7, conclusion="Pass", all_passed=True, commit_sha="abc")
        step = state["steps"]["7"]
        self.assertTrue(step["all_passed"])
        self.assertEqual(step["commit_sha"], "abc")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_migration_state.py::StepQueryTest -v`
Expected: FAIL

- [ ] **Step 3: Implement query functions**

```python
# Append to scripts/migration_state.py

def get_last_completed_step(state: dict[str, Any]) -> int:
    """Return the highest step number that is completed, or 0."""
    last = 0
    for key, step_data in state.get("steps", {}).items():
        if step_data.get("completed"):
            step_num = int(key)
            if step_num > last:
                last = step_num
    return last


def should_skip_step(state: dict[str, Any], step: int) -> bool:
    """Return True if the step is already completed."""
    step_data = state.get("steps", {}).get(str(step), {})
    return bool(step_data.get("completed"))


def mark_step_completed(
    state: dict[str, Any],
    step: int,
    *,
    conclusion: str,
    **extra: Any,
) -> None:
    """Mark a step as completed with timestamp and optional extra data."""
    step_data = {
        "completed": True,
        "completed_at": _now_iso(),
        "conclusion": conclusion,
    }
    step_data.update(extra)
    state["steps"][str(step)] = step_data
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_migration_state.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/migration_state.py tests/test_migration_state.py
git commit -m "feat: add state query functions (get_last_completed, should_skip, mark_completed)"
```

---

## Task 3: Problem Tracking

**Files:**
- Modify: `scripts/migration_state.py`
- Modify: `tests/test_migration_state.py`

- [ ] **Step 1: Write failing tests**

```python
# Append to tests/test_migration_state.py

class ProblemTrackingTest(unittest.TestCase):
    def test_add_problem_returns_id_and_appends(self):
        state = ms.new_empty_state("x")
        pid = ms.add_problem(state, step=8, description="copy-image failed", category="build")
        self.assertEqual(pid, "p1")
        self.assertEqual(len(state["problems"]), 1)
        p = state["problems"][0]
        self.assertEqual(p["id"], "p1")
        self.assertEqual(p["step"], 8)
        self.assertEqual(p["status"], "open")
        self.assertIn("created_at", p)

    def test_add_multiple_problems_increments_id(self):
        state = ms.new_empty_state("x")
        ms.add_problem(state, step=7, description="preflight fail", category="preflight")
        pid2 = ms.add_problem(state, step=8, description="build fail", category="build")
        self.assertEqual(pid2, "p2")
        self.assertEqual(len(state["problems"]), 2)

    def test_resolve_problem(self):
        state = ms.new_empty_state("x")
        ms.add_problem(state, step=8, description="fail", category="build")
        ms.resolve_problem(state, "p1", resolution="Set package to public")
        p = state["problems"][0]
        self.assertEqual(p["status"], "resolved")
        self.assertEqual(p["resolution"], "Set package to public")
        self.assertIn("resolved_at", p)

    def test_get_pending_backports(self):
        state = ms.new_empty_state("x")
        ms.add_problem(state, step=8, description="fail", category="build")
        ms.resolve_problem(state, "p1", resolution="manual fix")
        pending = ms.get_pending_backports(state)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["id"], "p1")

    def test_mark_backported(self):
        state = ms.new_empty_state("x")
        ms.add_problem(state, step=8, description="fail", category="build")
        ms.resolve_problem(state, "p1", resolution="fix")
        ms.mark_backported(state, "p1", target="full_migrate.py", description="Added pre-check")
        p = state["problems"][0]
        self.assertEqual(p["status"], "backported")
        self.assertTrue(p["backport"]["committed"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_migration_state.py::ProblemTrackingTest -v`
Expected: FAIL

- [ ] **Step 3: Implement problem tracking**

```python
# Append to scripts/migration_state.py

def add_problem(
    state: dict[str, Any],
    step: int,
    description: str,
    category: str,
) -> str:
    """Append a problem record. Returns the problem id (p1, p2, ...)."""
    problems = state.setdefault("problems", [])
    pid = f"p{len(problems) + 1}"
    problems.append({
        "id": pid,
        "step": step,
        "created_at": _now_iso(),
        "description": description,
        "category": category,
        "status": "open",
        "resolution": None,
        "resolved_at": None,
        "backport": {
            "target": None,
            "description": None,
            "committed": False,
        },
    })
    return pid


def resolve_problem(state: dict[str, Any], problem_id: str, resolution: str) -> None:
    """Mark a problem as resolved with a resolution description."""
    for p in state.get("problems", []):
        if p["id"] == problem_id:
            p["status"] = "resolved"
            p["resolution"] = resolution
            p["resolved_at"] = _now_iso()
            return
    raise ValueError(f"Problem {problem_id} not found")


def get_pending_backports(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Return problems that are resolved but not yet backported."""
    return [
        p for p in state.get("problems", [])
        if p["status"] == "resolved" and not p.get("backport", {}).get("committed")
    ]


def mark_backported(
    state: dict[str, Any],
    problem_id: str,
    target: str,
    description: str,
) -> None:
    """Mark a resolved problem as backported to a script."""
    for p in state.get("problems", []):
        if p["id"] == problem_id:
            p["status"] = "backported"
            p["backport"] = {
                "target": target,
                "description": description,
                "committed": True,
            }
            return
    raise ValueError(f"Problem {problem_id} not found")
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_migration_state.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/migration_state.py tests/test_migration_state.py
git commit -m "feat: add problem tracking (add/resolve/backport lifecycle)"
```

---

## Task 4: Serialization Helpers

**Files:**
- Modify: `scripts/migration_state.py`
- Modify: `tests/test_migration_state.py`

- [ ] **Step 1: Write failing tests**

```python
# Append to tests/test_migration_state.py

class SerializationTest(unittest.TestCase):
    def test_serialize_path_relative(self):
        repo_root = Path("/home/user/lzcat-apps")
        p = Path("/home/user/lzcat-apps/apps/myapp/Dockerfile")
        self.assertEqual(ms.serialize_path(p, repo_root), "apps/myapp/Dockerfile")

    def test_serialize_path_none(self):
        self.assertIsNone(ms.serialize_path(None, Path("/root")))

    def test_serialize_paths_list(self):
        repo_root = Path("/repo")
        paths = [Path("/repo/a.txt"), Path("/repo/b/c.txt")]
        self.assertEqual(ms.serialize_paths(paths, repo_root), ["a.txt", "b/c.txt"])

    def test_serialize_set_to_sorted_list(self):
        self.assertEqual(ms.serialize_set({"c", "a", "b"}), ["a", "b", "c"])

    def test_serialize_set_none(self):
        self.assertEqual(ms.serialize_set(None), [])

    def test_serialize_dataclass(self):
        from dataclasses import dataclass

        @dataclass
        class Sample:
            name: str
            value: int

        result = ms.serialize_dataclass(Sample(name="test", value=42))
        self.assertEqual(result, {"name": "test", "value": 42})

    def test_full_round_trip_with_paths(self):
        """State with Path values survives save/load cycle."""
        tmpdir = tempfile.mkdtemp()
        app_dir = Path(tmpdir) / "apps" / "test"
        app_dir.mkdir(parents=True)
        try:
            state = ms.new_empty_state("x")
            state["context"]["registration"] = {
                "monorepo_path": "apps/test",
                "config_path": "registry/repos/test.json",
            }
            ms.save_state(app_dir, state)
            loaded = ms.load_state(app_dir)
            self.assertEqual(loaded["context"]["registration"]["monorepo_path"], "apps/test")
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_migration_state.py::SerializationTest -v`
Expected: FAIL

- [ ] **Step 3: Implement serialization helpers**

```python
# Append to scripts/migration_state.py
from dataclasses import asdict, is_dataclass


def serialize_path(p: Path | None, repo_root: Path) -> str | None:
    """Convert an absolute Path to a repo-root-relative string."""
    if p is None:
        return None
    try:
        return str(p.relative_to(repo_root))
    except ValueError:
        return str(p)


def serialize_paths(paths: list[Path], repo_root: Path) -> list[str]:
    """Convert a list of Paths to relative strings."""
    return [serialize_path(p, repo_root) for p in paths]


def serialize_set(s: set | None) -> list:
    """Convert a set to a sorted list for deterministic JSON."""
    if s is None:
        return []
    return sorted(s)


def serialize_dataclass(obj: Any) -> dict[str, Any]:
    """Convert a dataclass instance to a dict, handling Path fields."""
    if not is_dataclass(obj):
        raise TypeError(f"{type(obj)} is not a dataclass")
    result = asdict(obj)
    # Convert any remaining Path objects to strings
    def _convert(v: Any) -> Any:
        if isinstance(v, Path):
            return str(v)
        if isinstance(v, dict):
            return {k: _convert(val) for k, val in v.items()}
        if isinstance(v, list):
            return [_convert(item) for item in v]
        return v
    return _convert(result)
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_migration_state.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/migration_state.py tests/test_migration_state.py
git commit -m "feat: add serialization helpers for Path, set, dataclass"
```

---

## Task 5: MigrationProblem Exception + find_state_by_source()

**Files:**
- Modify: `scripts/migration_state.py`
- Modify: `tests/test_migration_state.py`

- [ ] **Step 1: Write failing tests**

```python
# Append to tests/test_migration_state.py

class MigrationProblemTest(unittest.TestCase):
    def test_exception_carries_category(self):
        exc = ms.MigrationProblem("build failed", category="build", step=8)
        self.assertEqual(str(exc), "build failed")
        self.assertEqual(exc.category, "build")
        self.assertEqual(exc.step, 8)


class FindStateBySourceTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.apps_dir = Path(self.tmpdir) / "apps"
        # Create two app dirs with state files
        for slug, source in [("myapp", "owner/myapp"), ("other", "owner/other")]:
            app_dir = self.apps_dir / slug
            app_dir.mkdir(parents=True)
            state = ms.new_empty_state(source)
            ms.save_state(app_dir, state)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_finds_matching_state(self):
        result = ms.find_state_by_source(self.apps_dir, "owner/myapp")
        self.assertIsNotNone(result)
        app_dir, state = result
        self.assertEqual(app_dir.name, "myapp")
        self.assertEqual(state["source_input"], "owner/myapp")

    def test_returns_none_when_no_match(self):
        result = ms.find_state_by_source(self.apps_dir, "owner/unknown")
        self.assertIsNone(result)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_migration_state.py::MigrationProblemTest tests/test_migration_state.py::FindStateBySourceTest -v`
Expected: FAIL

- [ ] **Step 3: Implement**

```python
# Append to scripts/migration_state.py

class MigrationProblem(Exception):
    """Raised when a migration step encounters a trackable problem."""

    def __init__(self, message: str, *, category: str, step: int):
        super().__init__(message)
        self.category = category
        self.step = step


def find_state_by_source(
    apps_dir: Path, source_input: str,
) -> tuple[Path, dict[str, Any]] | None:
    """Scan apps/*/.migration-state.json for a matching source_input.

    Used by --resume when slug is not yet known.
    """
    if not apps_dir.is_dir():
        return None
    for app_dir in sorted(apps_dir.iterdir()):
        if not app_dir.is_dir():
            continue
        state = load_state(app_dir)
        if state is not None and state.get("source_input") == source_input:
            return app_dir, state
    return None
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_migration_state.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/migration_state.py tests/test_migration_state.py
git commit -m "feat: add MigrationProblem exception and find_state_by_source"
```

---

## Task 6: CLI Arguments — --resume, --resume-from, --verify

**Files:**
- Modify: `scripts/full_migrate.py` (line 6059: `parse_args()`)
- Modify: `tests/test_full_migrate.py`

- [ ] **Step 1: Write failing test**

```python
# Append to tests/test_full_migrate.py

class ParseArgsResumeTest(unittest.TestCase):
    def test_resume_flag(self):
        # Simulate sys.argv
        import sys
        old_argv = sys.argv
        try:
            sys.argv = ["full_migrate.py", "owner/repo", "--resume"]
            args = full_migrate_module.parse_args()
            self.assertTrue(args.resume)
            self.assertIsNone(args.resume_from)
            self.assertFalse(args.verify)
        finally:
            sys.argv = old_argv

    def test_resume_from_flag(self):
        import sys
        old_argv = sys.argv
        try:
            sys.argv = ["full_migrate.py", "owner/repo", "--resume-from", "5"]
            args = full_migrate_module.parse_args()
            self.assertEqual(args.resume_from, 5)
        finally:
            sys.argv = old_argv

    def test_verify_flag(self):
        import sys
        old_argv = sys.argv
        try:
            sys.argv = ["full_migrate.py", "owner/repo", "--verify"]
            args = full_migrate_module.parse_args()
            self.assertTrue(args.verify)
        finally:
            sys.argv = old_argv
```

Note: `full_migrate_module` is the imported module — check how existing tests import it. The current `test_full_migrate.py` uses `subprocess.run()` to call the script, not direct import. For parse_args testing, use the same subprocess pattern or add a direct import path. Match the existing test pattern:

```python
# If direct import not available, test via subprocess:
class ParseArgsResumeTest(unittest.TestCase):
    def test_resume_flag_accepted(self):
        """Verify --resume is a valid flag (no argparse error)."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "owner/repo", "--resume", "--no-build", "--repo-root", self.repo_root],
            capture_output=True, text=True,
        )
        # Should not fail with "unrecognized arguments"
        self.assertNotIn("unrecognized arguments", result.stderr)
```

- [ ] **Step 2: Add arguments to `parse_args()`**

At `scripts/full_migrate.py` line 6059, in the `parse_args()` function, add after the `--build-mode` argument (before `return parser.parse_args()`):

```python
    parser.add_argument("--resume", action="store_true",
                        help="Resume from last completed step (reads .migration-state.json)")
    parser.add_argument("--resume-from", type=int, metavar="N", default=None,
                        help="Resume from step N (1-10), keeping context from prior steps")
    parser.add_argument("--verify", action="store_true",
                        help="Run from scratch and compare against existing state for reproducibility")
```

- [ ] **Step 3: Run existing tests to verify no regression**

Run: `python3 -m pytest tests/test_full_migrate.py -v`
Expected: All existing tests PASS (new args are optional, don't affect existing behavior)

- [ ] **Step 4: Commit**

```bash
git add scripts/full_migrate.py tests/test_full_migrate.py
git commit -m "feat: add --resume, --resume-from, --verify CLI arguments"
```

---

## Task 7: Integrate State into main() — Steps 1-3

This is the core integration. We modify `main()` to create/load state and populate `context` after Steps 1, 2, and 3.

**Files:**
- Modify: `scripts/full_migrate.py` (line 6074: `main()`)

- [ ] **Step 1: Add import at top of full_migrate.py**

At `scripts/full_migrate.py` line 23 (after `import bootstrap_migration as bm`), add:

```python
import migration_state as ms
```

- [ ] **Step 2: Add state initialization in main() before Step 1**

At line ~6094 (after `step_state = StepState()` and before the try block), insert the state loading logic:

```python
    # --- State management ---
    # Slug is unknown until Step 2; for --resume, scan apps/ to find matching state
    existing_state = None
    resolved_app_dir = None
    if not args.force and not args.verify:
        found = ms.find_state_by_source(repo_root / "apps", args.source)
        if found:
            resolved_app_dir, existing_state = found

    if args.resume_from is not None:
        start_step = args.resume_from
    elif args.resume and existing_state:
        start_step = ms.get_last_completed_step(existing_state) + 1
    elif existing_state and not args.force:
        start_step = ms.get_last_completed_step(existing_state) + 1
    else:
        start_step = 1

    state = existing_state if existing_state else ms.new_empty_state(args.source)
```

- [ ] **Step 3: Wrap Step 1 with state skip/save logic**

Replace the Step 1 block (lines ~6106-6117) with:

```python
        if start_step <= 1:
            step_state.current_step = 1
            source_dir, extra_outputs, cleanup = prepare_source(normalized)
            step1_outputs.extend(extra_outputs)

            # Persist to state
            state["context"]["source"] = {
                "kind": normalized.kind,
                "url": normalized.source,
                "upstream_repo": normalized.upstream_repo,
                "homepage": normalized.homepage,
            }
            state["context"]["environment"] = {
                "gh_token_source": gh_token_source or "none",
                "lzc_cli_token_source": lzc_cli_token_source or "none",
                "container_runtime": runtime_name or "none",
                "image_owner": image_owner or "",
            }
            ms.mark_step_completed(state, 1,
                conclusion=f"已识别输入类型为 `{normalized.kind}`",
                scripts_called=["full_migrate.py"])

            step_report(1, "收集上游信息",
                conclusion=f"已识别输入类型为 `{normalized.kind}`，并准备好可分析的上游材料。",
                outputs=step1_outputs, risks=step1_risks,
                next_step="进入 [2/10] 选择移植路线")
        else:
            # Restore from state
            source_dir, extra_outputs, cleanup = prepare_source(normalized)
            step1_outputs.extend(extra_outputs)
```

- [ ] **Step 4: Wrap Step 2 with state skip/save logic**

Replace the Step 2 block (lines ~6119-6137) with:

```python
        if start_step <= 2:
            step_state.current_step = 2
            analysis = analyze_source(normalized, source_dir)

            # Persist route decision to state
            state["context"]["route_decision"] = {
                "route": analysis.route,
                "build_strategy": analysis.spec.get("build_strategy", ""),
                "check_strategy": analysis.spec.get("check_strategy", ""),
                "primary_service": analysis.spec.get("primary_service", ""),
                "risks": analysis.risks,
                "compose_file": ms.serialize_path(analysis.compose_file, repo_root) if analysis.compose_file else None,
                "dockerfile": ms.serialize_path(analysis.dockerfile, repo_root) if analysis.dockerfile else None,
            }
            state["context"]["version"] = {
                "upstream": analysis.spec.get("source_version", ""),
                "normalized": analysis.spec.get("version", ""),
            }
            ms.mark_step_completed(state, 2,
                conclusion=f"已自动推断构建路线为 `{analysis.route}`")

            # Now we know the slug — save state for the first time
            app_dir = repo_root / "apps" / analysis.slug
            app_dir.mkdir(parents=True, exist_ok=True)
            ms.save_state(app_dir, state)

            step_report(2, "选择移植路线",
                conclusion=f"已自动推断构建路线为 `{analysis.route}`。",
                outputs=[f"slug={analysis.slug}", f"route={analysis.route}"],
                scripts=["scripts/full_migrate.py"],
                next_step="进入 [3/10] 注册目标 app")
        else:
            # Restore analysis from state — re-run analyze_source since analysis is complex
            analysis = analyze_source(normalized, source_dir)
            app_dir = repo_root / "apps" / analysis.slug
```

- [ ] **Step 5: Wrap Step 3 with state skip/save logic**

After the Step 3 finalize_spec + apply_fixes block, add state persistence:

```python
        if start_step <= 3:
            # ... existing Step 3 code (finalize_spec, apply_generated_app_fixes) ...

            # Persist finalized spec and registration info to state
            state["context"]["finalized"] = finalized
            state["context"]["registration"] = {
                "slug": finalized["slug"],
                "monorepo_path": f"apps/{finalized['slug']}",
                "config_path": f"registry/repos/{finalized['slug']}.json",
                "index_updated": True,
            }
            ms.mark_step_completed(state, 3, conclusion="已完成 monorepo 注册")
            ms.save_state(app_dir, state)

            # ... existing step_report ...
        else:
            # Restore finalized from state
            if "finalized" in state.get("context", {}):
                finalized = state["context"]["finalized"]
            else:
                # Fallback: re-derive
                finalized = bm.finalize_spec(analysis.spec, gh_token, fetch_upstream=False)
                finalized = apply_generated_app_fixes(finalized, analysis)
```

- [ ] **Step 6: Run existing integration tests**

Run: `python3 -m pytest tests/test_full_migrate.py -v`
Expected: All existing tests still PASS. State file creation is additive and should not break existing behavior.

- [ ] **Step 7: Commit**

```bash
git add scripts/full_migrate.py
git commit -m "feat: integrate state persistence into Steps 1-3 of main()"
```

---

## Task 8: Integrate State into main() — Steps 4-10

**Files:**
- Modify: `scripts/full_migrate.py`

- [ ] **Step 1: Add state save after Step 4 (file generation)**

After the existing Step 4 block (write_files + post_write), add:

```python
            ms.mark_step_completed(state, 4,
                conclusion="骨架文件已生成",
                files_written=[str(p.relative_to(repo_root)) for p in written[:6]],
                post_write_files=[str(p.relative_to(repo_root)) for p in post_written],
                force_overwrite=effective_force)
            ms.save_state(app_dir, state)
```

- [ ] **Step 2: Add state save after Steps 5 and 6 (confirmation steps)**

After each step_report for steps 5 and 6:

```python
            # After Step 5 step_report
            ms.mark_step_completed(state, 5, conclusion="manifest 已确认")
            ms.save_state(app_dir, state)

            # After Step 6 step_report
            ms.mark_step_completed(state, 6, conclusion="剩余文件已确认")
            ms.save_state(app_dir, state)
```

- [ ] **Step 3: Add state save after Step 7 (preflight)**

After the preflight check passes and git commit succeeds:

```python
            preflight_data = {
                "all_passed": ok,
                "git_committed": True,
            }
            if not ok:
                preflight_data["issues"] = issues
                ms.add_problem(state, 7, "; ".join(issues), "preflight")
                ms.save_state(app_dir, state)
            else:
                ms.mark_step_completed(state, 7, conclusion="预检通过", **preflight_data)
                ms.save_state(app_dir, state)
```

- [ ] **Step 4: Add state save after Step 8 (build)**

After build completes (success or failure):

```python
            if build_result.returncode == 0:
                ms.mark_step_completed(state, 8,
                    conclusion="构建成功",
                    build_mode=effective_build_mode,
                    lpk_path=str(lpk_path.relative_to(repo_root)) if lpk_path and lpk_path.exists() else None)
            else:
                ms.add_problem(state, 8, f"Build failed: exit {build_result.returncode}", "build")
            ms.save_state(app_dir, state)
```

- [ ] **Step 5: Add state save after Step 9 (verify lpk)**

```python
            if lpk_path.exists():
                sha = file_sha256(lpk_path)
                ms.mark_step_completed(state, 9,
                    conclusion="lpk 已验证",
                    lpk_path=str(lpk_path.relative_to(repo_root)),
                    lpk_sha256=sha,
                    lpk_size_bytes=lpk_path.stat().st_size)
            else:
                ms.add_problem(state, 9, f"lpk not found: {lpk_path}", "artifact")
            ms.save_state(app_dir, state)
```

- [ ] **Step 6: Add state save after Step 10 (acceptance)**

```python
            # At end of Step 10, before return
            pending = ms.get_pending_backports(state)
            step10_extra = {}
            if pending:
                step10_extra["pending_backports"] = [p["id"] for p in pending]
                print(f"\n⚠ {len(pending)} resolved problems not yet backported:")
                for p in pending:
                    print(f"  - [{p['id']}] {p['description']} → {p['resolution']}")
            ms.mark_step_completed(state, 10, conclusion="验收完成", **step10_extra)
            ms.save_state(app_dir, state)
```

- [ ] **Step 7: Add MigrationProblem catch in main exception handler**

In the exception handler (the `except Exception` block at the end of main), add before the generic handler:

```python
        except ms.MigrationProblem as exc:
            traceback.print_exc()
            ms.add_problem(state, exc.step, str(exc), exc.category)
            if app_dir:
                ms.save_state(app_dir, state)
            step_report(exc.step, "自动迁移失败",
                conclusion=f"[{exc.category}] {exc}",
                outputs=[str(exc)], risks=[str(exc)])
            return 1
```

- [ ] **Step 8: Run all tests**

Run: `python3 -m pytest tests/ -v`
Expected: All PASS

- [ ] **Step 9: Commit**

```bash
git add scripts/full_migrate.py
git commit -m "feat: integrate state persistence into Steps 4-10"
```

---

## Task 9: Step Skip Logic for Resume

**Files:**
- Modify: `scripts/full_migrate.py`

- [ ] **Step 1: Add step gating to each step block**

Wrap each Step N block with:

```python
        if not ms.should_skip_step(state, N) and start_step <= N:
            # ... existing step code ...
        elif ms.should_skip_step(state, N):
            print(f"[{N}/10] ⏭ Skipped (already completed)")
```

The key steps that need state restoration when skipped:

- **Steps 1-2:** Always re-run `prepare_source()` and `analyze_source()` even when skipping (needed for `source_dir` and `analysis` variables). Only skip the state writes and reports.
- **Step 3:** Restore `finalized` from `state["context"]["finalized"]` if skipping.
- **Steps 4-6:** Skip file generation entirely (files already on disk).
- **Steps 7-10:** Run normally (they validate/build current state).

- [ ] **Step 2: Test resume scenario**

Add to `tests/test_full_migrate.py`:

```python
class ResumeFromStepTest(unittest.TestCase):
    """Test that --resume-from skips completed steps."""

    def setUp(self):
        self.repo_root = self.make_repo_root()
        # Create a source repo and run initial migration to step 7
        self.source_dir = self.make_source_repo_with_compose()

    # ... (use existing helper methods from the test class) ...

    def test_resume_from_7_skips_analysis(self):
        """First run to preflight, then resume-from 7 should not re-analyze."""
        # First run with --no-build
        result1 = self.run_script(self.source_dir, extra_args=["--no-build"])
        self.assertEqual(result1.returncode, 0)

        # Verify state file exists
        # Find the app dir (slug derived from source)
        app_dirs = list((Path(self.repo_root) / "apps").iterdir())
        self.assertGreater(len(app_dirs), 0)
        state_path = app_dirs[0] / ".migration-state.json"
        self.assertTrue(state_path.exists())

        # Resume from 7 with --no-build should pass quickly
        result2 = self.run_script(
            self.source_dir,
            extra_args=["--resume-from", "7", "--no-build"],
        )
        self.assertEqual(result2.returncode, 0)
```

- [ ] **Step 3: Run tests**

Run: `python3 -m pytest tests/test_full_migrate.py -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add scripts/full_migrate.py tests/test_full_migrate.py
git commit -m "feat: implement --resume and --resume-from step skip logic"
```

---

## Task 10: --verify Mode

**Files:**
- Modify: `scripts/full_migrate.py`
- Modify: `scripts/migration_state.py`
- Modify: `tests/test_migration_state.py`

- [ ] **Step 1: Write failing test for `compare_states()`**

```python
# Append to tests/test_migration_state.py

class CompareStatesTest(unittest.TestCase):
    def test_identical_states_produce_no_diffs(self):
        s1 = ms.new_empty_state("x")
        s1["context"]["route_decision"] = {"route": "official_image"}
        s2 = ms.new_empty_state("x")
        s2["context"]["route_decision"] = {"route": "official_image"}
        diffs = ms.compare_states(s1, s2)
        self.assertEqual(len(diffs), 0)

    def test_different_route_produces_diff(self):
        s1 = ms.new_empty_state("x")
        s1["context"]["route_decision"] = {"route": "official_image"}
        s2 = ms.new_empty_state("x")
        s2["context"]["route_decision"] = {"route": "upstream_dockerfile"}
        diffs = ms.compare_states(s1, s2)
        self.assertGreater(len(diffs), 0)
        self.assertEqual(diffs[0]["path"], "context.route_decision.route")
```

- [ ] **Step 2: Implement `compare_states()`**

```python
# Append to scripts/migration_state.py

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

    _compare("", baseline.get("context", {}), current.get("context", {}))
    return diffs
```

- [ ] **Step 3: Add verify mode to main()**

In `full_migrate.py` main(), after parsing args and before the normal flow, add:

```python
    if args.verify:
        return run_verify_mode(args.source, repo_root, state)
```

And implement:

```python
def run_verify_mode(source: str, repo_root: Path, existing_state: dict[str, Any] | None) -> int:
    """Run from scratch in temp copy and compare against existing state."""
    if existing_state is None:
        print("No existing .migration-state.json found. Run a normal migration first.")
        return 1

    print("=== Verify Mode: running from scratch ===")
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        # Copy repo to temp
        tmp_repo = Path(tmp) / "repo"
        shutil.copytree(repo_root, tmp_repo, ignore=shutil.ignore_patterns(".git", "dist", "*.lpk"))

        # Run migration from scratch in temp (equivalent to --force --no-build)
        result = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), source,
             "--repo-root", str(tmp_repo), "--force", "--no-build"],
            capture_output=True, text=True, cwd=str(tmp_repo),
        )
        if result.returncode != 0:
            print(f"Verify migration failed:\n{result.stderr[-500:]}")
            return 1

        # Find the new state
        slug = existing_state.get("context", {}).get("registration", {}).get("slug", "")
        if not slug:
            slug = existing_state.get("context", {}).get("route_decision", {}).get("primary_service", "")
        new_app_dir = tmp_repo / "apps" / slug
        new_state = ms.load_state(new_app_dir)
        if new_state is None:
            print("Verify run did not produce a state file.")
            return 1

        # Compare
        diffs = ms.compare_states(existing_state, new_state)
        if not diffs:
            print("✓ Verify PASSED: from-scratch run produces identical state")
            existing_state["verification"] = {
                "last_run": ms._now_iso(),
                "result": "pass",
                "diffs": [],
            }
        else:
            print(f"✗ Verify FAILED: {len(diffs)} differences found:")
            for d in diffs[:20]:
                print(f"  {d['path']}: {d['detail']}")
            existing_state["verification"] = {
                "last_run": ms._now_iso(),
                "result": "fail",
                "diffs": diffs,
            }

        # Save verification result back to original state
        orig_app_dir = repo_root / "apps" / slug
        ms.save_state(orig_app_dir, existing_state)
        return 0 if not diffs else 1
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/ -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/migration_state.py scripts/full_migrate.py tests/test_migration_state.py
git commit -m "feat: implement --verify mode with state comparison"
```

---

## Task 11: Integration Test — Full State Round-Trip

**Files:**
- Modify: `tests/test_full_migrate.py`

- [ ] **Step 1: Write integration test**

```python
# Append to tests/test_full_migrate.py

class StateRoundTripTest(unittest.TestCase):
    """Verify that a full run produces .migration-state.json with expected structure."""

    def setUp(self):
        self.repo_root = self.make_repo_root()
        self.source_dir = self.make_source_repo_with_compose()

    def make_repo_root(self):
        """Create minimal monorepo structure. (Copy from existing test helper.)"""
        tmpdir = tempfile.mkdtemp()
        registry = Path(tmpdir) / "registry" / "repos"
        registry.mkdir(parents=True)
        (registry / "index.json").write_text("[]", encoding="utf-8")
        (Path(tmpdir) / "apps").mkdir()
        return tmpdir

    def make_source_repo_with_compose(self):
        """Create source repo with compose file. (Copy from existing test helper.)"""
        src = tempfile.mkdtemp()
        (Path(src) / "docker-compose.yml").write_text(
            "services:\n  web:\n    image: nginx:latest\n    ports:\n      - '8080:80'\n",
            encoding="utf-8",
        )
        (Path(src) / "README.md").write_text("# Test App\nA test application.\n", encoding="utf-8")
        return src

    def tearDown(self):
        import shutil
        shutil.rmtree(self.repo_root, ignore_errors=True)
        shutil.rmtree(self.source_dir, ignore_errors=True)

    def test_full_run_creates_state_file(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), self.source_dir,
             "--repo-root", self.repo_root, "--no-build"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-500:])

        # Find state file
        app_dirs = [d for d in (Path(self.repo_root) / "apps").iterdir() if d.is_dir()]
        self.assertGreater(len(app_dirs), 0, "No app directory created")

        state_path = app_dirs[0] / ".migration-state.json"
        self.assertTrue(state_path.exists(), f"No state file at {state_path}")

        state = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(state["schema_version"], 1)
        self.assertIn("context", state)
        self.assertIn("source", state["context"])
        self.assertIn("route_decision", state["context"])
        self.assertIn("finalized", state["context"])

        # Steps 1-7 should be completed (no-build stops at preflight)
        for step_num in ["1", "2", "3", "4", "5", "6", "7"]:
            self.assertIn(step_num, state["steps"], f"Step {step_num} missing")
            self.assertTrue(state["steps"][step_num]["completed"], f"Step {step_num} not completed")

    def test_second_run_reuses_state(self):
        """Running twice without --force should skip analysis steps."""
        # First run
        subprocess.run(
            [sys.executable, str(SCRIPT), self.source_dir,
             "--repo-root", self.repo_root, "--no-build"],
            capture_output=True, text=True,
        )
        # Second run
        result2 = subprocess.run(
            [sys.executable, str(SCRIPT), self.source_dir,
             "--repo-root", self.repo_root, "--no-build"],
            capture_output=True, text=True,
        )
        self.assertEqual(result2.returncode, 0)
        # Should see "Skipped" messages in output
        self.assertIn("Skipped", result2.stdout + result2.stderr)
```

- [ ] **Step 2: Run integration tests**

Run: `python3 -m pytest tests/test_full_migrate.py::StateRoundTripTest -v`
Expected: All PASS

- [ ] **Step 3: Run full test suite**

Run: `python3 -m pytest tests/ -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_full_migrate.py
git commit -m "test: add integration tests for state round-trip and resume"
```

---

## Task 12: Update SKILL.md and CLAUDE.md

**Files:**
- Modify: `skills/lazycat-migrate/SKILL.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update SKILL.md CLI reference**

In `skills/lazycat-migrate/SKILL.md`, update the "主入口" section to include new flags:

```markdown
- `python3 scripts/full_migrate.py <upstream> [--repo-root <path>] [--force] [--no-build] [--build-mode auto|build|install|reinstall|validate-only] [--resume] [--resume-from N] [--verify]`
  全量 10 步 SOP 自动化入口。`--resume` 从最后完成步骤继续，`--resume-from N` 从第 N 步开始，`--verify` 从零复现验证。每步产出写入 `apps/<slug>/.migration-state.json`。
```

- [ ] **Step 2: Add state file to CLAUDE.md per-app files table**

In `CLAUDE.md`, under "Per-App Required Files" or "Auto-generated during build", add:

```markdown
| `.migration-state.json` | Migration state: structured decisions, problems, verification results |
```

- [ ] **Step 3: Update SKILL.md standard output template**

In the "标准输出模板" section, add a note:

```markdown
每步执行完毕后，结构化数据自动写入 `apps/<slug>/.migration-state.json`。汇报格式不变，但 state 文件包含完整可机读数据。
```

- [ ] **Step 4: Commit**

```bash
git add skills/lazycat-migrate/SKILL.md CLAUDE.md
git commit -m "docs: update SKILL.md and CLAUDE.md with state file references"
```

---

## Summary

| Task | What it delivers | Tests |
|------|-----------------|-------|
| 1 | `migration_state.py` core: new/save/load | 4 unit tests |
| 2 | Step query functions | 7 unit tests |
| 3 | Problem tracking lifecycle | 5 unit tests |
| 4 | Serialization helpers | 7 unit tests |
| 5 | MigrationProblem + find_state_by_source | 3 unit tests |
| 6 | CLI args: --resume, --resume-from, --verify | 3 unit tests |
| 7 | State integration: Steps 1-3 | Existing tests pass |
| 8 | State integration: Steps 4-10 | Existing tests pass |
| 9 | Resume step skip logic | 1 integration test |
| 10 | --verify mode | 2 unit tests |
| 11 | Full round-trip integration test | 2 integration tests |
| 12 | Documentation updates | N/A |

**Phases covered:** 1 (state layer), 2 (structured output + resume), 3 (problem tracking), 4 (verify).

**Follow-up plan needed for:** Phase 5 (--verify-all + --stats), Phase 6 (pattern library), Phase 7 (new file scanners).
