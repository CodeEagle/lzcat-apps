# Branch Workspace Auto Migration Design

## Goal

Redesign LazyCat auto migration around clean branch ownership, isolated workspaces, Discord collaboration, required screenshot sets, and mandatory Playground guide generation.

## Source Of Truth

- `main`: completed app artifacts only.
- `template`: migration platform only.
- `migration/<slug>`: one app migration and its long-lived maintenance context.
- Independent control workspace: discovery daemon, queue state, Discord routing, and worker launch control.

## Migration Lifecycle

```text
discover candidate
  -> create Discord channel
  -> create migration/<slug> from template
  -> create worktree under migration.workspace_root
  -> run full_migrate.py in that worktree
  -> build and install LPK
  -> Browser Use acceptance
  -> collect 2 desktop screenshots and 3 mobile screenshots
  -> generate store copy, submission metadata, and Playground guide
  -> publish/list with human confirmation
  -> merge app result to main
  -> merge generic improvements to template
```

## Worker Model

Codex worker default model is `gpt-5.5`. The design prefers fewer, higher-quality migration attempts over cheap repeated repair loops. Small candidate classification can later use a lighter model, but no app should be promoted to build/install based only on a lightweight classifier.

The worker can enter `waiting_for_human` when it needs a product or operational decision. The Discord channel receives the question and options. The human answer is stored back into queue state and included in the next worker prompt.

## Discord Channel Contract

Each migrated repo gets one Discord channel named with the configured prefix and slug, for example `migration-piclaw`.

The channel should contain:

- Initial project card with upstream repo, status, candidate reason, and expected app slug.
- Progress updates as the queue state changes.
- Codex questions and human answers.
- Build, install, Browser Use, screenshot, store metadata, and Playground guide artifact links.
- Final listed/published status.

## Artifact Contract

Every app must generate:

- `apps/<slug>/store-submission/screenshots/desktop/*.png`
- `apps/<slug>/store-submission/screenshots/mobile/*.png`
- `apps/<slug>/store-submission/screenshots/manifest.json`
- `apps/<slug>/playground/tutorial.md`
- `apps/<slug>/playground/cover.png`
- `apps/<slug>/playground/screenshots/*`
- `apps/<slug>/store-submission/submission.json`
- `apps/<slug>/copywriting/store-copy.md`

Minimum screenshot counts are 2 desktop images and 3 mobile viewport images.

## Rewards Checklist

The final migration report must list which official incentive categories the app may qualify for:

- self-hosted app migration
- game server migration
- high-quality Playground guide
- LazyCat account integration bonus
- LazyCat cloud drive right-click integration bonus
- original feature or enhancement follow-up

## GitHub Actions

The `trigger-build.yml` schedule is removed. Builds should be manually triggered, dispatched, or invoked by the control workspace for a specific migration branch.

## LaunchAgent

The existing LaunchAgent must stay stopped until it is replaced by a control service that:

- runs outside `main`
- reads `project-config.json`
- creates per-app worktrees from `template`
- starts Codex/gnhf workers in those worktrees
- posts Discord progress
- never writes half-migrated app artifacts directly into `main`
