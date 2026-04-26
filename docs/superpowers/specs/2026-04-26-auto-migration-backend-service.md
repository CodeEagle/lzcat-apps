# Auto Migration Backend Service Design

## Goal

Run the LazyCat migration pipeline as a background service that continuously discovers suitable upstream projects, filters duplicate or unsuitable candidates, migrates one app at a time, and only proceeds to copywriting or publishing after Codex Browser Use functional acceptance.

## Control Loop

```text
developer page sync
  -> local publication status snapshot
  -> scout candidate scan
  -> candidate filter and scoring
  -> migration queue
  -> auto_migrate validate-only
  -> build/install
  -> Browser Use acceptance
  -> copywriter/tutorial package
  -> human publish confirmation
```

## Queue States

- `discovered`: found in scout snapshot.
- `filtered_out`: known migrated, excluded category, or unsuitable runtime.
- `ready`: portable and not already published/registered.
- `scaffolded`: `auto_migrate --build-mode validate-only` reached preflight.
- `build_failed`: build or image copy failed.
- `installed`: `.lpk` installed on a LazyCat box.
- `browser_failed`: Browser Use found blocking functional issues.
- `browser_passed`: Browser Use result is pass.
- `copy_ready`: copywriting and tutorial files generated.
- `publish_ready`: Browser Use pass, functional check pass, copywriting present, and human confirmation pending.
- `published`: developer page sync sees the package.

## Candidate Filter

The background service should score and filter before running migrations:

- Drop `already_migrated`, `in_progress`, `excluded`, and weak `needs_review` candidates.
- Prefer normal web services with Dockerfile, compose, official image, or release binary.
- Penalize Cloudflare Workers-only, browser extension, mobile/desktop-native, SDK/library, VPN/proxy, GPU-first, and privileged sandbox runtimes.
- Prefer projects with clear ports, persistent paths, license, and recent upstream activity.
- Allow one migration worker at a time until the failure loop is mature.

## Safety Gates

- Existing `apps/<slug>` blocks migration unless `--allow-existing` is explicitly used.
- `--resume` only bypasses the existing-app guard when `.migration-state.json` exists.
- Publish is blocked unless Browser Use acceptance passes.
- Copywriting/tutorial generation is blocked unless Browser Use acceptance passes.
- Runtime outputs stay under ignored paths: `registry/candidates/`, `registry/status/`, app acceptance files, and app upstream caches.

## Copywriter Stage

Each accepted app must generate:

- `apps/<slug>/copywriting/store-copy.md`
- `apps/<slug>/copywriting/tutorial.md`

The copywriter stage should include:

- app store title, short pitch, Chinese description, English description, keywords
- Browser Use evidence
- screenshot/video checklist
- install-and-first-workflow tutorial
- troubleshooting notes
- "收益素材清单" so every migration has the artifacts needed for review, promotion, and incentive capture

## Initial Scheduler Shape

The first service is `scripts/auto_migration_service.py`. It owns a durable local queue at
`registry/auto-migration/queue.json` and can run once for debugging or continuously as a daemon.

```bash
python3 scripts/auto_migration_service.py --once --dry-run
python3 scripts/auto_migration_service.py --once
python3 scripts/auto_migration_service.py \
  --daemon \
  --interval-seconds 3600 \
  --limit 50 \
  --max-migrations-per-cycle 1
```

Default execution advances portable candidates to `scaffolded` with `auto_migrate.py --build-mode validate-only`.
Real build/install is opt-in:

```bash
python3 scripts/auto_migration_service.py \
  --daemon \
  --enable-build-install \
  --functional-check \
  --box-domain <box-domain>
```

Codex repair is opt-in on top of build/install:

```bash
python3 scripts/auto_migration_service.py \
  --daemon \
  --enable-build-install \
  --functional-check \
  --box-domain <box-domain> \
  --enable-codex-worker \
  --max-codex-attempts 1
```

When a queue item reaches `build_failed` or `browser_failed`, the service can run
`scripts/codex_migration_worker.py`. The worker writes a task bundle under
`registry/auto-migration/codex-tasks/`, runs `codex exec` non-interactively, stores stdout/stderr and the
last Codex message, then writes an IM-friendly Markdown notification under
`registry/auto-migration/notifications/`. A successful Codex run resets the item to `ready`, allowing the
same daemon cycle to retry migration. Failed Codex runs stay capped by `--max-codex-attempts`.

With build/install enabled, the service can move apps to `browser_pending`, `browser_failed`, or `browser_passed`
based on `.functional-check.json`. On later cycles it rechecks `browser_pending` apps, so a Codex Browser Use
acceptance file can be recorded asynchronously and the daemon will continue from there.

When Browser Use passes, the service runs `copywriter.py` and `prepare_store_submission.py`. The app then reaches
`publish_ready`, which means the LPK, copy, tutorial, source attribution, screenshots, and submission checklist are
ready. The final developer-console submit/review action remains a human confirmation gate.

Runtime files are intentionally ignored by git:

- `registry/auto-migration/queue.json`
- `registry/auto-migration/service logs`
- `registry/auto-migration/codex-tasks`
- `registry/auto-migration/notifications`
- `registry/candidates/*.json`
- `registry/status/*.json`
