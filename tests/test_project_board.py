from __future__ import annotations

import argparse
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import project_board


class FakeRun:
    """Drop-in for subprocess.run that pops responses from a queue.

    Each entry is either a dict (encoded as JSON stdout, returncode=0) or a
    tuple (returncode, stdout, stderr).
    """

    def __init__(self, responses: list) -> None:
        self.responses = list(responses)
        self.calls: list[list[str]] = []

    def __call__(self, cmd, **kwargs):  # noqa: ANN001 - signature matches subprocess.run
        self.calls.append(list(cmd))
        if not self.responses:
            raise AssertionError(f"Unexpected gh call: {cmd}")
        item = self.responses.pop(0)
        if isinstance(item, dict):
            stdout = json.dumps({"data": item})
            rc, stderr = 0, ""
        elif isinstance(item, tuple):
            rc, stdout, stderr = item
        else:
            raise AssertionError(f"Bad fake response {item!r}")

        class _Result:
            def __init__(self, returncode, stdout, stderr):
                self.returncode = returncode
                self.stdout = stdout
                self.stderr = stderr

        return _Result(rc, stdout, stderr)


def _ns(repo_root: Path, **extra) -> argparse.Namespace:
    base = {"repo_root": str(repo_root)}
    base.update(extra)
    return argparse.Namespace(**base)


def _seed_cache(repo_root: Path) -> None:
    cache = {
        "project": {
            "owner": "CodeEagle",
            "owner_id": "U_kgDO",
            "owner_type": "user",
            "project_id": "PVT_kw1",
            "project_number": 1,
            "project_title": "Migration Queue",
        },
        "fields": {
            "Status": {
                "id": "F_status",
                "name": "Status",
                "data_type": "SINGLE_SELECT",
                "options": {
                    "Inbox": "opt_inbox",
                    "Approved": "opt_approved",
                    "In-Progress": "opt_inprog",
                    "Browser-Test": "opt_browser",
                    "Awaiting-Human": "opt_human",
                    "Published": "opt_published",
                    "Blocked": "opt_blocked",
                    "Filtered": "opt_filtered",
                },
            },
            "Slug": {"id": "F_slug", "name": "Slug", "data_type": "TEXT"},
            "Upstream": {"id": "F_upstream", "name": "Upstream", "data_type": "TEXT"},
            "Build Strategy": {
                "id": "F_strategy",
                "name": "Build Strategy",
                "data_type": "SINGLE_SELECT",
                "options": {
                    "official_image": "opt_off",
                    "upstream_dockerfile": "opt_up",
                    "target_repo_dockerfile": "opt_target",
                    "upstream_with_target_template": "opt_uptmpl",
                    "precompiled_binary": "opt_precom",
                },
            },
            "AI Score": {"id": "F_ai", "name": "AI Score", "data_type": "NUMBER"},
            "Branch": {"id": "F_branch", "name": "Branch", "data_type": "TEXT"},
            "PR": {"id": "F_pr", "name": "PR", "data_type": "TEXT"},
            "Last Run": {"id": "F_run", "name": "Last Run", "data_type": "DATE"},
            "Failures": {"id": "F_fail", "name": "Failures", "data_type": "TEXT"},
            "Codex Attempts": {"id": "F_attempts", "name": "Codex Attempts", "data_type": "NUMBER"},
        },
    }
    project_board.save_cache(repo_root, cache)


def _items_page(items: list[dict], end: bool = True) -> dict:
    return {
        "node": {
            "items": {
                "pageInfo": {"hasNextPage": not end, "endCursor": "" if end else "next"},
                "nodes": items,
            }
        }
    }


def _item_node(item_id: str, fields: dict[str, object], archived: bool = False) -> dict:
    field_value_nodes: list[dict] = []
    for label, value in fields.items():
        fid = f"F_{label.lower().replace(' ', '_')}"
        common = {"field": {"id": fid, "name": label}}
        if isinstance(value, dict) and "name" in value:
            field_value_nodes.append({**common, "name": value["name"], "optionId": value.get("optionId", "")})
        elif isinstance(value, (int, float)):
            field_value_nodes.append({**common, "number": value})
        elif isinstance(value, str) and value.startswith("date:"):
            field_value_nodes.append({**common, "date": value[len("date:"):]})
        else:
            field_value_nodes.append({**common, "text": value})
    return {"id": item_id, "isArchived": archived, "fieldValues": {"nodes": field_value_nodes}}


