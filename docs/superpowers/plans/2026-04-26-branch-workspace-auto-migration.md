# Branch Workspace Auto Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move AI auto migration to a clean `main` / `template` / `migration/<slug>` operating model with isolated worktrees, Discord progress channels, stronger Codex defaults, screenshot gates, and mandatory Playground guides.

**Architecture:** Add small helper modules instead of rewriting the whole migration pipeline at once. The control service will create worktrees from `template`, run existing migration scripts inside those worktrees, and report status to Discord. Publishing remains gated by Browser Use acceptance, required screenshots, guide artifacts, and human confirmation.

**Tech Stack:** Python standard library, existing unittest suite, Git worktrees, Discord HTTP API, existing LazyCat migration scripts, Codex CLI.

---

### Task 1: Freeze Old Automation And Encode Defaults

**Files:**
- Modify: `.github/workflows/trigger-build.yml`
- Modify: `scripts/codex_migration_worker.py`
- Modify: `scripts/project_config.py`
- Modify: `project-config.json`
- Modify: `scripts/.env.local.example`
- Test: `tests/test_codex_migration_worker.py`
- Test: `tests/test_project_config.py`

- [x] **Step 1: Stop old LaunchAgent**

Run:

```bash
launchctl bootout gui/$(id -u) /Users/lincoln/Library/LaunchAgents/cloud.lazycat.auto-migration.plist
```

Expected: no `auto_migration_service.py` process remains.

- [x] **Step 2: Write failing tests for model and config defaults**

Tests assert `gpt-5.5`, Discord config, screenshot counts, and Playground requirement.

- [x] **Step 3: Implement defaults**

`scripts/codex_migration_worker.py` defaults to `gpt-5.5`; `scripts/project_config.py` exposes `migration` and `discord` config sections.

- [x] **Step 4: Remove main schedule**

Delete `on.schedule` from `.github/workflows/trigger-build.yml`.

### Task 2: Add Migration Worktree Helper

**Files:**
- Create: `scripts/migration_workspace.py`
- Test: `tests/test_migration_workspace.py`

- [x] **Step 1: Write failing worktree tests**

Expected helpers:

```python
migration_branch_name("PicLaw") == "migration/piclaw"
migration_workspace_path(Path("/repo/workspaces"), "piclaw") == Path("/repo/workspaces/migration-piclaw")
```

- [x] **Step 2: Implement helper**

Create pure functions for slug normalization, branch naming, workspace path, and `git worktree add -b migration/<slug> <path> template` command construction.

### Task 3: Discord Channel Control

**Files:**
- Create: `scripts/discord_migration_notifier.py`
- Test: `tests/test_discord_migration_notifier.py`
- Modify: `scripts/auto_migration_service.py`

- [x] **Step 1: Write tests for channel naming and status messages**

Tests should verify `migration-piclaw`, project card content, and final status content.

- [x] **Step 2: Implement Discord API wrapper**

Use `urllib.request` to call Discord with `LZCAT_DISCORD_BOT_TOKEN`. Implement channel lookup/create and message send/edit.

- [x] **Step 3: Store Discord message state**

Queue item stores `discord.channel_id`, `discord.message_id`, and `discord.last_update_at`.

### Task 4: Worktree-Aware Control Service

**Files:**
- Modify: `scripts/auto_migration_service.py`
- Test: `tests/test_auto_migration_service.py`

- [x] **Step 1: Add config fields**

Service config receives `template_branch`, `workspace_root`, `discord_enabled`, and `codex_worker_model`.

- [x] **Step 2: Create migration worktree before migration**

When selecting a ready item, create `migration/<slug>` from `template` in `migration.workspace_root` and run `auto_migrate.py` with `cwd` set to that worktree.

- [x] **Step 3: Preserve old states**

Never write generated app artifacts directly to `main`. Failed and pending states stay attached to the migration branch/worktree.

### Task 5: Human-In-The-Loop Worker State

**Files:**
- Modify: `scripts/codex_migration_worker.py`
- Modify: `scripts/auto_migration_service.py`
- Test: `tests/test_codex_migration_worker.py`
- Test: `tests/test_auto_migration_service.py`

- [x] **Step 1: Add waiting state tests**

Queue item can enter `waiting_for_human` with `human_request.question`, `human_request.options`, and `human_request.created_at`.

- [x] **Step 2: Add prompt contract**

Codex prompt explicitly asks the worker to stop and request human input for product decisions, credentials, upstream ambiguity, listing eligibility, or publish confirmation.

- [ ] **Step 3: Resume after answer**

When `human_response` exists, include it in the next worker prompt and resume the migration item.

### Task 6: Screenshot And Playground Gates

**Files:**
- Modify: `scripts/prepare_store_submission.py`
- Modify: `scripts/copywriter.py`
- Create: `scripts/playground_writer.py`
- Test: `tests/test_prepare_store_submission.py`
- Test: `tests/test_copywriter.py`
- Test: `tests/test_playground_writer.py`

- [x] **Step 1: Enforce screenshot counts**

`publish_ready` requires at least 2 desktop screenshots and 3 mobile screenshots under `apps/<slug>/store-submission/screenshots/`.

- [x] **Step 2: Add Playground writer**

Generate a scenario-based guide with real screenshots, store link, upstream attribution, and practical tips.

- [x] **Step 3: Add reward checklist**

Store submission output includes self-hosted migration, game server, Playground guide, account integration, and cloud drive integration opportunities.

### Task 7: Restart New LaunchAgent

**Files:**
- Modify: `/Users/lincoln/Library/LaunchAgents/cloud.lazycat.auto-migration.plist`
- Test: runtime smoke check

- [ ] **Step 1: Update working directory**

Point the LaunchAgent at the independent control workspace, not the `main` checkout.

- [ ] **Step 2: Enable new flags**

Start with Discord disabled until credentials exist, then enable Discord once `LZCAT_DISCORD_BOT_TOKEN`, guild ID, and category ID are configured.

- [ ] **Step 3: Smoke test**

Run one dry cycle and confirm it creates no app artifacts in `main`.
