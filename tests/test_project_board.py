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
            self.assertEqual(summary["recreated_fields"], [])
            cache = project_board.load_cache(root)
            self.assertEqual(cache["project"]["project_id"], "PVT_existing")

    def test_bootstrap_updates_built_in_status_field_options(self) -> None:
        # GitHub Projects v2 auto-create a Status field with Todo/In Progress/Done.
        # Status is built-in (cannot delete), so bootstrap must mutate its options
        # in place via updateProjectV2Field.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "project-config.json").write_text(
                json.dumps({"project_board": {"owner": "CodeEagle", "project_number": 1}}),
                encoding="utf-8",
            )

            existing = []
            for key, label, dtype, options in project_board.FIELD_SCHEMA:
                node = {"id": f"F_{key}", "name": label, "dataType": dtype}
                if label == "Status":
                    node["options"] = [
                        {"id": "opt_todo", "name": "Todo"},
                        {"id": "opt_in_progress", "name": "In Progress"},
                        {"id": "opt_done", "name": "Done"},
                    ]
                elif dtype == "SINGLE_SELECT":
                    node["options"] = [{"id": f"opt_{i}", "name": opt} for i, opt in enumerate(options)]
                existing.append(node)

            responses: list = [
                {"user": {"id": "U_owner", "login": "CodeEagle"}},
                {"user": {"projectsV2": {
                    "pageInfo": {"hasNextPage": False, "endCursor": ""},
                    "nodes": [{"id": "PVT_existing", "number": 1, "title": "Migration Queue", "closed": False}],
                }}},
                {"node": {"fields": {"pageInfo": {"hasNextPage": False, "endCursor": ""}, "nodes": existing}}},
                {"updateProjectV2Field": {"projectV2Field": {
                    "id": "F_status",
                    "name": "Status",
                    "dataType": "SINGLE_SELECT",
                    "options": [{"id": f"opt_new_{i}", "name": n}
                                for i, n in enumerate(["Inbox", "Approved", "In-Progress", "Browser-Test",
                                                       "Awaiting-Human", "Published", "Blocked", "Filtered"])],
                }}},
            ]
            fake = FakeRun(responses)
            with patch.object(project_board.subprocess, "run", fake), redirect_stdout(io.StringIO()) as buf:
                rc = project_board.cmd_bootstrap(_ns(root))
            self.assertEqual(rc, 0)
            summary = json.loads(buf.getvalue())
            self.assertEqual(summary["updated_fields"], ["Status"])
            self.assertEqual(summary["created_fields"], [])
            self.assertEqual(summary["recreated_fields"], [])
            cache = project_board.load_cache(root)
            self.assertEqual(cache["fields"]["Status"]["options"]["Inbox"], "opt_new_0")

    def test_bootstrap_recreates_custom_field_with_wrong_options(self) -> None:
        # Custom single-select fields (e.g. Build Strategy) DO support deletion,
        # so bootstrap delete-recreates them when options drift.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "project-config.json").write_text(
                json.dumps({"project_board": {"owner": "CodeEagle", "project_number": 1}}),
                encoding="utf-8",
            )

            existing = []
            for key, label, dtype, options in project_board.FIELD_SCHEMA:
                node = {"id": f"F_{key}", "name": label, "dataType": dtype}
                if label == "Build Strategy":
                    node["options"] = [{"id": "opt_legacy", "name": "legacy_only"}]
                elif dtype == "SINGLE_SELECT":
                    node["options"] = [{"id": f"opt_{i}", "name": opt} for i, opt in enumerate(options)]
                existing.append(node)

            responses: list = [
                {"user": {"id": "U_owner", "login": "CodeEagle"}},
                {"user": {"projectsV2": {
                    "pageInfo": {"hasNextPage": False, "endCursor": ""},
                    "nodes": [{"id": "PVT_existing", "number": 1, "title": "Migration Queue", "closed": False}],
                }}},
                {"node": {"fields": {"pageInfo": {"hasNextPage": False, "endCursor": ""}, "nodes": existing}}},
                {"deleteProjectV2Field": {"projectV2Field": {"id": "F_build_strategy"}}},
                {"createProjectV2Field": {"projectV2Field": {
                    "id": "F_build_strategy_new",
                    "name": "Build Strategy",
                    "dataType": "SINGLE_SELECT",
                    "options": [{"id": f"opt_{i}", "name": n} for i, n in enumerate([
                        "official_image", "upstream_dockerfile", "target_repo_dockerfile",
                        "upstream_with_target_template", "precompiled_binary",
                    ])],
                }}},
            ]
            fake = FakeRun(responses)
            with patch.object(project_board.subprocess, "run", fake), redirect_stdout(io.StringIO()) as buf:
                rc = project_board.cmd_bootstrap(_ns(root))
            self.assertEqual(rc, 0)
            summary = json.loads(buf.getvalue())
            self.assertEqual(summary["recreated_fields"], ["Build Strategy"])
            self.assertEqual(summary["updated_fields"], [])


    def test_lookup_owner_falls_back_to_organization(self) -> None:
        responses = [
            (1, json.dumps({"errors": [{"message": "no user", "type": "NOT_FOUND"}]}), "no user"),
            {"organization": {"id": "O_org", "login": "ExampleOrg"}},
        ]
        fake = FakeRun(responses)
        with patch.object(project_board.subprocess, "run", fake):
            owner = project_board.lookup_owner("ExampleOrg")
        self.assertEqual(owner, {"id": "O_org", "type": "organization", "login": "ExampleOrg"})