# -----------------------------------------------------------------------------


class GraphQLHelpersTest(unittest.TestCase):
    def test_gh_graphql_passes_string_and_numeric_variables(self) -> None:
        fake = FakeRun([{"ok": True}])
        with patch.object(project_board.subprocess, "run", fake):
            data = project_board.gh_graphql("query", {"login": "CodeEagle", "limit": 50, "flag": True})
        self.assertEqual(data, {"ok": True})
        cmd = fake.calls[0]
        self.assertIn("graphql", cmd)
        # string -> -f, numeric/bool -> -F
        self.assertIn("-f", cmd)
        self.assertIn("login=CodeEagle", cmd)
        self.assertIn("limit=50", cmd)
        self.assertIn("flag=true", cmd)

    def test_gh_graphql_retries_on_rate_limited(self) -> None:
        fake = FakeRun([
            (1, "", "RATE_LIMITED: secondary rate limit"),
            {"final": True},
        ])
        with patch.object(project_board.subprocess, "run", fake), patch.object(project_board.time, "sleep") as sleep:
            data = project_board.gh_graphql("query")
        self.assertEqual(data, {"final": True})
        self.assertEqual(sleep.call_count, 1)

    def test_gh_graphql_raises_on_graphql_errors(self) -> None:
        fake = FakeRun([
            (0, json.dumps({"errors": [{"message": "boom", "type": "FORBIDDEN"}]}), ""),
        ])
        with patch.object(project_board.subprocess, "run", fake):
            with self.assertRaises(project_board.GraphQLError):
                project_board.gh_graphql("query")


class BootstrapTest(unittest.TestCase):
    def test_bootstrap_creates_project_and_all_fields_when_none_exist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "project-config.json").write_text(
                json.dumps({"project_board": {"owner": "CodeEagle", "repo": "lzcat-apps"}}),
                encoding="utf-8",
            )

            field_count = len(project_board.FIELD_SCHEMA)
            responses: list = [
                # lookup_owner: user query succeeds
                {"user": {"id": "U_owner", "login": "CodeEagle"}},
                # find_project — empty user.projectsV2, single page
                {"user": {"projectsV2": {"pageInfo": {"hasNextPage": False, "endCursor": ""}, "nodes": []}}},
                # create_project
                {"createProjectV2": {"projectV2": {"id": "PVT_new", "number": 7, "title": "Migration Queue"}}},
                # list_project_fields — empty, single page
                {"node": {"fields": {"pageInfo": {"hasNextPage": False, "endCursor": ""}, "nodes": []}}},
            ]
            # one createProjectV2Field response per schema field
            for key, label, dtype, options in project_board.FIELD_SCHEMA:
                node = {"id": f"F_{key}", "name": label, "dataType": dtype}
                if dtype == "SINGLE_SELECT":
                    node["options"] = [{"id": f"opt_{i}", "name": opt} for i, opt in enumerate(options)]
                responses.append({"createProjectV2Field": {"projectV2Field": node}})

            fake = FakeRun(responses)
            buf = io.StringIO()
            with patch.object(project_board.subprocess, "run", fake), redirect_stdout(buf):
                rc = project_board.cmd_bootstrap(_ns(root))
            self.assertEqual(rc, 0)
            summary = json.loads(buf.getvalue())
            self.assertTrue(summary["created_project"])
            self.assertEqual(len(summary["created_fields"]), field_count)

            cache = project_board.load_cache(root)
            self.assertEqual(cache["project"]["project_id"], "PVT_new")
            self.assertEqual(cache["project"]["project_number"], 7)
            self.assertIn("Status", cache["fields"])
            self.assertEqual(cache["fields"]["Status"]["options"]["Inbox"], "opt_0")

            # project-config.json was updated with the new project_number
            updated = json.loads((root / "project-config.json").read_text())
            self.assertEqual(updated["project_board"]["project_number"], 7)

    def test_bootstrap_reuses_existing_project_and_skips_existing_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "project-config.json").write_text(
                json.dumps({
                    "project_board": {
                        "owner": "CodeEagle",
                        "repo": "lzcat-apps",
                        "project_number": 3,
                        "project_title": "Migration Queue",
                    }
                }),
                encoding="utf-8",
            )

            existing_fields_nodes = []
            for key, label, dtype, options in project_board.FIELD_SCHEMA:
                node = {"id": f"F_{key}", "name": label, "dataType": dtype}
                if dtype == "SINGLE_SELECT":
                    node["options"] = [{"id": f"opt_{i}", "name": opt} for i, opt in enumerate(options)]
                existing_fields_nodes.append(node)

            responses: list = [
                {"user": {"id": "U_owner", "login": "CodeEagle"}},
                {"user": {"projectsV2": {
                    "pageInfo": {"hasNextPage": False, "endCursor": ""},
                    "nodes": [{"id": "PVT_existing", "number": 3, "title": "Migration Queue", "closed": False}],
                }}},
                {"node": {"fields": {"pageInfo": {"hasNextPage": False, "endCursor": ""}, "nodes": existing_fields_nodes}}},
            ]
            fake = FakeRun(responses)
            with patch.object(project_board.subprocess, "run", fake), redirect_stdout(io.StringIO()) as buf:
                rc = project_board.cmd_bootstrap(_ns(root))
            self.assertEqual(rc, 0)
            summary = json.loads(buf.getvalue())
            self.assertFalse(summary["created_project"])
            self.assertEqual(summary["created_fields"], [])
            cache = project_board.load_cache(root)
            self.assertEqual(cache["project"]["project_id"], "PVT_existing")


    def test_lookup_owner_falls_back_to_organization(self) -> None:
        responses = [
            (1, json.dumps({"errors": [{"message": "no user", "type": "NOT_FOUND"}]}), "no user"),
            {"organization": {"id": "O_org", "login": "ExampleOrg"}},
        ]
        fake = FakeRun(responses)
        with patch.object(project_board.subprocess, "run", fake):
            owner = project_board.lookup_owner("ExampleOrg")
        self.assertEqual(owner, {"id": "O_org", "type": "organization", "login": "ExampleOrg"})


