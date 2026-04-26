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

For ambiguous projects, add an AI-review holding state. The first implementation only creates the state and prompt bundle; it does not let ambiguous candidates proceed automatically. The Codex worker can later be used to fill `discovery_review.result` with `migrate`, `skip`, or `needs_human`.

## Data Flow

1. Status sync refreshes publication status.
2. Scout and LocalAgent snapshots are merged.
3. Candidate upsert records latest discovery evidence.
4. Queue reconcile applies hard filters to all queue items before selection.
5. Items requiring AI review move to `discovery_review`.
6. `select_next_ready_item` only sees items still in `ready`.

## Testing

- Unit test that published upstream repos are filtered out even if the candidate says `portable`.
- Unit test that an existing queue item in `ready` or `build_failed` is downgraded to `filtered_out` when newer evidence says `already_migrated`.
- Unit test that ambiguous candidates enter `discovery_review` instead of `ready`.
- Unit test that Discord gets a status update when reconcile changes an item.
