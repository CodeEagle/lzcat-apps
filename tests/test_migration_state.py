"""Comprehensive tests for migration_state module."""

import json
import shutil
import sys
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import migration_state as ms


class NewEmptyStateTest(unittest.TestCase):
    def test_creates_state_with_schema_version_and_source(self):
        state = ms.new_empty_state("https://github.com/owner/repo")
        self.assertEqual(state["schema_version"], 1)
        self.assertEqual(state["source_input"], "https://github.com/owner/repo")
        self.assertIn("created_at", state)
        self.assertIn("updated_at", state)
        self.assertEqual(state["context"], {})
        self.assertEqual(state["steps"], {})
        self.assertEqual(state["problems"], [])
        self.assertEqual(state["verification"], {})


class SaveLoadStateTest(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    def test_save_creates_file_and_load_reads_it(self):
        state = ms.new_empty_state("source-a")
        ms.save_state(self.tmp_dir, state)

        loaded = ms.load_state(self.tmp_dir)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["source_input"], "source-a")
        self.assertEqual(loaded["schema_version"], 1)

    def test_load_returns_none_when_no_file(self):
        result = ms.load_state(self.tmp_dir)
        self.assertIsNone(result)

    def test_save_is_atomic_no_tmp_remains(self):
        state = ms.new_empty_state("source-b")
        ms.save_state(self.tmp_dir, state)

        files = list(self.tmp_dir.iterdir())
        names = [f.name for f in files]
        self.assertIn(ms.STATE_FILENAME, names)
        self.assertNotIn(ms.STATE_FILENAME.replace(".json", ".tmp"), names)
        # No .tmp file should remain
        tmp_files = [f for f in files if f.suffix == ".tmp"]
        self.assertEqual(len(tmp_files), 0)


class StepQueryTest(unittest.TestCase):
    def test_get_last_completed_step_returns_highest(self):
        state = ms.new_empty_state("x")
        ms.mark_step_completed(state, 1, conclusion="done")
        ms.mark_step_completed(state, 3, conclusion="done")
        self.assertEqual(ms.get_last_completed_step(state), 3)

    def test_get_last_completed_step_returns_zero_when_none(self):
        state = ms.new_empty_state("x")
        self.assertEqual(ms.get_last_completed_step(state), 0)

    def test_should_skip_step_true_when_completed(self):
        state = ms.new_empty_state("x")
        ms.mark_step_completed(state, 2, conclusion="ok")
        self.assertTrue(ms.should_skip_step(state, 2))

    def test_should_skip_step_false_when_not_completed(self):
        state = ms.new_empty_state("x")
        state["steps"]["2"] = {"completed": False}
        self.assertFalse(ms.should_skip_step(state, 2))

    def test_should_skip_step_false_when_missing(self):
        state = ms.new_empty_state("x")
        self.assertFalse(ms.should_skip_step(state, 99))

    def test_mark_step_completed(self):
        state = ms.new_empty_state("x")
        ms.mark_step_completed(state, 5, conclusion="all good")
        step = state["steps"]["5"]
        self.assertTrue(step["completed"])
        self.assertEqual(step["conclusion"], "all good")
        self.assertIn("completed_at", step)

    def test_mark_step_completed_with_extra_data(self):
        state = ms.new_empty_state("x")
        ms.mark_step_completed(state, 1, conclusion="ok", artifact="foo.lpk", size=42)
        step = state["steps"]["1"]
        self.assertEqual(step["artifact"], "foo.lpk")
        self.assertEqual(step["size"], 42)


class ProblemTrackingTest(unittest.TestCase):
    def test_add_problem_returns_id_and_appends(self):
        state = ms.new_empty_state("x")
        pid = ms.add_problem(state, 2, "port conflict", "networking")
        self.assertEqual(pid, "p1")
        self.assertEqual(len(state["problems"]), 1)
        self.assertEqual(state["problems"][0]["status"], "open")
        self.assertEqual(state["problems"][0]["category"], "networking")

    def test_add_multiple_problems_increments_id(self):
        state = ms.new_empty_state("x")
        p1 = ms.add_problem(state, 1, "issue a", "cat-a")
        p2 = ms.add_problem(state, 2, "issue b", "cat-b")
        p3 = ms.add_problem(state, 3, "issue c", "cat-c")
        self.assertEqual(p1, "p1")
        self.assertEqual(p2, "p2")
        self.assertEqual(p3, "p3")

    def test_resolve_problem(self):
        state = ms.new_empty_state("x")
        pid = ms.add_problem(state, 1, "broken", "build")
        ms.resolve_problem(state, pid, "fixed Dockerfile")
        problem = state["problems"][0]
        self.assertEqual(problem["status"], "resolved")
        self.assertEqual(problem["resolution"], "fixed Dockerfile")
        self.assertIn("resolved_at", problem)

        # ValueError for missing id
        with self.assertRaises(ValueError):
            ms.resolve_problem(state, "p999", "nope")

    def test_get_pending_backports(self):
        state = ms.new_empty_state("x")
        p1 = ms.add_problem(state, 1, "a", "cat")
        p2 = ms.add_problem(state, 2, "b", "cat")
        p3 = ms.add_problem(state, 3, "c", "cat")

        # p1 resolved, no backport -> pending
        ms.resolve_problem(state, p1, "fix a")
        # p2 resolved with backport committed=False -> pending
        ms.resolve_problem(state, p2, "fix b")
        state["problems"][1]["backport"] = {"committed": False}
        # p3 still open -> not pending

        pending = ms.get_pending_backports(state)
        ids = [p["id"] for p in pending]
        self.assertIn("p1", ids)
        self.assertIn("p2", ids)
        self.assertNotIn("p3", ids)

    def test_mark_backported(self):
        state = ms.new_empty_state("x")
        pid = ms.add_problem(state, 1, "issue", "cat")
        ms.resolve_problem(state, pid, "fixed")
        ms.mark_backported(state, pid, "upstream/main", "cherry-pick abc123")

        problem = state["problems"][0]
        self.assertEqual(problem["status"], "backported")
        self.assertTrue(problem["backport"]["committed"])
        self.assertEqual(problem["backport"]["target"], "upstream/main")
        self.assertEqual(problem["backport"]["description"], "cherry-pick abc123")