class SyncTest(unittest.TestCase):
    def _setup(self, queue: dict, *, exclude: list[str] | None = None, threshold: float | None = None) -> Path:
        root = Path(tempfile.mkdtemp(prefix="pb-sync-"))
        _seed_cache(root)
        (root / "registry" / "auto-migration").mkdir(parents=True, exist_ok=True)
        (root / "registry" / "auto-migration" / "queue.json").write_text(
            json.dumps(queue), encoding="utf-8",
        )
        if exclude is not None:
            (root / "registry" / "auto-migration" / "exclude-list.json").write_text(
                json.dumps({"slugs": exclude}), encoding="utf-8",
            )
        config: dict = {"project_board": {"owner": "CodeEagle", "project_number": 1}}
        if threshold is not None:
            config["migration"] = {"auto_approve_score_threshold": threshold}
        (root / "project-config.json").write_text(json.dumps(config), encoding="utf-8")
        return root

    def test_sync_creates_inbox_item_for_new_slug(self) -> None:
        queue = {
            "items": [
                {
                    "id": "github:owner/demo",
                    "slug": "demo",
                    "state": "ready",
                    "candidate": {"repo_url": "https://github.com/owner/demo", "build_strategy": "official_image"},
                    "discovery_review": {"score": 0.5, "status": "migrate"},
                }
            ]
        }
        root = self._setup(queue)
        responses: list = [
            # _ensure_item -> find_item_by_slug -> list_project_items (empty)
            _items_page([]),
            # add_item
            {"addProjectV2DraftIssue": {"projectItem": {"id": "PVTI_new"}}},
            # set Slug
            {"updateProjectV2ItemFieldValue": {"projectV2Item": {"id": "PVTI_new"}}},
            # set Status=Inbox
            {"updateProjectV2ItemFieldValue": {"projectV2Item": {"id": "PVTI_new"}}},
            # set Upstream
            {"updateProjectV2ItemFieldValue": {"projectV2Item": {"id": "PVTI_new"}}},
            # set Build Strategy
            {"updateProjectV2ItemFieldValue": {"projectV2Item": {"id": "PVTI_new"}}},
            # set AI Score
            {"updateProjectV2ItemFieldValue": {"projectV2Item": {"id": "PVTI_new"}}},
        ]
        fake = FakeRun(responses)
        buf = io.StringIO()
        with patch.object(project_board.subprocess, "run", fake), redirect_stdout(buf):
            rc = project_board.cmd_sync(_ns(root))
        self.assertEqual(rc, 0)
        summary = json.loads(buf.getvalue())
        self.assertEqual(summary["created"], ["demo"])
        self.assertEqual(summary["approved"], [])

    def test_sync_promotes_inbox_to_approved_when_score_meets_threshold(self) -> None:
        queue = {
            "items": [
                {
                    "id": "github:owner/demo",
                    "slug": "demo",
                    "state": "ready",
                    "candidate": {"repo_url": "https://github.com/owner/demo"},
                    "discovery_review": {"score": 0.85, "status": "migrate"},
                }
            ]
        }
        root = self._setup(queue, threshold=0.8)
        existing = _item_node(
            "PVTI_demo",
            {
                "Slug": "demo",
                "Status": {"name": "Inbox", "optionId": "opt_inbox"},
                "Upstream": "https://github.com/owner/demo",
                "AI Score": 0.85,
            },
        )
        responses: list = [
            _items_page([existing]),  # find_item_by_slug
            {"updateProjectV2ItemFieldValue": {"projectV2Item": {"id": "PVTI_demo"}}},  # set Status=Approved
        ]
        fake = FakeRun(responses)
        buf = io.StringIO()
        with patch.object(project_board.subprocess, "run", fake), redirect_stdout(buf):
            rc = project_board.cmd_sync(_ns(root))
        self.assertEqual(rc, 0)
        summary = json.loads(buf.getvalue())
        self.assertEqual(summary["approved"], ["demo"])

    def test_sync_does_not_demote_in_progress_item(self) -> None:
        queue = {
            "items": [
                {
                    "id": "github:owner/demo",
                    "slug": "demo",
                    "state": "ready",
                    "candidate": {"repo_url": "https://github.com/owner/demo"},
                    "discovery_review": {"score": 0.95, "status": "migrate"},
                }
            ]
        }
        root = self._setup(queue, threshold=0.8)
        existing = _item_node(
            "PVTI_demo",
            {
                "Slug": "demo",
                "Status": {"name": "In-Progress", "optionId": "opt_inprog"},
                "Upstream": "https://github.com/owner/demo",
                "AI Score": 0.95,
            },
        )
        fake = FakeRun([_items_page([existing])])  # only one lookup, no mutations
        buf = io.StringIO()
        with patch.object(project_board.subprocess, "run", fake), redirect_stdout(buf):
            rc = project_board.cmd_sync(_ns(root))
        self.assertEqual(rc, 0)
        summary = json.loads(buf.getvalue())
        self.assertEqual(summary["approved"], [])
        self.assertIn("demo", summary["updated"])

    def test_sync_skips_excluded_slug_not_yet_on_board(self) -> None:
        queue = {
            "items": [
                {
                    "id": "github:owner/codex-web",
                    "slug": "codex-web",
                    "state": "ready",
                    "candidate": {"repo_url": "https://github.com/owner/codex-web"},
                }
            ]
        }
        root = self._setup(queue, exclude=["codex-web"])
        # Excluded not yet on board: only the find_item_by_slug list call.
        responses: list = [_items_page([])]
        fake = FakeRun(responses)
        buf = io.StringIO()
        with patch.object(project_board.subprocess, "run", fake), redirect_stdout(buf):
            rc = project_board.cmd_sync(_ns(root))
        self.assertEqual(rc, 0)
        summary = json.loads(buf.getvalue())
        self.assertEqual(summary["filtered_excluded"], ["codex-web"])
        self.assertEqual(summary["created"], [])

    def test_sync_marks_excluded_slug_filtered_when_already_on_board(self) -> None:
        queue = {
            "items": [
                {
                    "id": "github:owner/codex-web",
                    "slug": "codex-web",
                    "state": "ready",
                    "candidate": {"repo_url": "https://github.com/owner/codex-web"},
                }
            ]
        }
        root = self._setup(queue, exclude=["codex-web"])
        existing = _item_node(
            "PVTI_x",
            {"Slug": "codex-web", "Status": {"name": "Inbox", "optionId": "opt_inbox"}},
        )
        responses: list = [
            _items_page([existing]),  # find_item_by_slug
            {"updateProjectV2ItemFieldValue": {"projectV2Item": {"id": "PVTI_x"}}},  # Status=Filtered
        ]
        fake = FakeRun(responses)
        buf = io.StringIO()
        with patch.object(project_board.subprocess, "run", fake), redirect_stdout(buf):
            rc = project_board.cmd_sync(_ns(root))
        self.assertEqual(rc, 0)
        summary = json.loads(buf.getvalue())
        self.assertEqual(summary["filtered_excluded"], ["codex-web"])


