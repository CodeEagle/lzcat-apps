# LocalAgent Dashboard Discord Replies Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate LocalAgent discovery, daily dashboard reporting, and Discord human replies into the 7x24 migration service.

**Architecture:** Add small focused modules for LocalAgent import, Discord inbound replies, and daily dashboard generation. Wire them into `auto_migration_service.py` through config fields and pure helper functions so each behavior is unit-tested without network calls.

**Tech Stack:** Python standard library, existing unittest suite, Discord REST v10 wrapper, LaunchAgent shell/plist wrappers.

---

### Task 1: LocalAgent Candidate Bridge

**Files:**
- Create: `scripts/local_agent_bridge.py`
- Modify: `scripts/project_config.py`
- Modify: `scripts/auto_migration_service.py`
- Test: `tests/test_local_agent_bridge.py`
- Test: `tests/test_auto_migration_service.py`

- [ ] Write tests for normalizing LocalAgent `projects` entries and `external_sources` entries.
- [ ] Add project config fields for `local_agent.enabled`, `path`, and `snapshot_path`.
- [ ] Implement bridge helpers that read LocalAgent JSON files and write `registry/candidates/local-agent-latest.json`.
- [ ] Merge LocalAgent candidates into `run_cycle` before queue upsert.
- [ ] Run bridge and service tests.

### Task 2: Discord Human Replies

**Files:**
- Create: `scripts/discord_human_replies.py`
- Modify: `scripts/discord_migration_notifier.py`
- Modify: `scripts/auto_migration_service.py`
- Test: `tests/test_discord_human_replies.py`
- Test: `tests/test_auto_migration_service.py`

- [ ] Write tests for listing channel messages, ignoring bot messages, applying a human response, and sending an acknowledgement.
- [ ] Add `DiscordClient.list_messages`.
- [ ] Implement queue mutation for `waiting_for_human` items with channel-bound replies.
- [ ] Let Codex worker resume `waiting_for_human` items once `human_response` exists.
- [ ] Show `human_request` in the Discord progress message.
- [ ] Run Discord and service tests.

### Task 3: Daily Dashboard

**Files:**
- Create: `scripts/dashboard_daily_summary.py`
- Test: `tests/test_dashboard_daily_summary.py`

- [ ] Write tests for queue counts, LocalAgent counts, top candidates, Markdown rendering, and latest report writes.
- [ ] Implement summary builder and CLI.
- [ ] Publish dashboard updates to a fixed Discord channel when token/config exist.
- [ ] Run dashboard tests.

### Task 4: Runtime Wiring

**Files:**
- Modify: `project-config.json`
- Create: `/Users/lincoln/Develop/GitHub/lzcat/auto-migration/run-dashboard-daily-summary.sh`
- Create: `/Users/lincoln/Library/LaunchAgents/cloud.lazycat.auto-migration-dashboard.plist`

- [ ] Enable LocalAgent bridge in project config.
- [ ] Add dashboard wrapper that loads the Discord token from Keychain.
- [ ] Load the daily LaunchAgent.
- [ ] Run full unittest suite.
- [ ] Run one dashboard generation command and inspect outputs.
