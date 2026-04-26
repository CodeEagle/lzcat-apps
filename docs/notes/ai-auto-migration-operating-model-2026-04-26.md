# AI Auto Migration Operating Model

Date: 2026-04-26

## Decisions

- `main` only stores completed apps that are published, ready to publish, or under long-term maintenance.
- `template` stays clean and stores migration platform capability only: scripts, templates, shared docs, tests, workflow definitions, and base registry structure.
- `template` must not store completed app directories.
- Every new migration starts from `template` in a new branch named `migration/<slug>`.
- Every `migration/<slug>` branch runs in its own workspace/worktree.
- `migration/<slug>` branches are retained after listing so follow-up fixes can return to the original migration context.
- Automated discovery runs from an independent control workspace, not from `main`.
- The old `main` scheduled GitHub Actions build is removed.
- The old 7x24 LaunchAgent is stopped until it is rebuilt around the branch/workspace model.
- Codex worker default model is `gpt-5.5`.
- Small candidate classification can use a lighter model later, but app migration should prefer completing correctly in one high-quality pass.
- `gnhf` remains useful for multi-iteration worker orchestration, but every new migration still runs in its own worktree.
- Discord replaces Telegram. One migrated repo gets one Discord channel.
- Discord channels carry progress updates, Codex questions, human answers, final status, and links to artifacts.
- Screenshots are required before publish readiness: at least 2 desktop screenshots and 3 mobile viewport screenshots.
- Playground guide generation is mandatory for every listed app.
- Non-original apps must keep upstream author, upstream URL, and license attribution in store and guide artifacts.

## Branch Flow

```text
template
  -> migration/<slug> in a dedicated worktree
  -> build/install/browser acceptance
  -> screenshots + store copy + Playground guide + attribution
  -> publish/list
  -> app artifacts merge to main
  -> reusable script and rule improvements merge back to template
  -> migration/<slug> remains available for maintenance context
```

## Discord Requirements

To enable Discord integration, provide:

- `LZCAT_DISCORD_BOT_TOKEN`: dedicated bot token, never committed.
- `LZCAT_DISCORD_GUILD_ID`: server ID.
- `LZCAT_DISCORD_CATEGORY_ID`: category where migration channels should be created.
- Bot permissions: `Manage Channels`, `Send Messages`, `Read Message History`, `Manage Messages`.

Non-secret defaults live in `project-config.json`.

## Rewards And Extra Yield

Official references:

- Community incentives: https://developer.lazycat.cloud/store-rule.html
- Store submission guide: https://developer.lazycat.cloud/store-submission-guide.html
- Playground channel: https://lazycat.cloud/playground/

The pipeline should try to capture every applicable reward opportunity:

- High-quality self-hosted app migration: prepare a functional listed app.
- Game server migration: detect whether the app is a game server and whether it qualifies as high-quality.
- Playground guide: generate a real, scenario-based guide with actual screenshots and store link.
- LazyCat account integration: flag apps where OIDC/account integration is practical.
- LazyCat cloud drive context menu integration: flag file tools where right-click integration can add value.
- Original enhancement opportunities: record ideas only when the migration adds meaningful original features beyond packaging.

## Publish Gate

An app cannot move to `publish_ready` unless all are true:

- LPK exists and installs.
- Browser Use functional acceptance passes.
- Desktop screenshots count is at least 2.
- Mobile screenshots count is at least 3.
- Playground guide exists and references real tested steps.
- Store submission metadata includes upstream attribution.
- If credentials are required, ordinary users can obtain them from the store listing or first-run flow.
- The app is not a library, SDK, database-only service, forbidden content, or another non-listable type according to the official submission guide.

## Current Operational Change

The old local LaunchAgent `cloud.lazycat.auto-migration` has been stopped. It should not be restarted until the new control workspace creates per-app `migration/<slug>` worktrees and Discord state updates.