class ListApprovedTest(unittest.TestCase):
    def test_list_approved_emits_oldest_last_run_first(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_cache(root)
            items = [
                _item_node("PVTI_a", {"Slug": "alpha", "Status": {"name": "Approved"}, "Last Run": "date:2026-05-04"}),
                _item_node("PVTI_b", {"Slug": "bravo", "Status": {"name": "Approved"}, "Last Run": "date:2026-05-01"}),
                _item_node("PVTI_c", {"Slug": "charlie", "Status": {"name": "Inbox"}}),
            ]
            fake = FakeRun([_items_page(items)])
            buf = io.StringIO()
            with patch.object(project_board.subprocess, "run", fake), redirect_stdout(buf):
                rc = project_board.cmd_list_approved(_ns(root, limit=2, format="json"))
            self.assertEqual(rc, 0)
            self.assertEqual(json.loads(buf.getvalue()), ["bravo", "alpha"])


class ReadUpdateUpsertArchiveTest(unittest.TestCase):
    def _setup(self) -> Path:
        root = Path(tempfile.mkdtemp(prefix="pb-cmd-"))
        _seed_cache(root)
        return root

    def test_read_returns_full_field_map(self) -> None:
        root = self._setup()
        existing = _item_node(
            "PVTI_demo",
            {"Slug": "demo", "Status": {"name": "Inbox", "optionId": "opt_inbox"}, "AI Score": 0.7},
        )
        fake = FakeRun([_items_page([existing])])
        buf = io.StringIO()
        with patch.object(project_board.subprocess, "run", fake), redirect_stdout(buf):
            rc = project_board.cmd_read(_ns(root, slug="demo", field=None))
        self.assertEqual(rc, 0)
        flat = json.loads(buf.getvalue())
        self.assertEqual(flat["Slug"], "demo")
        self.assertEqual(flat["AI Score"], 0.7)

    def test_read_returns_single_field_when_requested(self) -> None:
        root = self._setup()
        existing = _item_node(
            "PVTI_demo",
            {"Slug": "demo", "Status": {"name": "Approved", "optionId": "opt_approved"}},
        )
        fake = FakeRun([_items_page([existing])])
        buf = io.StringIO()
        with patch.object(project_board.subprocess, "run", fake), redirect_stdout(buf):
            rc = project_board.cmd_read(_ns(root, slug="demo", field="Status"))
        self.assertEqual(rc, 0)
        self.assertEqual(buf.getvalue().strip(), "Approved")

    def test_update_status_and_extra_field(self) -> None:
        root = self._setup()
        existing = _item_node("PVTI_demo", {"Slug": "demo", "Status": {"name": "Inbox", "optionId": "opt_inbox"}})
        responses: list = [
            _items_page([existing]),
            {"updateProjectV2ItemFieldValue": {"projectV2Item": {"id": "PVTI_demo"}}},  # Status
            {"updateProjectV2ItemFieldValue": {"projectV2Item": {"id": "PVTI_demo"}}},  # Failures
        ]
        fake = FakeRun(responses)
        buf = io.StringIO()
        with patch.object(project_board.subprocess, "run", fake), redirect_stdout(buf):
            rc = project_board.cmd_update(
                _ns(root, slug="demo", status="In-Progress", field=["Failures=build retry 1"]),
            )
        self.assertEqual(rc, 0)
        # Verify the Status mutation used the right optionId
        status_call = fake.calls[1]
        self.assertIn("optionId=opt_inprog", status_call)

    def test_update_unknown_slug_returns_error(self) -> None:
        root = self._setup()
        fake = FakeRun([_items_page([])])
        buf = io.StringIO()
        with patch.object(project_board.subprocess, "run", fake), redirect_stdout(buf):
            rc = project_board.cmd_update(_ns(root, slug="missing", status="Inbox", field=[]))
        self.assertEqual(rc, 1)
        self.assertIn("error", json.loads(buf.getvalue()))

    def test_upsert_creates_then_updates(self) -> None:
        root = self._setup()
        responses: list = [
            _items_page([]),  # find_item_by_slug -> empty
            {"addProjectV2DraftIssue": {"projectItem": {"id": "PVTI_new"}}},
            {"updateProjectV2ItemFieldValue": {"projectV2Item": {"id": "PVTI_new"}}},  # Slug
            {"updateProjectV2ItemFieldValue": {"projectV2Item": {"id": "PVTI_new"}}},  # Status=Inbox
            {"updateProjectV2ItemFieldValue": {"projectV2Item": {"id": "PVTI_new"}}},  # Upstream
            {"updateProjectV2ItemFieldValue": {"projectV2Item": {"id": "PVTI_new"}}},  # Strategy
            {"updateProjectV2ItemFieldValue": {"projectV2Item": {"id": "PVTI_new"}}},  # AI Score
        ]
        fake = FakeRun(responses)
        buf = io.StringIO()
        with patch.object(project_board.subprocess, "run", fake), redirect_stdout(buf):
            rc = project_board.cmd_upsert(
                _ns(
                    root,
                    slug="demo",
                    upstream="https://github.com/owner/demo",
                    strategy="official_image",
                    score=0.9,
                ),
            )
        self.assertEqual(rc, 0)
        out = json.loads(buf.getvalue())
        self.assertTrue(out["created"])

    def test_archive_sets_terminal_status_then_archives(self) -> None:
        root = self._setup()
        existing = _item_node("PVTI_demo", {"Slug": "demo", "Status": {"name": "Awaiting-Human"}})
        responses: list = [
            _items_page([existing]),
            {"updateProjectV2ItemFieldValue": {"projectV2Item": {"id": "PVTI_demo"}}},  # Status=Published
            {"archiveProjectV2Item": {"item": {"id": "PVTI_demo"}}},
        ]
        fake = FakeRun(responses)
        buf = io.StringIO()
        with patch.object(project_board.subprocess, "run", fake), redirect_stdout(buf):
            rc = project_board.cmd_archive(_ns(root, slug="demo", status="Published"))
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(buf.getvalue())["archived"], True)


class ConfigHelpersTest(unittest.TestCase):
    def test_auto_approve_threshold_falls_back_to_default(self) -> None:
        self.assertEqual(project_board.auto_approve_threshold({}), project_board.DEFAULT_AUTO_APPROVE_THRESHOLD)

    def test_auto_approve_threshold_reads_migration_config(self) -> None:
        self.assertEqual(
            project_board.auto_approve_threshold({"migration": {"auto_approve_score_threshold": 0.65}}),
            0.65,
        )

    def test_load_exclude_slugs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "registry" / "auto-migration").mkdir(parents=True)
            (root / "registry" / "auto-migration" / "exclude-list.json").write_text(
                json.dumps({"slugs": ["codex-web", "  ", "demo"]}), encoding="utf-8",
            )
            self.assertEqual(project_board.load_exclude_slugs(root), {"codex-web", "demo"})

    def test_queue_item_score_handles_missing_or_bad(self) -> None:
        self.assertIsNone(project_board.queue_item_score({}))
        self.assertIsNone(project_board.queue_item_score({"discovery_review": {"score": "nope"}}))
        self.assertEqual(project_board.queue_item_score({"discovery_review": {"score": 0.42}}), 0.42)


if __name__ == "__main__":
    unittest.main()
