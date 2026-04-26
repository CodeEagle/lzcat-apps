# Discovery Gate AI Review Design

## Goal

Stop the auto-migration service from migrating repositories that are already published, already represented in the local app registry, excluded by discovery rules, or suspicious enough to require AI review before migration.

## Root Cause

LocalAgent candidates are imported as a second discovery source, but they do not currently pass through the same LazyCat store/publication checks as `scout_core`. Existing queue items also keep protected states such as `ready`, `build_failed`, and `browser_failed` even when newer discovery evidence says the repository is already migrated or excluded.

## Design

Add a discovery gate that runs before any queue item can be selected for migration. The gate uses hard rules first:

- If the latest candidate status is `already_migrated` or `excluded`, the queue item becomes `filtered_out`.
- If the source repo matches a published or migrated app in `registry/status/local-publication-status.json`, the item becomes `filtered_out`.
- If the repo or slug matches an existing local app that is not the same active migration workspace, the item becomes `filtered_out`.
- If a queue item is already in `ready`, `build_failed`, `browser_failed`, or `waiting_for_human` but newer evidence says it should be filtered, the service updates it immediately and publishes the Discord status.

For ambiguous projects, add an AI-review state and run a dedicated Codex discovery reviewer when `--enable-codex-worker` is active. The reviewer only decides discovery suitability; it must not run migration/build/publish steps. Its decisions are merged back into the queue as `ready`, `filtered_out`, or `waiting_for_human`.

Workers still request the configured default model first. If the installed Codex CLI rejects that model with a "requires a newer version of Codex" error, the worker retries once with `gpt-5.4` and writes `model-fallback.json` in the task directory.

## Data Flow

1. Status sync refreshes publication status.
2. Before repair or migration work, the queue reconcile applies hard filters to existing items.
3. Existing `discovery_review` items, plus discovery-specific human replies, are routed to `codex_discovery_reviewer.py`.
4. Scout and LocalAgent snapshots are merged.
5. Candidate upsert records latest discovery evidence.
6. Queue reconcile applies hard filters again after upsert.
7. Newly imported `needs_review` items are routed to the discovery reviewer in the same cycle.
8. `select_next_ready_item` only sees items still in `ready`.

## Testing

- Unit test that published upstream repos are filtered out even if the candidate says `portable`.
- Unit test that an existing queue item in `ready` or `build_failed` is downgraded to `filtered_out` when newer evidence says `already_migrated`.
- Unit test that ambiguous candidates enter `discovery_review` instead of `ready`.
- Unit test that Codex discovery reviewer can promote an item to `ready` before migration selection.
- Unit test that discovery-human replies resume the discovery reviewer instead of the migration repair worker.
- Unit test that both Codex workers retry with `gpt-5.4` when the installed CLI cannot run the configured default model.
- Unit test that Discord gets a status update when reconcile changes an item.
