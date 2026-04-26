from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.auto_migration_service import (
    CommandResult,
    ServiceConfig,
    build_codex_worker_command,
    build_copywriter_command,
    build_functional_check_command,
    build_prepare_submission_command,
    build_auto_migrate_command,
    run_cycle,
    select_next_ready_item,
    upsert_candidates,
)


class AutoMigrationServiceTest(unittest.TestCase):
    def make_repo_root(self) -> Path:
        return Path(tempfile.mkdtemp(prefix="auto-migration-service-test-"))

    def test_upsert_candidates_records_ready_and_filtered_items(self) -> None:
        queue = {"schema_version": 1, "items": []}
        candidates = [
            {"full_name": "owner/demo", "repo": "demo", "repo_url": "https://github.com/owner/demo", "status": "portable"},
            {"full_name": "owner/sdk", "repo": "sdk", "repo_url": "https://github.com/owner/sdk", "status": "excluded"},
        ]

        updated = upsert_candidates(queue, candidates, now="2026-04-26T00:00:00Z")

        states = {item["id"]: item["state"] for item in updated["items"]}
        self.assertEqual(states["github:owner/demo"], "ready")
        self.assertEqual(states["github:owner/sdk"], "filtered_out")
        self.assertEqual(updated["items"][0]["source"], "owner/demo")
        self.assertEqual(updated["items"][0]["slug"], "demo")

    def test_upsert_candidates_preserves_in_progress_state(self) -> None:
        queue = {
            "schema_version": 1,
            "items": [
                {
                    "id": "github:owner/demo",
                    "source": "owner/demo",
                    "slug": "demo",
                    "state": "browser_pending",
                    "created_at": "2026-04-25T00:00:00Z",
                    "updated_at": "2026-04-25T00:00:00Z",
                }
            ],
        }

        updated = upsert_candidates(
            queue,
            [{"full_name": "owner/demo", "repo": "demo", "status": "portable"}],
            now="2026-04-26T00:00:00Z",
        )

        self.assertEqual(updated["items"][0]["state"], "browser_pending")
        self.assertEqual(updated["items"][0]["updated_at"], "2026-04-26T00:00:00Z")

    def test_select_next_ready_item_skips_filtered_and_pending_items(self) -> None:
        queue = {
            "schema_version": 1,
            "items": [
                {"id": "github:owner/sdk", "state": "filtered_out"},
                {"id": "github:owner/wait", "state": "browser_pending"},
                {"id": "github:owner/demo", "state": "ready", "source": "owner/demo"},
            ],
        }

        self.assertEqual(select_next_ready_item(queue)["id"], "github:owner/demo")

    def test_build_auto_migrate_command_defaults_to_validate_only(self) -> None:
        repo_root = self.make_repo_root()
        config = ServiceConfig(repo_root=repo_root, queue_path=repo_root / "registry" / "auto-migration" / "queue.json")
        item = {"source": "owner/demo", "slug": "demo"}

        command = build_auto_migrate_command(config, item)

        self.assertEqual(
            command,
            [
                "python3",
                "scripts/auto_migrate.py",
                "owner/demo",
                "--repo-root",
                str(repo_root),
                "--build-mode",
                "validate-only",
            ],
        )

    def test_build_auto_migrate_command_enables_reinstall_and_functional_check(self) -> None:
        repo_root = self.make_repo_root()
        config = ServiceConfig(
            repo_root=repo_root,
            queue_path=repo_root / "registry" / "auto-migration" / "queue.json",
            enable_build_install=True,
            functional_check=True,
            box_domain="box.example.test",
        )
        item = {"source": "owner/demo", "slug": "demo"}

        command = build_auto_migrate_command(config, item)

        self.assertIn("reinstall", command)
        self.assertIn("--functional-check", command)
        self.assertIn("--box-domain", command)
        self.assertIn("box.example.test", command)

    def test_run_cycle_dry_run_scans_and_writes_queue_without_migrating(self) -> None:
        repo_root = self.make_repo_root()
        snapshot_path = repo_root / "registry" / "candidates" / "latest.json"
        snapshot_path.parent.mkdir(parents=True)
        snapshot_path.write_text(
            json.dumps(
                {
                    "candidates": [
                        {
                            "full_name": "owner/demo",
                            "repo": "demo",
                            "repo_url": "https://github.com/owner/demo",
                            "status": "portable",
                        }
                    ]
                }
            )
            + "\n",
            encoding="utf-8",
        )
        calls: list[list[str]] = []

        def runner(command: list[str]) -> CommandResult:
            calls.append(command)
            return CommandResult(returncode=0)

        summary = run_cycle(
            ServiceConfig(
                repo_root=repo_root,
                queue_path=repo_root / "registry" / "auto-migration" / "queue.json",
                dry_run=True,
            ),
            runner=runner,
            now="2026-04-26T00:00:00Z",
        )

        self.assertEqual(len(calls), 2)
        self.assertEqual(summary["selected"], "github:owner/demo")
        self.assertEqual(summary["migration"]["status"], "dry_run")
        queue = json.loads((repo_root / "registry" / "auto-migration" / "queue.json").read_text(encoding="utf-8"))
        self.assertEqual(queue["items"][0]["state"], "ready")

    def test_run_cycle_migrates_one_ready_candidate(self) -> None:
        repo_root = self.make_repo_root()
        snapshot_path = repo_root / "registry" / "candidates" / "latest.json"
        snapshot_path.parent.mkdir(parents=True)
        snapshot_path.write_text(
            json.dumps(
                {
                    "candidates": [
                        {"full_name": "owner/one", "repo": "one", "status": "portable"},
                        {"full_name": "owner/two", "repo": "two", "status": "portable"},
                    ]
                }
            )
            + "\n",
            encoding="utf-8",
        )
        calls: list[list[str]] = []

        def runner(command: list[str]) -> CommandResult:
            calls.append(command)
            return CommandResult(returncode=0)

        summary = run_cycle(
            ServiceConfig(
                repo_root=repo_root,
                queue_path=repo_root / "registry" / "auto-migration" / "queue.json",
            ),
            runner=runner,
            now="2026-04-26T00:00:00Z",
        )

        self.assertEqual(summary["selected"], "github:owner/one")
        self.assertEqual(summary["migration"]["status"], "scaffolded")
        auto_migrate_calls = [call for call in calls if call[:2] == ["python3", "scripts/auto_migrate.py"]]
        self.assertEqual(len(auto_migrate_calls), 1)
        queue = json.loads((repo_root / "registry" / "auto-migration" / "queue.json").read_text(encoding="utf-8"))
        states = {item["id"]: item["state"] for item in queue["items"]}
        self.assertEqual(states["github:owner/one"], "scaffolded")
        self.assertEqual(states["github:owner/two"], "ready")

    def test_run_cycle_records_browser_pending_from_functional_check(self) -> None:
        repo_root = self.make_repo_root()
        (repo_root / "registry" / "candidates").mkdir(parents=True)
        (repo_root / "registry" / "candidates" / "latest.json").write_text(
            json.dumps({"candidates": [{"full_name": "owner/demo", "repo": "demo", "status": "portable"}]}) + "\n",
            encoding="utf-8",
        )
        (repo_root / "apps" / "demo").mkdir(parents=True)

        def runner(command: list[str]) -> CommandResult:
            if command[:2] == ["python3", "scripts/auto_migrate.py"]:
                (repo_root / "apps" / "demo" / ".functional-check.json").write_text(
                    json.dumps({"browser_acceptance_status": "browser_pending"}) + "\n",
                    encoding="utf-8",
                )
                return CommandResult(returncode=2)
            return CommandResult(returncode=0)

        summary = run_cycle(
            ServiceConfig(
                repo_root=repo_root,
                queue_path=repo_root / "registry" / "auto-migration" / "queue.json",
                enable_build_install=True,
                functional_check=True,
                box_domain="box.example.test",
            ),
            runner=runner,
            now="2026-04-26T00:00:00Z",
        )

        self.assertEqual(summary["migration"]["status"], "browser_pending")
        queue = json.loads((repo_root / "registry" / "auto-migration" / "queue.json").read_text(encoding="utf-8"))
        self.assertEqual(queue["items"][0]["state"], "browser_pending")

    def test_browser_passed_item_generates_copy_and_submission_materials(self) -> None:
        repo_root = self.make_repo_root()
        queue_path = repo_root / "registry" / "auto-migration" / "queue.json"
        queue_path.parent.mkdir(parents=True)
        queue_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "items": [
                        {
                            "id": "github:owner/demo",
                            "source": "owner/demo",
                            "slug": "demo",
                            "state": "browser_passed",
                            "created_at": "2026-04-25T00:00:00Z",
                            "updated_at": "2026-04-25T00:00:00Z",
                        }
                    ],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        calls: list[list[str]] = []

        def runner(command: list[str]) -> CommandResult:
            calls.append(command)
            return CommandResult(returncode=0)

        summary = run_cycle(
            ServiceConfig(
                repo_root=repo_root,
                queue_path=queue_path,
                skip_status_sync=True,
                skip_scout=True,
                developer_url="https://lazycat.cloud/appstore/more/developers/178",
            ),
            runner=runner,
            now="2026-04-26T00:00:00Z",
        )

        self.assertEqual(summary["post_acceptance"][0]["status"], "publish_ready")
        self.assertIn(build_copywriter_command(ServiceConfig(repo_root=repo_root, queue_path=queue_path), {"slug": "demo"}), calls)
        self.assertIn(
            build_prepare_submission_command(
                ServiceConfig(
                    repo_root=repo_root,
                    queue_path=queue_path,
                    developer_url="https://lazycat.cloud/appstore/more/developers/178",
                ),
                {"slug": "demo"},
            ),
            calls,
        )
        queue = json.loads(queue_path.read_text(encoding="utf-8"))
        self.assertEqual(queue["items"][0]["state"], "publish_ready")

    def test_browser_pending_item_is_rechecked_then_prepared_for_publish(self) -> None:
        repo_root = self.make_repo_root()
        queue_path = repo_root / "registry" / "auto-migration" / "queue.json"
        queue_path.parent.mkdir(parents=True)
        queue_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "items": [
                        {
                            "id": "github:owner/demo",
                            "source": "owner/demo",
                            "slug": "demo",
                            "state": "browser_pending",
                            "created_at": "2026-04-25T00:00:00Z",
                            "updated_at": "2026-04-25T00:00:00Z",
                        }
                    ],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (repo_root / "apps" / "demo").mkdir(parents=True)
        calls: list[list[str]] = []

        def runner(command: list[str]) -> CommandResult:
            calls.append(command)
            if command[:2] == ["python3", "scripts/functional_checker.py"]:
                (repo_root / "apps" / "demo" / ".functional-check.json").write_text(
                    json.dumps({"browser_acceptance_status": "browser_pass"}) + "\n",
                    encoding="utf-8",
                )
            return CommandResult(returncode=0)

        config = ServiceConfig(
            repo_root=repo_root,
            queue_path=queue_path,
            skip_status_sync=True,
            skip_scout=True,
            functional_check=True,
            box_domain="box.example.test",
            developer_url="https://lazycat.cloud/appstore/more/developers/178",
        )

        summary = run_cycle(config, runner=runner, now="2026-04-26T00:00:00Z")

        self.assertEqual(summary["browser_recheck"][0]["status"], "browser_passed")
        self.assertEqual(summary["post_acceptance"][0]["status"], "publish_ready")
        self.assertIn(build_functional_check_command(config, {"slug": "demo"}), calls)
        queue = json.loads(queue_path.read_text(encoding="utf-8"))
        self.assertEqual(queue["items"][0]["state"], "publish_ready")

    def test_build_codex_worker_command_passes_queue_item_json(self) -> None:
        repo_root = self.make_repo_root()
        config = ServiceConfig(
            repo_root=repo_root,
            queue_path=repo_root / "registry" / "auto-migration" / "queue.json",
            box_domain="box.example.test",
        )
        item = {"id": "github:owner/demo", "source": "owner/demo", "slug": "demo", "state": "build_failed"}

        command = build_codex_worker_command(config, item)

        self.assertEqual(command[:2], ["python3", "scripts/codex_migration_worker.py"])
        self.assertIn("--item-json", command)
        payload = json.loads(command[command.index("--item-json") + 1])
        self.assertEqual(payload["id"], "github:owner/demo")
        self.assertIn("--box-domain", command)
        self.assertIn("box.example.test", command)

    def test_run_cycle_invokes_codex_worker_for_failed_item(self) -> None:
        repo_root = self.make_repo_root()
        queue_path = repo_root / "registry" / "auto-migration" / "queue.json"
        queue_path.parent.mkdir(parents=True)
        queue_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "items": [
                        {
                            "id": "github:owner/demo",
                            "source": "owner/demo",
                            "slug": "demo",
                            "state": "build_failed",
                            "last_error": "compose parser failed",
                            "created_at": "2026-04-25T00:00:00Z",
                            "updated_at": "2026-04-25T00:00:00Z",
                        }
                    ],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        calls: list[list[str]] = []

        def runner(command: list[str]) -> CommandResult:
            calls.append(command)
            return CommandResult(returncode=0)

        summary = run_cycle(
            ServiceConfig(
                repo_root=repo_root,
                queue_path=queue_path,
                skip_status_sync=True,
                skip_scout=True,
                dry_run=True,
                enable_codex_worker=True,
                box_domain="box.example.test",
            ),
            runner=runner,
            now="2026-04-26T00:00:00Z",
        )

        self.assertEqual(summary["codex_worker"][0]["status"], "ready")
        self.assertEqual(summary["migration"]["status"], "dry_run")
        self.assertTrue(any(call[:2] == ["python3", "scripts/codex_migration_worker.py"] for call in calls))
        queue = json.loads(queue_path.read_text(encoding="utf-8"))
        self.assertEqual(queue["items"][0]["state"], "ready")
        self.assertEqual(queue["items"][0]["codex"]["attempts"], 1)

    def test_run_cycle_respects_codex_attempt_limit(self) -> None:
        repo_root = self.make_repo_root()
        queue_path = repo_root / "registry" / "auto-migration" / "queue.json"
        queue_path.parent.mkdir(parents=True)
        queue_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "items": [
                        {
                            "id": "github:owner/demo",
                            "source": "owner/demo",
                            "slug": "demo",
                            "state": "build_failed",
                            "codex": {"attempts": 1},
                            "created_at": "2026-04-25T00:00:00Z",
                            "updated_at": "2026-04-25T00:00:00Z",
                        }
                    ],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        calls: list[list[str]] = []

        def runner(command: list[str]) -> CommandResult:
            calls.append(command)
            return CommandResult(returncode=0)

        summary = run_cycle(
            ServiceConfig(
                repo_root=repo_root,
                queue_path=queue_path,
                skip_status_sync=True,
                skip_scout=True,
                enable_codex_worker=True,
                max_codex_attempts=1,
            ),
            runner=runner,
            now="2026-04-26T00:00:00Z",
        )

        self.assertEqual(summary["codex_worker"], [])
        self.assertEqual(calls, [])
        queue = json.loads(queue_path.read_text(encoding="utf-8"))
        self.assertEqual(queue["items"][0]["state"], "build_failed")


if __name__ == "__main__":
    unittest.main()
