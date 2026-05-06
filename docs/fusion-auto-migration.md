# Fusion 7x24 Auto Migration

This runbook wires the `lzcat-apps` discovery, review, migration, repair, Browser Use acceptance, copywriting, and publish-prep pipeline into the Fusion deployment at:

```text
https://fusion.rx79.heiyu.space
```

## Current Runtime Shape

- `scripts/auto_migration_service.py` owns the queue and migration control loop.
- `scripts/scout.py` discovers candidates.
- `scripts/discovery_gate.py` filters known-published and unsuitable candidates.
- `scripts/codex_discovery_reviewer.py` reviews ambiguous candidates before migration.
- `scripts/auto_migrate.py` / `scripts/full_migrate.py` migrate candidates.
- `scripts/codex_migration_worker.py` repairs failed build or browser-acceptance items.
- `scripts/functional_checker.py`, `scripts/copywriter.py`, and `scripts/prepare_store_submission.py` advance accepted apps toward publish readiness.
- `scripts/fusion_auto_migration.py` renders or starts the Fusion-oriented 7x24 daemon command.

## One-Cycle Smoke Test

```bash
python3 scripts/fusion_auto_migration.py \
  --once \
  --dry-run \
  --box-domain rx79.heiyu.space \
  --print-command
```

To execute one dry-run cycle:

```bash
python3 scripts/fusion_auto_migration.py \
  --once \
  --dry-run \
  --box-domain rx79.heiyu.space
```

## Foreground Daemon

```bash
python3 scripts/fusion_auto_migration.py \
  --box-domain rx79.heiyu.space \
  --interval-seconds 3600
```

The wrapper loads `scripts/.env.local`, uses `../migration-workspaces` for isolated `migration/<slug>` worktrees, enables build/install, enables functional checks against `rx79.heiyu.space`, and enables Codex repair workers.

## LaunchAgent Plist

Render the plist without installing it:

```bash
python3 scripts/fusion_auto_migration.py --print-launchd-plist
```

Write it to `~/Library/LaunchAgents/cloud.lazycat.auto-migration.plist`:

```bash
python3 scripts/fusion_auto_migration.py --write-launchd-plist
```

Loading the LaunchAgent changes the local machine startup state and should be done explicitly:

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/cloud.lazycat.auto-migration.plist
launchctl kickstart -k gui/$(id -u)/cloud.lazycat.auto-migration
```

Logs are written under:

```text
registry/auto-migration/logs/launchd.out.log
registry/auto-migration/logs/launchd.err.log
```

## Fusion Project Setup

Inside Fusion, the project repository should have a Git remote pointing at:

```text
https://github.com/CodeEagle/lzcat-apps.git
```

The Fusion terminal can verify this with:

```bash
git remote -v
```

If the remote is missing:

```bash
git remote add origin https://github.com/CodeEagle/lzcat-apps.git
```

Fusion can then inspect the project, import GitHub issues or PRs when GitHub credentials are connected, and keep manual AI-planning tasks alongside the background daemon state.