class BuildItemIndexTest(unittest.TestCase):
    def test_build_item_index_keys_by_slug(self) -> None:
        items = [
            _item_node("PVTI_a", {"Slug": "alpha", "Status": {"name": "Inbox"}}),
            _item_node("PVTI_b", {"Slug": "bravo", "Status": {"name": "Approved"}}),
            # Item without Slug field — should be skipped.
            _item_node("PVTI_x", {"Status": {"name": "Inbox"}}),
        ]
        fake = FakeRun([_items_page(items)])
        with patch.object(project_board.subprocess, "run", fake):
            index = project_board._build_item_index("PVT_xx")
        self.assertEqual(set(index.keys()), {"alpha", "bravo"})
        node, flat = index["alpha"]
        self.assertEqual(node["id"], "PVTI_a")
        self.assertEqual(flat["Slug"], "alpha")

    def test_sync_calls_list_project_items_only_once_for_many_queue_entries(self) -> None:
        # Performance regression guard: 50 queue items should result in exactly
        # one paginated _build_item_index call, not 50 lookups.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_cache(root)
            (root / "registry" / "auto-migration").mkdir(parents=True, exist_ok=True)
            (root / "registry" / "auto-migration" / "queue.json").write_text(
                json.dumps({"items": [
                    {"id": f"github:demo/{i}", "slug": f"slug-{i}", "state": "ready",
                     "candidate": {"repo_url": f"https://github.com/demo/{i}"}}
                    for i in range(50)
                ]}),
                encoding="utf-8",
            )
            (root / "project-config.json").write_text(
                json.dumps({"project_board": {"owner": "CodeEagle", "project_number": 1}}),
                encoding="utf-8",
            )

            responses: list = [_items_page([])]   # one and only list call
            # Per slug: add_item + Slug + Status=Inbox + Upstream
            # (no Status=Approved — no AI score, so no auto-approve)
            for _ in range(50):
                responses.append({"addProjectV2DraftIssue": {"projectItem": {"id": "PVTI_x"}}})
                responses.extend([
                    {"updateProjectV2ItemFieldValue": {"projectV2Item": {"id": "PVTI_x"}}}
                ] * 3)

            fake = FakeRun(responses)
            buf = io.StringIO()
            with patch.object(project_board.subprocess, "run", fake), redirect_stdout(buf):
                rc = project_board.cmd_sync(_ns(root))
            self.assertEqual(rc, 0)
            list_calls = sum(1 for c in fake.calls if any("PROJECT_ITEMS_BY_SLUG" in p or "items(first:" in p for p in c))
            self.assertLessEqual(list_calls, 1, f"sync triggered {list_calls} list-items calls")


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
                    # Score is below threshold (0.8) so AI says no.
                    "discovery_review": {"score": 0.5, "status": "migrate"},
                }
            ]
        }
        root = self._setup(queue)
        responses: list = [
            # _build_item_index -> list_project_items (empty)
            _items_page([]),
            # add_item
            {"addProjectV2DraftIssue": {"projectItem": {"id": "PVTI_new"}}},
            # set Slug, Status=Inbox, Upstream, Build Strategy, AI Score
            {"updateProjectV2ItemFieldValue": {"projectV2Item": {"id": "PVTI_new"}}},
            {"updateProjectV2ItemFieldValue": {"projectV2Item": {"id": "PVTI_new"}}},
            {"updateProjectV2ItemFieldValue": {"projectV2Item": {"id": "PVTI_new"}}},
            {"updateProjectV2ItemFieldValue": {"projectV2Item": {"id": "PVTI_new"}}},
            {"updateProjectV2ItemFieldValue": {"projectV2Item": {"id": "PVTI_new"}}},
        ]
        fake = FakeRun(responses)
        buf = io.StringIO()
        with patch.object(project_board.subprocess, "run", fake), redirect_stdout(buf):
            rc = project_board.cmd_sync(_ns(root))
        self.assertEqual(rc, 0)
        summary = json.loads(buf.getvalue())
        self.assertEqual(summary["created"], ["demo"])
        # state=ready alone is NOT enough — AI score 0.5 < 0.8 threshold.
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

    def test_sync_does_not_auto_approve_ready_items_without_ai_score(self) -> None:
        # Mechanical state="ready" alone is not enough. AI must score the
        # item past the threshold first; otherwise low-signal repos like
        # personal homepages slip into Approved.
        queue = {
            "items": [
                {
                    "id": "github:owner/demo",
                    "slug": "demo",
                    "state": "ready",
                    "candidate": {"repo_url": "https://github.com/owner/demo"},
                    # No discovery_review.score field at all
                }
            ]
        }
        root = self._setup(queue)
        existing = _item_node(
            "PVTI_demo",
            {
                "Slug": "demo",
                "Status": {"name": "Inbox", "optionId": "opt_inbox"},
                "Upstream": "https://github.com/owner/demo",
            },
        )
        # No mutations — score is missing → no auto-approve, no field changes.
        responses: list = [_items_page([existing])]
        fake = FakeRun(responses)
        buf = io.StringIO()
        with patch.object(project_board.subprocess, "run", fake), redirect_stdout(buf):
            rc = project_board.cmd_sync(_ns(root))
        self.assertEqual(rc, 0)
        summary = json.loads(buf.getvalue())
        self.assertEqual(summary["approved"], [])

    def test_sync_moves_filtered_out_queue_items_to_filtered_status(self) -> None:
        # AI said "skip" → state=filtered_out. Card should slide to the
        # Filtered column automatically so dispatcher / human aren't
        # distracted by dead cards.
        queue = {
            "items": [
                {
                    "id": "github:owner/demo",
                    "slug": "demo",
                    "state": "filtered_out",
                    "filtered_reason": "ai_discovery_skip",
                    "candidate": {"repo_url": "https://github.com/owner/demo"},
                    "discovery_review": {"score": 0.1, "status": "skip"},
                }
            ]
        }
        root = self._setup(queue)
        existing = _item_node(
            "PVTI_demo",
            {
                "Slug": "demo",
                "Status": {"name": "Inbox", "optionId": "opt_inbox"},
                "Upstream": "https://github.com/owner/demo",
                "AI Score": 0.1,
            },
        )
        responses: list = [
            _items_page([existing]),
            {"updateProjectV2ItemFieldValue": {"projectV2Item": {"id": "PVTI_demo"}}},  # Status=Filtered
        ]
        fake = FakeRun(responses)
        buf = io.StringIO()
        with patch.object(project_board.subprocess, "run", fake), redirect_stdout(buf):
            rc = project_board.cmd_sync(_ns(root))
        self.assertEqual(rc, 0)
        summary = json.loads(buf.getvalue())
        self.assertIn("demo->Filtered", summary["auto_terminal"])

    def test_sync_moves_build_failed_queue_items_to_blocked_status(self) -> None:
        queue = {
            "items": [
                {
                    "id": "github:owner/demo",
                    "slug": "demo",
                    "state": "build_failed",
                    "candidate": {"repo_url": "https://github.com/owner/demo"},
                    "discovery_review": {"score": 0.85, "status": "migrate"},
                }
            ]
        }
        root = self._setup(queue)
        existing = _item_node(
            "PVTI_demo",
            {
                "Slug": "demo",
                "Status": {"name": "In-Progress", "optionId": "opt_ip"},
                "Upstream": "https://github.com/owner/demo",
                "AI Score": 0.85,
            },
        )
        responses: list = [
            _items_page([existing]),
            {"updateProjectV2ItemFieldValue": {"projectV2Item": {"id": "PVTI_demo"}}},  # Status=Blocked
        ]
        fake = FakeRun(responses)
        buf = io.StringIO()
        with patch.object(project_board.subprocess, "run", fake), redirect_stdout(buf):
            rc = project_board.cmd_sync(_ns(root))
        self.assertEqual(rc, 0)
        summary = json.loads(buf.getvalue())
        self.assertIn("demo->Blocked", summary["auto_terminal"])

    def test_sync_does_not_auto_approve_discovery_review_items(self) -> None:
        queue = {
            "items": [
                {
                    "id": "github:owner/demo",
                    "slug": "demo",
                    "state": "discovery_review",   # awaiting AI verdict
                    "candidate": {"repo_url": "https://github.com/owner/demo"},
                }
            ]
        }
        root = self._setup(queue)
        existing = _item_node(
            "PVTI_demo",
            {
                "Slug": "demo",
                "Status": {"name": "Inbox", "optionId": "opt_inbox"},
                "Upstream": "https://github.com/owner/demo",   # already-set; no mutation needed
            },
        )
        # _build_item_index only; no Status=Approved because state is
        # discovery_review (awaiting AI) and no score is set yet.
        fake = FakeRun([_items_page([existing])])
        buf = io.StringIO()
        with patch.object(project_board.subprocess, "run", fake), redirect_stdout(buf):
            rc = project_board.cmd_sync(_ns(root))
        self.assertEqual(rc, 0)
        summary = json.loads(buf.getvalue())
        self.assertEqual(summary["approved"], [])

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


