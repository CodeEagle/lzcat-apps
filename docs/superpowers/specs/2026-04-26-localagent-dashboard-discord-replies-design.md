# LocalAgent Dashboard Discord Replies Design

## Goal

Add LocalAgent as an input source for the AI migration pipeline, publish a daily migration dashboard, and let the user answer Codex worker questions directly inside the per-repo Discord channel.

## Architecture

`lzcat-apps` remains the source of truth for migration state. LocalAgent is treated as a read-only candidate source: the bridge reads LocalAgent data, normalizes candidates into the existing candidate snapshot shape, and lets `auto_migration_service.py` upsert them into `registry/auto-migration/queue.json`.

Discord remains the operator surface. Outbound messages continue to update one progress message per app channel. Inbound replies are polled from those app channels when a queue item is `waiting_for_human`; the first human message after the progress message is written to the queue as `human_response`, acknowledged in Discord, and then picked up by the Codex worker on the next pass.

The daily dashboard is a separate command and LaunchAgent. It reads queue state, publication status, candidate snapshots, and LocalAgent bridge output, writes Markdown/JSON reports under `registry/dashboard/`, and updates a fixed Discord dashboard channel. It must not block the 7x24 migration daemon.

## Data Flow

1. LocalAgent writes `data/state.json` and `data/external_sources.json`.
2. `local_agent_bridge.py` reads those files and writes `registry/candidates/local-agent-latest.json`.
3. `auto_migration_service.py` loads both the normal scout snapshot and the LocalAgent snapshot, then upserts candidates into the queue.
4. If Codex worker needs help, it records `state=waiting_for_human` plus `human_request`.
5. Discord progress update shows the question.
6. The service polls the app channel. A non-bot reply becomes `human_response`.
7. Codex worker receives the queue item with `human_response` and resumes.
8. `dashboard_daily_summary.py` writes the daily report and publishes a Discord dashboard update.

## Boundaries

- LocalAgent is not allowed to mutate the migration queue directly.
- Discord inbound replies are only accepted from the app channel already attached to that queue item.
- Bot messages are ignored.
- The daily dashboard has its own LaunchAgent so reporting failures do not stop migration work.
- Template branch stays clean; migration work continues in `migration/<slug>` worktrees.

## Testing

- Unit test LocalAgent project and external source normalization.
- Unit test candidate snapshot merging in the migration service.
- Unit test Discord inbound polling, bot-message filtering, queue mutation, and acknowledgement.
- Unit test daily dashboard JSON/Markdown output.
- Run the full Python unittest suite before restarting LaunchAgents.
