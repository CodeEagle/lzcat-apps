# Discovery Gate AI Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent duplicate or already-published repos from being migrated and route ambiguous discovery decisions through AI review.

**Architecture:** Add a pure `discovery_gate.py` module that classifies queue items from candidate evidence plus publication index. Wire it into `auto_migration_service.py` before item selection, then route ambiguous `discovery_review` items through a Codex discovery reviewer.

**Tech Stack:** Python standard library, current unittest suite, existing `publication_status` index and Discord notifier.

---

### Task 1: Queue Reconcile Hard Filters

**Files:**
- Create: `scripts/discovery_gate.py`
- Modify: `scripts/auto_migration_service.py`
- Test: `tests/test_discovery_gate.py`
- Test: `tests/test_auto_migration_service.py`

- [x] Write failing tests for published repo, already migrated candidate, and existing local app matches.
- [x] Implement `reconcile_queue_items(queue, publication_index, now)` returning changed item statuses.
- [x] Call reconcile in `run_cycle` before Codex/migration work and again after candidate upsert.
- [x] Publish Discord updates for changed items.

### Task 2: AI Discovery Review Hold State

**Files:**
- Modify: `scripts/discovery_gate.py`
- Test: `tests/test_discovery_gate.py`

- [x] Write failing test for a candidate with `status=needs_review` and weak evidence.
- [x] Implement `discovery_review` state with a `discovery_review.prompt`.
- [x] Keep `discovery_review` out of migration selection.

### Task 2b: Codex Discovery Reviewer

**Files:**
- Create: `scripts/codex_discovery_reviewer.py`
- Modify: `scripts/auto_migration_service.py`
- Test: `tests/test_codex_discovery_reviewer.py`
- Test: `tests/test_auto_migration_service.py`

- [x] Write failing tests for discovery reviewer command construction and prompt contract.
- [x] Route pre-existing `discovery_review` items to Codex when `--enable-codex-worker` is active.
- [x] Route newly imported `needs_review` candidates to Codex in the same cycle before selection.
- [x] Keep discovery-human replies on the discovery reviewer path instead of the migration-repair worker path.
- [x] Merge reviewer decisions from disk into `ready`, `filtered_out`, or `waiting_for_human`.
- [x] Add runtime fallback from `gpt-5.5` to `gpt-5.4` when the installed Codex CLI rejects the default model.

### Task 3: Verify and Restart Runtime

**Files:**
- No code changes unless tests reveal a gap.

- [x] Run targeted tests.
- [x] Run full unittest suite.
- [x] Restart `cloud.lazycat.auto-migration` LaunchAgent.
- [x] Confirm it is running and no already published queue item remains runnable.