class SerializationTest(unittest.TestCase):
    def test_serialize_path_relative(self):
        repo_root = Path("/home/user/project")
        p = Path("/home/user/project/apps/foo/icon.png")
        result = ms.serialize_path(p, repo_root)
        self.assertEqual(result, "apps/foo/icon.png")

    def test_serialize_path_none(self):
        self.assertIsNone(ms.serialize_path(None, Path("/root")))

    def test_serialize_paths_list(self):
        repo_root = Path("/repo")
        paths = [Path("/repo/a.txt"), Path("/repo/b/c.txt")]
        result = ms.serialize_paths(paths, repo_root)
        self.assertEqual(result, ["a.txt", "b/c.txt"])

    def test_serialize_set_to_sorted_list(self):
        result = ms.serialize_set({"c", "a", "b"})
        self.assertEqual(result, ["a", "b", "c"])

    def test_serialize_set_none(self):
        self.assertEqual(ms.serialize_set(None), [])

    def test_serialize_dataclass(self):
        @dataclass
        class Config:
            name: str
            path: Path
            count: int

        obj = Config(name="test", path=Path("/foo/bar"), count=3)
        result = ms.serialize_dataclass(obj)
        self.assertEqual(result, {"name": "test", "path": "/foo/bar", "count": 3})

    def test_full_round_trip_with_paths(self):
        @dataclass
        class Inner:
            file: Path

        @dataclass
        class Outer:
            name: str
            inner: Inner
            items: list

        obj = Outer(name="app", inner=Inner(file=Path("/a/b")), items=[Path("/c"), "d"])
        result = ms.serialize_dataclass(obj)
        self.assertEqual(result["name"], "app")
        self.assertEqual(result["inner"]["file"], "/a/b")
        self.assertEqual(result["items"], ["/c", "d"])


class MigrationProblemTest(unittest.TestCase):
    def test_exception_carries_category(self):
        exc = ms.MigrationProblem("oops", category="networking", step=3)
        self.assertEqual(str(exc), "oops")
        self.assertEqual(exc.category, "networking")
        self.assertEqual(exc.step, 3)
        self.assertIsInstance(exc, Exception)


class FindStateBySourceTest(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    def test_finds_matching_state(self):
        app_dir = self.tmp_dir / "my-app"
        app_dir.mkdir()
        state = ms.new_empty_state("https://github.com/owner/repo")
        ms.save_state(app_dir, state)

        result = ms.find_state_by_source(self.tmp_dir, "https://github.com/owner/repo")
        self.assertIsNotNone(result)
        found_dir, found_state = result
        self.assertEqual(found_dir, app_dir)
        self.assertEqual(found_state["source_input"], "https://github.com/owner/repo")

    def test_returns_none_when_no_match(self):
        app_dir = self.tmp_dir / "other-app"
        app_dir.mkdir()
        state = ms.new_empty_state("different-source")
        ms.save_state(app_dir, state)

        result = ms.find_state_by_source(self.tmp_dir, "no-match")
        self.assertIsNone(result)


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

    def test_ignores_timestamps(self):
        s1 = ms.new_empty_state("x")
        s2 = ms.new_empty_state("x")
        # Timestamps will differ but should be ignored
        s2["created_at"] = "2099-01-01T00:00:00Z"
        s2["updated_at"] = "2099-01-01T00:00:00Z"
        diffs = ms.compare_states(s1, s2)
        self.assertEqual(len(diffs), 0)

    def test_list_length_mismatch(self):
        s1 = ms.new_empty_state("x")
        s1["context"]["items"] = [1, 2, 3]
        s2 = ms.new_empty_state("x")
        s2["context"]["items"] = [1, 2]
        diffs = ms.compare_states(s1, s2)
        self.assertGreater(len(diffs), 0)


if __name__ == "__main__":
    unittest.main()