class RenderCardBodyTest(unittest.TestCase):
    def test_renders_markdown_with_full_audit_chain(self) -> None:
        body = project_board.render_card_body({
            "id": "github:owner/demo",
            "slug": "demo",
            "source": "owner/demo",
            "candidate": {
                "repo_url": "https://github.com/owner/demo",
                "description": "Self-hosted memes",
                "language": "Python",
                "total_stars": 1234,
                "first_seen_at": "2026-04-01T10:00:00Z",
                "lazycat_hits": [
                    {"raw_label": "Memes Pro 12", "detail_url": "https://lazycat.cloud/appstore/detail/x"},
                    {"raw_label": "Other 3", "detail_url": "https://lazycat.cloud/appstore/detail/y"},
                ],
                "source_labels": ["GitHub Trending Daily", "Awesome Self-Hosted"],
            },
            "discovery_review": {
                "status": "migrate",
                "score": 0.91,
                "reviewer": "claude",
                "reason": "Real self-hosted web service with active maintenance.",
                "evidence": ["docker-compose.yml present", "README has install steps"],
                "reviewed_at": "2026-04-15T08:00:00Z",
            },
            "last_error": "",
        })
        self.assertIn("# `demo`", body)
        self.assertIn("https://github.com/owner/demo", body)
        self.assertIn("Self-hosted memes", body)
        self.assertIn("Stars: 1234", body)
        self.assertIn("Discovered: 2026-04-01", body)
        self.assertIn("Reviewed: 2026-04-15", body)
        self.assertIn("`migrate`", body)
        self.assertIn("score **0.91**", body)
        self.assertIn("docker-compose.yml present", body)
        self.assertIn("[Memes Pro 12](https://lazycat.cloud/appstore/detail/x)", body)
        self.assertIn("Discovered via**: GitHub Trending Daily, Awesome Self-Hosted", body)

    def test_renders_minimal_body_when_only_slug_known(self) -> None:
        body = project_board.render_card_body({"slug": "tiny", "candidate": {}})
        self.assertIn("# `tiny`", body)
        # No AI verdict / store-hits / errors → those sections must be absent.
        self.assertNotIn("## AI verdict", body)
        self.assertNotIn("## LazyCat App Store", body)
        self.assertNotIn("## Last error", body)

    def test_renders_last_error_block_when_set(self) -> None:
        body = project_board.render_card_body({
            "slug": "broken",
            "candidate": {},
            "last_error": "build_failed: Dockerfile syntax error at line 42",
        })
        self.assertIn("## Last error", body)
        self.assertIn("Dockerfile syntax error", body)


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
