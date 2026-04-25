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

The first service can be a small Python daemon or scheduled command:

```bash
python3 scripts/status_sync.py
python3 scripts/scout.py scan --limit 50
python3 scripts/auto_migrate.py --from-candidates --build-mode validate-only
```

After validate-only succeeds, the service should stop and wait for an operator or a separate worker to approve real build/install. This keeps the early loop safe while still automating discovery and scaffolding.
