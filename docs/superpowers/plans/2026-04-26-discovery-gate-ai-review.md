# Discovery Gate AI Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent duplicate or already-published repos from being migrated and route ambiguous discovery decisions through AI review.

**Architecture:** Add a pure `discovery_gate.py` module that classifies queue items from candidate evidence plus publication index. Wire it into `auto_migration_service.py` immediately after candidate upsert and before item selection.

**Tech Stack:** Python standard library, current unittest suite, existing `publication_status` index and Discord notifier.

---

### Task 1: Queue Reconcile Hard Filters

**Files:**
- Create: `scripts/discovery_gate.py`
- Modify: `scripts/auto_migration_service.py`
- Test: `tests/test_discovery_gate.py`
- Test: `tests/test_auto_migration_service.py`

- [ ] Write failing tests for published repo, already migrated candidate, and existing local app matches.
- [ ] Implement `reconcile_queue_items(queue, publication_index, now)` returning changed item statuses.
- [ ] Call reconcile in `run_cycle` after candidate upsert and before `select_next_ready_item`.
- [ ] Publish Discord updates for changed items.

### Task 2: AI Discovery Review Hold State

**Files:**
- Modify: `scripts/discovery_gate.py`
- Test: `tests/test_discovery_gate.py`

- [ ] Write failing test for a candidate with `status=needs_review` and weak evidence.
- [ ] Implement `discovery_review` state with a `discovery_review.prompt`.
- [ ] Keep `discovery_review` out of migration selection.

### Task 3: Verify and Restart Runtime

**Files:**
- No code changes unless tests reveal a gap.

- [ ] Run targeted tests.
- [ ] Run full unittest suite.
- [ ] Restart `cloud.lazycat.auto-migration` LaunchAgent.
- [ ] Confirm it is running and no already published queue item remains runnable.
