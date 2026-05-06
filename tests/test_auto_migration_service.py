from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.auto_migration_service import (
    CommandResult,
    ServiceConfig,
    build_codex_discovery_review_command,
    build_codex_worker_command,
    build_config,
    build_copywriter_command,
    build_functional_check_command,
    build_prepare_submission_command,
    build_auto_migrate_command,
    run_cycle,
    load_env_file,
    select_next_ready_item,
    upsert_candidates,
)


class AutoMigrationServiceTest(unittest.TestCase):
    def make_repo_root(self) -> Path:
        return Path(tempfile.mkdtemp(prefix="auto-migration-service-test-"))

    def make_args(self, repo_root: Path) -> argparse.Namespace:
        return argparse.Namespace(
            repo_root=str(repo_root),
            queue_path="registry/auto-migration/queue.json",
            candidate_snapshot="registry/candidates/latest.json",
            limit=50,
            skip_status_sync=False,
            skip_scout=False,
            skip_github_search=False,
            skip_awesome_selfhosted=False,
            dry_run=False,
            enable_build_install=False,
            functional_check=False,
            box_domain="",
            developer_url="",
            max_migrations_per_cycle=1,
            max_discovery_reviews_per_cycle=1,
            commit_scaffold=False,
            resume=False,
            enable_codex_worker=False,
            max_codex_attempts=1,
            workspace_root="",
            template_branch="",
            codex_worker_model="",
            disable_discord=False,
            require_discord=False,
            disable_local_agent=False,
        )

    def test_load_env_file_reads_simple_dotenv_without_overwriting_existing_values(self) -> None:
        repo_root = self.make_repo_root()
        env_path = repo_root / "scripts" / ".env.local"
        env_path.parent.mkdir(parents=True)
        env_path.write_text(
            "\n".join(
                [
                    "# local secrets",
                    "GH_TOKEN=token-from-file",
                    "QUOTED_VALUE='hello world'",
                    "BAD-KEY=ignored",
                    "",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        with patch.dict("os.environ", {"GH_TOKEN": "existing-token"}, clear=False):
            loaded = load_env_file(env_path)

            self.assertNotIn("GH_TOKEN", loaded)
            self.assertIn("QUOTED_VALUE", loaded)
            self.assertEqual(os.environ["GH_TOKEN"], "existing-token")
            self.assertEqual(os.environ["QUOTED_VALUE"], "hello world")

    def test_build_config_disables_discord_when_token_is_missing_by_default(self) -> None:
        repo_root = self.make_repo_root()
        (repo_root / "project-config.json").write_text(
            json.dumps({"discord": {"enabled": True, "guild_id": "guild-1", "category_id": "category-1"}}) + "\n",
            encoding="utf-8",
        )

        with patch.dict("os.environ", {}, clear=True):
            config = build_config(self.make_args(repo_root))

        self.assertFalse(config.discord_enabled)

    def test_build_config_can_require_discord_credentials(self) -> None:
        repo_root = self.make_repo_root()
        (repo_root / "project-config.json").write_text(
            json.dumps({"discord": {"enabled": True, "guild_id": "guild-1", "category_id": "category-1"}}) + "\n",
            encoding="utf-8",
        )
        args = self.make_args(repo_root)
        args.require_discord = True

        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(SystemExit):
                build_config(args)

    def test_build_config_allows_cli_overrides_for_fusion_daemon(self) -> None:
        repo_root = self.make_repo_root()
        (repo_root / "project-config.json").write_text(
            json.dumps(
                {
                    "migration": {
                        "template_branch": "template",
                        "workspace_root": "/tmp/original-workspaces",
                        "codex_worker_model": "gpt-5.5",
                    },
                    "local_agent": {"enabled": True, "path": "/tmp/LocalAgent"},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        args = self.make_args(repo_root)
        args.workspace_root = "../migration-workspaces"
        args.template_branch = "template"
        args.codex_worker_model = "gpt-5.4"
        args.disable_local_agent = True

        config = build_config(args)

        self.assertEqual(config.workspace_root, repo_root.resolve() / "../migration-workspaces")
        self.assertEqual(config.codex_worker_model, "gpt-5.4")
        self.assertFalse(config.local_agent_enabled)

    def test_build_config_loads_migration_discord_and_local_agent_policy(self) -> None:
        repo_root = self.make_repo_root()
        (repo_root / "project-config.json").write_text(
            json.dumps(
                {
                    "migration": {
                        "template_branch": "template",
                        "workspace_root": "/tmp/lzcat-workspaces",
                        "codex_worker_model": "gpt-5.5",
                    },
                    "discord": {
                        "enabled": True,
                        "guild_id": "guild-1",
                        "category_id": "category-1",
                        "channel_prefix": "migration",
                    },
                    "local_agent": {
                        "enabled": True,
                        "path": "/tmp/LocalAgent",
                        "snapshot_path": "registry/candidates/local-agent-latest.json",
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )

        with patch.dict("os.environ", {"LZCAT_DISCORD_BOT_TOKEN": "token-1"}):
            config = build_config(self.make_args(repo_root))

        self.assertEqual(config.template_branch, "template")
        self.assertEqual(config.workspace_root, Path("/tmp/lzcat-workspaces"))
        self.assertEqual(config.codex_worker_model, "gpt-5.5")
        self.assertTrue(config.discord_enabled)
        self.assertEqual(config.discord_guild_id, "guild-1")
        self.assertEqual(config.discord_category_id, "category-1")
        self.assertEqual(config.discord_channel_prefix, "migration")
        self.assertEqual(config.discord_bot_token, "token-1")
        self.assertTrue(config.local_agent_enabled)
        self.assertEqual(config.local_agent_path, Path("/tmp/LocalAgent"))
        self.assertEqual(
            config.local_agent_snapshot_path,
            repo_root.resolve() / "registry" / "candidates" / "local-agent-latest.json",
        )

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

    def test_upsert_candidates_routes_needs_review_to_discovery_review(self) -> None:
        updated = upsert_candidates(
            {"schema_version": 1, "items": []},
            [{"full_name": "owner/demo", "repo": "demo", "repo_url": "https://github.com/owner/demo", "status": "needs_review"}],
            now="2026-04-26T00:00:00Z",
        )

        self.assertEqual(updated["items"][0]["state"], "discovery_review")

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

    def test_upsert_candidates_preserves_waiting_for_human_state(self) -> None:
        queue = {
            "schema_version": 1,
            "items": [
                {
                    "id": "github:owner/demo",
                    "source": "owner/demo",
                    "slug": "demo",
                    "state": "waiting_for_human",
                    "human_request": {"question": "Need credentials?", "created_at": "2026-04-25T00:00:00Z"},
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

        self.assertEqual(updated["items"][0]["state"], "waiting_for_human")
        self.assertEqual(updated["items"][0]["human_request"]["question"], "Need credentials?")

    def test_upsert_candidates_preserves_filtered_out_state(self) -> None:
        queue = {
            "schema_version": 1,
            "items": [
                {
                    "id": "github:owner/list",
                    "source": "owner/list",
                    "slug": "list",
                    "state": "filtered_out",
                    "filtered_reason": "ai_discovery_skip",
                    "discovery_review": {"status": "skip"},
                    "created_at": "2026-04-25T00:00:00Z",
                    "updated_at": "2026-04-25T00:00:00Z",
                }
            ],
        }

        updated = upsert_candidates(
            queue,
            [{"full_name": "owner/list", "repo": "list", "status": "needs_review"}],
            now="2026-04-26T00:00:00Z",
        )

        self.assertEqual(updated["items"][0]["state"], "filtered_out")
        self.assertEqual(updated["items"][0]["filtered_reason"], "ai_discovery_skip")

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

    def test_run_cycle_reconciles_published_candidate_before_migration(self) -> None:
        repo_root = self.make_repo_root()
        snapshot_path = repo_root / "registry" / "candidates" / "latest.json"
        snapshot_path.parent.mkdir(parents=True)
        snapshot_path.write_text(
            json.dumps({"candidates": [{"full_name": "owner/demo", "repo": "demo", "status": "portable"}]}) + "\n",
            encoding="utf-8",
        )
        status_path = repo_root / "registry" / "status" / "local-publication-status.json"
        status_path.parent.mkdir(parents=True)
        status_path.write_text(
            json.dumps(
                {
                    "apps": {
                        "demo": {
                            "slug": "demo",
                            "upstream_repo": "owner/demo",
                            "publication_status": "published",
                            "store_label": "Demo",
                        }
                    }
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
                skip_status_sync=True,
                skip_scout=True,
            ),
            runner=runner,
            now="2026-04-26T00:00:00Z",
        )

        self.assertEqual(summary["discovery_gate"][0]["reason"], "published_upstream")
        self.assertEqual(summary["migration"]["status"], "idle")
        self.assertFalse(any(call[:2] == ["python3", "scripts/auto_migrate.py"] for call in calls))
        queue = json.loads((repo_root / "registry" / "auto-migration" / "queue.json").read_text(encoding="utf-8"))
        self.assertEqual(queue["items"][0]["state"], "filtered_out")

    def test_run_cycle_merges_local_agent_candidates_but_waits_for_button_decision(self) -> None:
        repo_root = self.make_repo_root()
        local_agent_root = repo_root / "LocalAgent"
        (local_agent_root / "data").mkdir(parents=True)
        (local_agent_root / "data" / "state.json").write_text(
            json.dumps(
                {
                    "projects": {
                        "owner/localapp": {
                            "full_name": "owner/localapp",
                            "repo": "localapp",
                            "repo_url": "https://github.com/owner/localapp",
                            "status": "portable",
                            "description": "Found by LocalAgent",
                        }
                    }
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (repo_root / "registry" / "candidates").mkdir(parents=True)
        (repo_root / "registry" / "candidates" / "latest.json").write_text(json.dumps({"candidates": []}) + "\n", encoding="utf-8")

        summary = run_cycle(
            ServiceConfig(
                repo_root=repo_root,
                queue_path=repo_root / "registry" / "auto-migration" / "queue.json",
                skip_status_sync=True,
                skip_scout=True,
                dry_run=True,
                local_agent_enabled=True,
                local_agent_path=local_agent_root,
                local_agent_snapshot_path=repo_root / "registry" / "candidates" / "local-agent-latest.json",
            ),
            runner=lambda command: CommandResult(returncode=0),
            now="2026-04-26T00:00:00Z",
        )

        self.assertEqual(summary["local_agent"]["status"], "imported")
        self.assertIsNone(summary["selected"])
        queue = json.loads((repo_root / "registry" / "auto-migration" / "queue.json").read_text(encoding="utf-8"))
        self.assertEqual(queue["items"][0]["candidate"]["discovery_source"], "local_agent")
        self.assertEqual(queue["items"][0]["state"], "local_agent_pending_decision")

    def test_upsert_routes_local_agent_store_hits_to_discovery_review(self) -> None:
        queue = {"items": []}
        candidates = [
            {
                "full_name": "paperclipai/paperclip",
                "repo": "paperclip",
                "repo_url": "https://github.com/paperclipai/paperclip",
                "status": "needs_review",
                "status_reason": "LazyCat app-store search returned matches; AI discovery review required.",
                "discovery_source": "local_agent",
                "lazycat_hits": [
                    {
                        "raw_label": "Paperclip AI",
                        "detail_url": "https://lazycat.cloud/appstore/detail/fun.selfstudio.app.paperclip",
                    }
                ],
                "ai_store_review": {"status": "pending", "source": "lazycat_store_search"},
            }
        ]

        updated = upsert_candidates(queue, candidates, now="2026-04-26T00:00:00Z")

        self.assertEqual(updated["items"][0]["state"], "discovery_review")
        self.assertEqual(updated["items"][0]["candidate_status"], "needs_review")

    def test_run_cycle_periodically_refreshes_local_agent_store_search_cache(self) -> None:
        repo_root = self.make_repo_root()
        local_agent_root = repo_root / "LocalAgent"
        (local_agent_root / "data").mkdir(parents=True)
        (local_agent_root / "data" / "state.json").write_text(
            json.dumps(
                {
                    "projects": {
                        "owner/localapp": {
                            "full_name": "owner/localapp",
                            "repo": "localapp",
                            "repo_url": "https://github.com/owner/localapp",
                            "status": "portable",
                            "description": "Found by LocalAgent",
                        }
                    }
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (repo_root / "registry" / "candidates").mkdir(parents=True)
        (repo_root / "registry" / "candidates" / "latest.json").write_text(json.dumps({"candidates": []}) + "\n", encoding="utf-8")
        queue_path = repo_root / "registry" / "auto-migration" / "queue.json"
        queue_path.parent.mkdir(parents=True)
        queue_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "items": [
                        {
                            "id": "github:owner/localapp",
                            "source": "owner/localapp",
                            "slug": "localapp",
                            "state": "ready",
                            "candidate_status": "portable",
                            "candidate": {
                                "full_name": "owner/localapp",
                                "repo": "localapp",
                                "status": "portable",
                                "discovery_source": "local_agent",
                            },
                        }
                    ],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        cache_path = repo_root / "registry" / "auto-migration" / "local-agent-store-search-cache.json"
        cache_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "items": {
                        "github:owner/localapp": {
                            "reviewed_at": "2026-04-25T00:00:00Z",
                            "search_result": {
                                "status": "portable",
                                "reason": "No matching app found in LazyCat app store search.",
                                "searches": [{"term": "localapp"}],
                                "hits": [],
                                "errors": [],
                            },
                        }
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )

        def searcher(repo: dict[str, object]) -> dict[str, object]:
            return {
                "status": "needs_review",
                "reason": "LazyCat app-store search returned matches; AI discovery review required.",
                "searches": [{"term": "localapp"}],
                "hits": [{"raw_label": "Local App", "detail_url": "https://lazycat.cloud/appstore/detail/localapp"}],
                "errors": [],
            }

        with patch("scripts.local_agent_bridge.default_store_searcher", side_effect=searcher):
            summary = run_cycle(
                ServiceConfig(
                    repo_root=repo_root,
                    queue_path=queue_path,
                    skip_status_sync=True,
                    skip_scout=True,
                    dry_run=True,
                    enable_codex_worker=True,
                    local_agent_enabled=True,
                    local_agent_path=local_agent_root,
                    local_agent_snapshot_path=repo_root / "registry" / "candidates" / "local-agent-latest.json",
                    local_agent_store_search_ttl_seconds=3600,
                ),
                runner=lambda command: CommandResult(returncode=0),
                now="2026-04-26T11:00:01Z",
            )

        self.assertEqual(summary["local_agent"]["store_search_review"]["refreshed"], 1)
        queue = json.loads(queue_path.read_text(encoding="utf-8"))
        self.assertEqual(queue["items"][0]["state"], "discovery_review")
        self.assertEqual(queue["items"][0]["candidate"]["lazycat_hits"][0]["raw_label"], "Local App")

    def test_run_cycle_publishes_discord_update_for_migration_state(self) -> None:
        repo_root = self.make_repo_root()
        snapshot_path = repo_root / "registry" / "candidates" / "latest.json"
        snapshot_path.parent.mkdir(parents=True)
        snapshot_path.write_text(
            json.dumps({"candidates": [{"full_name": "owner/piclaw", "repo": "piclaw", "status": "portable"}]}) + "\n",
            encoding="utf-8",
        )

        class FakeDiscordNotifier:
            def __init__(self) -> None:
                self.updates: list[tuple[str, str]] = []

            def publish_update(self, item: dict[str, object], *, status: str, now: str) -> dict[str, str]:
                self.updates.append((str(item["id"]), status))
                item["discord"] = {
                    "channel_id": "channel-1",
                    "message_id": "message-1",
                    "last_status": status,
                    "last_update_at": now,
                }
                return item["discord"]  # type: ignore[return-value]

        notifier = FakeDiscordNotifier()

        summary = run_cycle(
            ServiceConfig(
                repo_root=repo_root,
                queue_path=repo_root / "registry" / "auto-migration" / "queue.json",
                skip_status_sync=True,
                skip_scout=True,
                discord_enabled=True,
                discord_guild_id="guild-1",
                discord_bot_token="token-1",
            ),
            runner=lambda command: CommandResult(returncode=0),
            now="2026-04-26T00:00:00Z",
            discord_notifier=notifier,
        )

        self.assertEqual(summary["migration"]["status"], "scaffolded")
        self.assertEqual(notifier.updates, [("github:owner/piclaw", "scaffolded")])
        queue = json.loads((repo_root / "registry" / "auto-migration" / "queue.json").read_text(encoding="utf-8"))
        self.assertEqual(queue["items"][0]["discord"]["channel_id"], "channel-1")
        self.assertEqual(queue["items"][0]["discord"]["message_id"], "message-1")

    def test_discord_update_failure_is_recorded_without_failing_cycle(self) -> None:
        repo_root = self.make_repo_root()
        snapshot_path = repo_root / "registry" / "candidates" / "latest.json"
        snapshot_path.parent.mkdir(parents=True)
        snapshot_path.write_text(
            json.dumps({"candidates": [{"full_name": "owner/piclaw", "repo": "piclaw", "status": "portable"}]}) + "\n",
            encoding="utf-8",
        )

        class FailingDiscordNotifier:
            def publish_update(self, item: dict[str, object], *, status: str, now: str) -> dict[str, str]:
                raise RuntimeError("Discord HTTP 403")

        summary = run_cycle(
            ServiceConfig(
                repo_root=repo_root,
                queue_path=repo_root / "registry" / "auto-migration" / "queue.json",
                skip_status_sync=True,
                skip_scout=True,
                discord_enabled=True,
                discord_guild_id="guild-1",
                discord_bot_token="token-1",
            ),
            runner=lambda command: CommandResult(returncode=0),
            now="2026-04-26T00:00:00Z",
            discord_notifier=FailingDiscordNotifier(),
        )

        self.assertEqual(summary["migration"]["status"], "scaffolded")
        queue = json.loads((repo_root / "registry" / "auto-migration" / "queue.json").read_text(encoding="utf-8"))
        self.assertIn("Discord HTTP 403", queue["items"][0]["discord"]["last_error"])

    def test_run_cycle_does_not_create_discord_channel_for_filtered_item(self) -> None:
        repo_root = self.make_repo_root()
        snapshot_path = repo_root / "registry" / "candidates" / "latest.json"
        snapshot_path.parent.mkdir(parents=True)
        snapshot_path.write_text(
            json.dumps({"candidates": [{"full_name": "owner/demo", "repo": "demo", "status": "portable"}]}) + "\n",
            encoding="utf-8",
        )
        status_path = repo_root / "registry" / "status" / "local-publication-status.json"
        status_path.parent.mkdir(parents=True)
        status_path.write_text(
            json.dumps({"apps": {"demo": {"slug": "demo", "upstream_repo": "owner/demo", "publication_status": "published"}}})
            + "\n",
            encoding="utf-8",
        )

        class FakeDiscordNotifier:
            def __init__(self) -> None:
                self.updates: list[tuple[str, str]] = []

            def publish_update(self, item: dict[str, object], *, status: str, now: str) -> dict[str, str]:
                self.updates.append((str(item["id"]), status))
                return {}

        notifier = FakeDiscordNotifier()

        summary = run_cycle(
            ServiceConfig(
                repo_root=repo_root,
                queue_path=repo_root / "registry" / "auto-migration" / "queue.json",
                skip_status_sync=True,
                skip_scout=True,
                discord_enabled=True,
                discord_guild_id="guild-1",
                discord_bot_token="token-1",
            ),
            runner=lambda command: CommandResult(returncode=0),
            now="2026-04-26T00:00:00Z",
            discord_notifier=notifier,
        )

        self.assertEqual(summary["migration"]["status"], "idle")
        self.assertEqual(summary["discovery_gate"][0]["reason"], "published_upstream")
        self.assertEqual(notifier.updates, [])

    def test_run_cycle_creates_migration_worktree_before_migrating(self) -> None:
        repo_root = self.make_repo_root()
        workspace_root = repo_root / "migration-workspaces"
        snapshot_path = repo_root / "registry" / "candidates" / "latest.json"
        snapshot_path.parent.mkdir(parents=True)
        snapshot_path.write_text(
            json.dumps({"candidates": [{"full_name": "owner/piclaw", "repo": "piclaw", "status": "portable"}]}) + "\n",
            encoding="utf-8",
        )
        calls: list[list[str]] = []

        def runner(command: list[str]) -> CommandResult:
            calls.append(command)
            if command[:3] == ["git", "-C", str(repo_root)]:
                (workspace_root / "migration-piclaw").mkdir(parents=True)
            return CommandResult(returncode=0)

        summary = run_cycle(
            ServiceConfig(
                repo_root=repo_root,
                queue_path=repo_root / "registry" / "auto-migration" / "queue.json",
                skip_status_sync=True,
                skip_scout=True,
                template_branch="template",
                workspace_root=workspace_root,
            ),
            runner=runner,
            now="2026-04-26T00:00:00Z",
        )

        workspace_path = workspace_root / "migration-piclaw"
        self.assertEqual(summary["migration"]["status"], "scaffolded")
        self.assertEqual(
            calls[0],
            ["git", "-C", str(repo_root), "worktree", "add", "-b", "migration/piclaw", str(workspace_path), "template"],
        )
        auto_migrate_call = calls[1]
        self.assertEqual(auto_migrate_call[:2], ["python3", "scripts/auto_migrate.py"])
        self.assertEqual(auto_migrate_call[auto_migrate_call.index("--repo-root") + 1], str(workspace_path))
        queue = json.loads((repo_root / "registry" / "auto-migration" / "queue.json").read_text(encoding="utf-8"))
        self.assertEqual(queue["items"][0]["branch"], "migration/piclaw")
        self.assertEqual(queue["items"][0]["workspace_path"], str(workspace_path))

    def test_codex_worker_uses_migration_worktree_for_failed_item(self) -> None:
        repo_root = self.make_repo_root()
        workspace_root = repo_root / "migration-workspaces"
        queue_path = repo_root / "registry" / "auto-migration" / "queue.json"
        queue_path.parent.mkdir(parents=True)
        queue_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "items": [
                        {
                            "id": "github:owner/piclaw",
                            "source": "owner/piclaw",
                            "slug": "piclaw",
                            "state": "build_failed",
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
            if command[:3] == ["git", "-C", str(repo_root)]:
                (workspace_root / "migration-piclaw").mkdir(parents=True)
            return CommandResult(returncode=0)

        summary = run_cycle(
            ServiceConfig(
                repo_root=repo_root,
                queue_path=queue_path,
                skip_status_sync=True,
                skip_scout=True,
                dry_run=True,
                enable_codex_worker=True,
                template_branch="template",
                workspace_root=workspace_root,
            ),
            runner=runner,
            now="2026-04-26T00:00:00Z",
        )

        workspace_path = workspace_root / "migration-piclaw"
        self.assertEqual(summary["codex_worker"][0]["status"], "ready")
        self.assertEqual(
            calls[0],
            ["git", "-C", str(repo_root), "worktree", "add", "-b", "migration/piclaw", str(workspace_path), "template"],
        )
        codex_call = calls[1]
        self.assertEqual(codex_call[:2], ["python3", "scripts/codex_migration_worker.py"])
        self.assertEqual(codex_call[codex_call.index("--repo-root") + 1], str(workspace_path))
        self.assertEqual(codex_call[codex_call.index("--queue-path") + 1], str(queue_path))
        self.assertEqual(
            codex_call[codex_call.index("--task-root") + 1],
            str(repo_root / "registry" / "auto-migration" / "codex-tasks"),
        )
        queue = json.loads(queue_path.read_text(encoding="utf-8"))
        self.assertEqual(queue["items"][0]["branch"], "migration/piclaw")
        self.assertEqual(queue["items"][0]["workspace_path"], str(workspace_path))

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
        self.assertIn("--model", command)
        self.assertIn("claude-sonnet-4-6", command)

    def test_build_codex_discovery_review_command_passes_queue_context(self) -> None:
        repo_root = self.make_repo_root()
        queue_path = repo_root / "registry" / "auto-migration" / "queue.json"
        config = ServiceConfig(repo_root=repo_root, queue_path=queue_path, box_domain="box.example.test")
        item = {"id": "github:owner/demo", "source": "owner/demo", "slug": "demo", "state": "discovery_review"}

        command = build_codex_discovery_review_command(config, item)

        self.assertEqual(command[:2], ["python3", "scripts/codex_discovery_reviewer.py"])
        self.assertIn("--queue-path", command)
        self.assertEqual(command[command.index("--queue-path") + 1], str(queue_path))
        self.assertIn("--item-id", command)
        self.assertEqual(command[command.index("--item-id") + 1], "github:owner/demo")
        payload = json.loads(command[command.index("--item-json") + 1])
        self.assertEqual(payload["state"], "discovery_review")
        self.assertIn("--model", command)
        self.assertIn("claude-sonnet-4-6", command)

    def test_run_cycle_invokes_discovery_reviewer_before_migration(self) -> None:
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
                            "state": "discovery_review",
                            "discovery_review": {"prompt": "Judge migrate or skip"},
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
            if command[:2] == ["python3", "scripts/codex_discovery_reviewer.py"]:
                queue_path.write_text(
                    json.dumps(
                        {
                            "schema_version": 1,
                            "items": [
                                {
                                    "id": "github:owner/demo",
                                    "source": "owner/demo",
                                    "slug": "demo",
                                    "state": "ready",
                                    "discovery_review": {
                                        "status": "migrate",
                                        "evidence": ["Has Dockerfile and web UI"],
                                    },
                                }
                            ],
                        }
                    )
                    + "\n",
                    encoding="utf-8",
                )
            return CommandResult(returncode=0)

        summary = run_cycle(
            ServiceConfig(
                repo_root=repo_root,
                queue_path=queue_path,
                skip_status_sync=True,
                skip_scout=True,
                dry_run=True,
                enable_codex_worker=True,
            ),
            runner=runner,
            now="2026-04-26T00:00:00Z",
        )

        self.assertEqual(calls[0][:2], ["python3", "scripts/codex_discovery_reviewer.py"])
        self.assertEqual(summary["discovery_reviewer"][0]["status"], "ready")
        self.assertEqual(summary["migration"]["status"], "dry_run")
        queue = json.loads(queue_path.read_text(encoding="utf-8"))
        self.assertEqual(queue["items"][0]["state"], "ready")
        self.assertEqual(queue["items"][0]["discovery_review"]["codex_attempts"], 1)

    def test_discovery_human_reply_resumes_discovery_reviewer_not_migration_worker(self) -> None:
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
                            "state": "waiting_for_human",
                            "human_request": {"kind": "discovery_review", "question": "Is this already listed?"},
                            "human_response": {"content": "没有上架，可以迁移。"},
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
            if command[:2] == ["python3", "scripts/codex_discovery_reviewer.py"]:
                queue_path.write_text(
                    json.dumps(
                        {
                            "schema_version": 1,
                            "items": [
                                {
                                    "id": "github:owner/demo",
                                    "source": "owner/demo",
                                    "slug": "demo",
                                    "state": "ready",
                                    "human_request": {"kind": "discovery_review", "question": "Is this already listed?"},
                                    "human_response": {"content": "没有上架，可以迁移。"},
                                    "discovery_review": {"status": "migrate"},
                                }
                            ],
                        }
                    )
                    + "\n",
                    encoding="utf-8",
                )
            return CommandResult(returncode=0)

        summary = run_cycle(
            ServiceConfig(
                repo_root=repo_root,
                queue_path=queue_path,
                skip_status_sync=True,
                skip_scout=True,
                dry_run=True,
                enable_codex_worker=True,
                max_codex_attempts=2,
            ),
            runner=runner,
            now="2026-04-26T00:00:00Z",
        )

        self.assertEqual(calls[0][:2], ["python3", "scripts/codex_discovery_reviewer.py"])
        self.assertFalse(any(call[:2] == ["python3", "scripts/codex_migration_worker.py"] for call in calls))
        self.assertEqual(summary["discovery_reviewer"][0]["status"], "ready")
        queue = json.loads(queue_path.read_text(encoding="utf-8"))
        self.assertEqual(queue["items"][0]["state"], "ready")

    def test_new_needs_review_candidate_is_reviewed_before_selection(self) -> None:
        repo_root = self.make_repo_root()
        queue_path = repo_root / "registry" / "auto-migration" / "queue.json"
        candidate_path = repo_root / "registry" / "candidates" / "latest.json"
        queue_path.parent.mkdir(parents=True)
        candidate_path.parent.mkdir(parents=True)
        queue_path.write_text(json.dumps({"schema_version": 1, "items": []}) + "\n", encoding="utf-8")
        candidate_path.write_text(
            json.dumps(
                {
                    "candidates": [
                        {
                            "full_name": "owner/demo",
                            "repo": "demo",
                            "repo_url": "https://github.com/owner/demo",
                            "status": "needs_review",
                            "status_reason": "Weak store-name match requires AI check",
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
            if command[:2] == ["python3", "scripts/codex_discovery_reviewer.py"]:
                queue_path.write_text(
                    json.dumps(
                        {
                            "schema_version": 1,
                            "items": [
                                {
                                    "id": "github:owner/demo",
                                    "source": "owner/demo",
                                    "slug": "demo",
                                    "state": "ready",
                                    "discovery_review": {"status": "migrate"},
                                }
                            ],
                        }
                    )
                    + "\n",
                    encoding="utf-8",
                )
            return CommandResult(returncode=0)

        summary = run_cycle(
            ServiceConfig(
                repo_root=repo_root,
                queue_path=queue_path,
                skip_status_sync=True,
                skip_scout=True,
                dry_run=True,
                enable_codex_worker=True,
            ),
            runner=runner,
            now="2026-04-26T00:00:00Z",
        )

        self.assertTrue(any(call[:2] == ["python3", "scripts/codex_discovery_reviewer.py"] for call in calls))
        self.assertEqual(summary["discovery_reviewer"][0]["status"], "ready")
        self.assertEqual(summary["selected"], "github:owner/demo")
        self.assertEqual(summary["migration"]["status"], "dry_run")

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
            if command[:2] == ["python3", "scripts/codex_migration_worker.py"]:
                return CommandResult(
                    returncode=0,
                    stdout=json.dumps(
                        {
                            "status": "completed",
                            "returncode": 0,
                            "session_id": "11111111-2222-3333-4444-555555555555",
                            "task_dir": str(repo_root / "registry" / "auto-migration" / "codex-tasks" / "demo"),
                        }
                    ),
                )
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
        self.assertEqual(queue["items"][0]["codex"]["session_id"], "11111111-2222-3333-4444-555555555555")

    def test_codex_worker_completed_install_moves_to_browser_pending(self) -> None:
        repo_root = self.make_repo_root()
        workspace_path = repo_root / "workspaces" / "migration-demo"
        app_dir = workspace_path / "apps" / "demo"
        app_dir.mkdir(parents=True)
        (app_dir / ".migration-state.json").write_text(
            json.dumps({"steps": {"10": {"completed": True}}}) + "\n",
            encoding="utf-8",
        )
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
                            "workspace_path": str(workspace_path),
                        }
                    ],
                }
            )
            + "\n",
            encoding="utf-8",
        )

        def runner(command: list[str]) -> CommandResult:
            if command[:2] == ["python3", "scripts/codex_migration_worker.py"]:
                return CommandResult(
                    returncode=0,
                    stdout=json.dumps({"status": "completed", "returncode": 0, "task_dir": str(repo_root / "tasks")}),
                )
            return CommandResult(returncode=0)

        summary = run_cycle(
            ServiceConfig(
                repo_root=repo_root,
                queue_path=queue_path,
                skip_status_sync=True,
                skip_scout=True,
                enable_codex_worker=True,
                enable_build_install=True,
                functional_check=True,
                box_domain="box.example.test",
            ),
            runner=runner,
            now="2026-04-26T00:00:00Z",
        )

        self.assertEqual(summary["codex_worker"][0]["status"], "browser_pending")
        queue = json.loads(queue_path.read_text(encoding="utf-8"))
        self.assertEqual(queue["items"][0]["state"], "browser_pending")

    def test_codex_worker_command_passes_existing_session_id_in_item_json(self) -> None:
        repo_root = self.make_repo_root()
        queue_path = repo_root / "registry" / "auto-migration" / "queue.json"
        item = {
            "id": "github:owner/demo",
            "source": "owner/demo",
            "slug": "demo",
            "state": "build_failed",
            "codex": {"session_id": "11111111-2222-3333-4444-555555555555"},
        }
        config = ServiceConfig(repo_root=repo_root, queue_path=queue_path)

        command = build_codex_worker_command(config, item)
        payload = json.loads(command[command.index("--item-json") + 1])

        self.assertEqual(payload["codex"]["session_id"], "11111111-2222-3333-4444-555555555555")

    def test_run_cycle_reconciles_excluded_item_before_codex_worker(self) -> None:
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
                            "candidate_status": "excluded",
                            "candidate": {"status_reason": "Already available in LazyCat store"},
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
            ),
            runner=runner,
            now="2026-04-26T00:00:00Z",
        )

        self.assertEqual(summary["discovery_gate"][0]["reason"], "candidate_excluded")
        self.assertFalse(any(call[:2] == ["python3", "scripts/codex_migration_worker.py"] for call in calls))
        queue = json.loads(queue_path.read_text(encoding="utf-8"))
        self.assertEqual(queue["items"][0]["state"], "filtered_out")

    def test_codex_worker_can_leave_item_waiting_for_human(self) -> None:
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
                            "created_at": "2026-04-25T00:00:00Z",
                            "updated_at": "2026-04-25T00:00:00Z",
                        }
                    ],
                }
            )
            + "\n",
            encoding="utf-8",
        )

        def runner(command: list[str]) -> CommandResult:
            if command[:2] == ["python3", "scripts/codex_migration_worker.py"]:
                queue_path.write_text(
                    json.dumps(
                        {
                            "schema_version": 1,
                            "items": [
                                {
                                    "id": "github:owner/demo",
                                    "source": "owner/demo",
                                    "slug": "demo",
                                    "state": "waiting_for_human",
                                    "human_request": {
                                        "question": "Need app-store owner confirmation?",
                                        "options": ["confirm", "skip"],
                                        "created_at": "2026-04-26T00:00:00Z",
                                    },
                                }
                            ],
                        }
                    )
                    + "\n",
                    encoding="utf-8",
                )
            return CommandResult(returncode=0)

        summary = run_cycle(
            ServiceConfig(
                repo_root=repo_root,
                queue_path=queue_path,
                skip_status_sync=True,
                skip_scout=True,
                dry_run=True,
                enable_codex_worker=True,
            ),
            runner=runner,
            now="2026-04-26T00:00:00Z",
        )

        self.assertEqual(summary["codex_worker"][0]["status"], "waiting_for_human")
        queue = json.loads(queue_path.read_text(encoding="utf-8"))
        self.assertEqual(queue["items"][0]["state"], "waiting_for_human")
        self.assertEqual(queue["items"][0]["human_request"]["question"], "Need app-store owner confirmation?")

    def test_human_reply_is_ingested_before_codex_worker_resumes(self) -> None:
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
                            "state": "waiting_for_human",
                            "discord": {"channel_id": "channel-1", "message_id": "progress-1"},
                            "human_request": {"question": "作者填谁？"},
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

        observed_messages_calls: list[tuple[str, str]] = []

        class FakeDiscordClient:
            def list_messages(self, channel_id: str, *, after: str = "", limit: int = 20) -> list[dict[str, object]]:
                observed_messages_calls.append((channel_id, after))
                return [{"id": "human-1", "content": "填上游作者，继续。", "author": {"id": "u1", "username": "lincoln"}}]

            def send_message(self, channel_id: str, content: str) -> dict[str, str]:
                return {"id": "ack-1"}

        class NullDiscordNotifier:
            def publish_update(self, item: dict[str, object], *, status: str, now: str) -> dict[str, str]:
                return {"channel_id": "channel-1", "message_id": "progress-1"}

        summary = run_cycle(
            ServiceConfig(
                repo_root=repo_root,
                queue_path=queue_path,
                skip_status_sync=True,
                skip_scout=True,
                dry_run=True,
                discord_enabled=True,
                discord_guild_id="guild-1",
                discord_bot_token="token-1",
                enable_codex_worker=True,
                max_codex_attempts=2,
            ),
            runner=runner,
            now="2026-04-26T00:00:00Z",
            discord_notifier=NullDiscordNotifier(),
            discord_client=FakeDiscordClient(),
        )

        self.assertEqual(summary["discord_replies"][0]["status"], "human_response_received")
        self.assertEqual(observed_messages_calls, [("channel-1", "progress-1")])
        self.assertTrue(any(call[:2] == ["python3", "scripts/codex_migration_worker.py"] for call in calls))
        queue = json.loads(queue_path.read_text(encoding="utf-8"))
        self.assertEqual(queue["items"][0]["state"], "ready")
        self.assertEqual(queue["items"][0]["human_response"]["content"], "填上游作者，继续。")

    def test_run_cycle_processes_discord_local_agent_commands(self) -> None:
        repo_root = self.make_repo_root()
        local_agent_root = repo_root / "LocalAgent"
        queue_path = repo_root / "registry" / "auto-migration" / "queue.json"
        queue_path.parent.mkdir(parents=True)
        queue_path.write_text(json.dumps({"schema_version": 1, "items": []}) + "\n", encoding="utf-8")
        observed = {}

        def fake_process(command_config: object, client: object, *, now: str) -> list[dict[str, str]]:
            observed["local_agent_root"] = str(command_config.local_agent_root)
            observed["guild_id"] = command_config.guild_id
            observed["now"] = now
            return [{"message_id": "human-1", "status": "imported"}]

        with patch("scripts.auto_migration_service.process_local_agent_commands", side_effect=fake_process):
            summary = run_cycle(
                ServiceConfig(
                    repo_root=repo_root,
                    queue_path=queue_path,
                    skip_status_sync=True,
                    skip_scout=True,
                    dry_run=True,
                    discord_enabled=True,
                    discord_guild_id="guild-1",
                    discord_bot_token="token-1",
                    local_agent_enabled=True,
                    local_agent_path=local_agent_root,
                    local_agent_snapshot_path=repo_root / "registry" / "candidates" / "local-agent-latest.json",
                ),
                runner=lambda command: CommandResult(returncode=0),
                now="2026-04-26T00:00:00Z",
            )

        self.assertEqual(summary["local_agent_commands"], [{"message_id": "human-1", "status": "imported"}])
        self.assertEqual(observed["local_agent_root"], str(local_agent_root))
        self.assertEqual(observed["guild_id"], "guild-1")
        self.assertEqual(observed["now"], "2026-04-26T00:00:00Z")

    def test_run_cycle_reconciles_excluded_item_before_codex_worker(self) -> None:
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
                            "candidate_status": "excluded",
                            "candidate": {"status_reason": "Already available in LazyCat store"},
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
            ),
            runner=runner,
            now="2026-04-26T00:00:00Z",
        )

        self.assertEqual(summary["discovery_gate"][0]["reason"], "candidate_excluded")
        self.assertFalse(any(call[:2] == ["python3", "scripts/codex_migration_worker.py"] for call in calls))
        queue = json.loads(queue_path.read_text(encoding="utf-8"))
        self.assertEqual(queue["items"][0]["state"], "filtered_out")

    def test_codex_worker_can_leave_item_waiting_for_human(self) -> None:
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
                            "created_at": "2026-04-25T00:00:00Z",
                            "updated_at": "2026-04-25T00:00:00Z",
                        }
                    ],
                }
            )
            + "\n",
            encoding="utf-8",
        )

        def runner(command: list[str]) -> CommandResult:
            if command[:2] == ["python3", "scripts/codex_migration_worker.py"]:
                queue_path.write_text(
                    json.dumps(
                        {
                            "schema_version": 1,
                            "items": [
                                {
                                    "id": "github:owner/demo",
                                    "source": "owner/demo",
                                    "slug": "demo",
                                    "state": "waiting_for_human",
                                    "human_request": {
                                        "question": "Need app-store owner confirmation?",
                                        "options": ["confirm", "skip"],
                                        "created_at": "2026-04-26T00:00:00Z",
                                    },
                                }
                            ],
                        }
                    )
                    + "\n",
                    encoding="utf-8",
                )
            return CommandResult(returncode=0)

        summary = run_cycle(
            ServiceConfig(
                repo_root=repo_root,
                queue_path=queue_path,
                skip_status_sync=True,
                skip_scout=True,
                dry_run=True,
                enable_codex_worker=True,
            ),
            runner=runner,
            now="2026-04-26T00:00:00Z",
        )

        self.assertEqual(summary["codex_worker"][0]["status"], "waiting_for_human")
        queue = json.loads(queue_path.read_text(encoding="utf-8"))
        self.assertEqual(queue["items"][0]["state"], "waiting_for_human")
        self.assertEqual(queue["items"][0]["human_request"]["question"], "Need app-store owner confirmation?")

    def test_human_reply_is_ingested_before_codex_worker_resumes(self) -> None:
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
                            "state": "waiting_for_human",
                            "discord": {"channel_id": "channel-1", "message_id": "progress-1"},
                            "human_request": {"question": "作者填谁？"},
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

        observed_messages_calls: list[tuple[str, str]] = []

        class FakeDiscordClient:
            def list_messages(self, channel_id: str, *, after: str = "", limit: int = 20) -> list[dict[str, object]]:
                observed_messages_calls.append((channel_id, after))
                return [{"id": "human-1", "content": "填上游作者，继续。", "author": {"id": "u1", "username": "lincoln"}}]

            def send_message(self, channel_id: str, content: str) -> dict[str, str]:
                return {"id": "ack-1"}

        class NullDiscordNotifier:
            def publish_update(self, item: dict[str, object], *, status: str, now: str) -> dict[str, str]:
                return {"channel_id": "channel-1", "message_id": "progress-1"}

        summary = run_cycle(
            ServiceConfig(
                repo_root=repo_root,
                queue_path=queue_path,
                skip_status_sync=True,
                skip_scout=True,
                dry_run=True,
                discord_enabled=True,
                discord_guild_id="guild-1",
                discord_bot_token="token-1",
                enable_codex_worker=True,
                max_codex_attempts=2,
            ),
            runner=runner,
            now="2026-04-26T00:00:00Z",
            discord_notifier=NullDiscordNotifier(),
            discord_client=FakeDiscordClient(),
        )

        self.assertEqual(summary["discord_replies"][0]["status"], "human_response_received")
        self.assertEqual(observed_messages_calls, [("channel-1", "progress-1")])
        self.assertTrue(any(call[:2] == ["python3", "scripts/codex_migration_worker.py"] for call in calls))
        queue = json.loads(queue_path.read_text(encoding="utf-8"))
        self.assertEqual(queue["items"][0]["state"], "ready")
        self.assertEqual(queue["items"][0]["human_response"]["content"], "填上游作者，继续。")

    def test_run_cycle_processes_discord_local_agent_commands(self) -> None:
        repo_root = self.make_repo_root()
        local_agent_root = repo_root / "LocalAgent"
        queue_path = repo_root / "registry" / "auto-migration" / "queue.json"
        queue_path.parent.mkdir(parents=True)
        queue_path.write_text(json.dumps({"schema_version": 1, "items": []}) + "\n", encoding="utf-8")
        observed = {}

        def fake_process(command_config: object, client: object, *, now: str) -> list[dict[str, str]]:
            observed["local_agent_root"] = str(command_config.local_agent_root)
            observed["guild_id"] = command_config.guild_id
            observed["now"] = now
            return [{"message_id": "human-1", "status": "imported"}]

        with patch("scripts.auto_migration_service.process_local_agent_commands", side_effect=fake_process):
            summary = run_cycle(
                ServiceConfig(
                    repo_root=repo_root,
                    queue_path=queue_path,
                    skip_status_sync=True,
                    skip_scout=True,
                    dry_run=True,
                    discord_enabled=True,
                    discord_guild_id="guild-1",
                    discord_bot_token="token-1",
                    local_agent_enabled=True,
                    local_agent_path=local_agent_root,
                    local_agent_snapshot_path=repo_root / "registry" / "candidates" / "local-agent-latest.json",
                ),
                runner=lambda command: CommandResult(returncode=0),
                now="2026-04-26T00:00:00Z",
            )

        self.assertEqual(summary["local_agent_commands"], [{"message_id": "human-1", "status": "imported"}])
        self.assertEqual(observed["local_agent_root"], str(local_agent_root))
        self.assertEqual(observed["guild_id"], "guild-1")
        self.assertEqual(observed["now"], "2026-04-26T00:00:00Z")

    def test_codex_worker_success_keeps_browser_failed_state(self) -> None:
        repo_root = self.make_repo_root()
        queue_path = repo_root / "registry" / "auto-migration" / "queue.json"
        queue_path.parent.mkdir(parents=True)
        app_dir = repo_root / "apps" / "demo"
        app_dir.mkdir(parents=True)
        (app_dir / ".functional-check.json").write_text(
            json.dumps({"browser_acceptance_status": "browser_failed"}) + "\n",
            encoding="utf-8",
        )
        queue_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "items": [
                        {
                            "id": "github:owner/demo",
                            "source": "owner/demo",
                            "slug": "demo",
                            "state": "browser_failed",
                            "last_error": "Browser Use failed",
                            "created_at": "2026-04-25T00:00:00Z",
                            "updated_at": "2026-04-25T00:00:00Z",
                        }
                    ],
                }
            )
            + "\n",
            encoding="utf-8",
        )

        summary = run_cycle(
            ServiceConfig(
                repo_root=repo_root,
                queue_path=queue_path,
                skip_status_sync=True,
                skip_scout=True,
                dry_run=True,
                functional_check=True,
                enable_codex_worker=True,
                box_domain="box.example.test",
            ),
            runner=lambda command: CommandResult(returncode=0),
            now="2026-04-26T00:00:00Z",
        )

        self.assertEqual(summary["codex_worker"][0]["status"], "browser_failed")
        queue = json.loads(queue_path.read_text(encoding="utf-8"))
        self.assertEqual(queue["items"][0]["state"], "browser_failed")
        self.assertEqual(queue["items"][0]["codex"]["last_status"], "browser_failed")

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

    def test_run_cycle_invokes_codex_worker_before_scout(self) -> None:
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
            if command[:2] == ["python3", "scripts/scout.py"]:
                return CommandResult(returncode=1)
            return CommandResult(returncode=0)

        summary = run_cycle(
            ServiceConfig(
                repo_root=repo_root,
                queue_path=queue_path,
                skip_status_sync=True,
                enable_codex_worker=True,
            ),
            runner=runner,
            now="2026-04-26T00:00:00Z",
        )

        self.assertEqual(calls[0][:2], ["python3", "scripts/codex_migration_worker.py"])
        self.assertEqual(summary["codex_worker"][0]["status"], "ready")
        self.assertEqual(summary["migration"]["status"], "scout_failed")


if __name__ == "__main__":
    unittest.main()
