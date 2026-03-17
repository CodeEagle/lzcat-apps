# Design: Consolidate lzcat-registry into lzcat-apps

**Date**: 2026-03-17
**Status**: Implemented

## Goal

Make `lzcat-apps` the single source of truth for all app manifests and build configurations. `lzcat-trigger` reads from and writes back to `lzcat-apps` directly. No individual standalone repos or `lzcat-registry` repo are needed.

## Current State

- `lzcat-apps/apps/<app>/` — app manifests (lzc-manifest.yml, lzc-build.yml, icon.png)
- `lzcat-apps/registry/repos/<app>.json` — build configs (already migrated from lzcat-registry)
- `lzcat-registry/` — legacy registry repo (now duplicate, to be archived)
- `CodeEagle/<app>` — individual standalone repos (lzcat-trigger writes outputs here)
- `lzcat-trigger` — reads config from lzcat-apps, but writes outputs to individual repos

## Target State

- `lzcat-apps` — single source of truth: manifests + registry configs
- `lzcat-trigger` — reads from AND writes back to `lzcat-apps`
- Individual standalone repos — archived after 48h soak period
- `lzcat-registry` — archived after 48h soak period

## Design

### 1. Data Model: Registry JSON Schema

Remove the `repo` field from all registry JSON files. App path is derived from filename by convention:

```
lzcat-apps/registry/repos/paperclip.json → lzcat-apps/apps/paperclip/
```

**Before:**
```json
{
  "repo": "CodeEagle/paperclip",
  "enabled": true,
  "upstream_repo": "paperclipai/paperclip",
  "build_strategy": "upstream_with_target_template"
}
```

**After:**
```json
{
  "enabled": true,
  "upstream_repo": "paperclipai/paperclip",
  "build_strategy": "upstream_with_target_template"
}
```

Filenames in `registry/repos/` already use the simple app name format (e.g., `paperclip.json`). No renaming needed.

**Invariant validation:** `collect_targets.py` must assert that `apps/<stem>/lzc-manifest.yml` exists for every enabled config before any build runs. If the path does not exist, fail fast with a clear error message. This catches any filename/directory mismatch immediately.

### 2. lzcat-trigger Workflow Changes (`update-image.yml`)

**Remove:**
- Step that checks out the individual target repo (e.g., `CodeEagle/paperclip`)
- Step that commits updated manifest back to the individual repo

**Change:**
- `run_build.py` reads manifest from `lzcat-apps/apps/<app>/lzc-manifest.yml` (already checked out)
- `run_build.py` writes updated `lzc-manifest.yml` and `.lazycat-build.json` back to `lzcat-apps/apps/<app>/`
- Commit target: `lzcat-apps` `main` branch
- Before each push: `git pull --rebase origin main` to handle concurrent builds
- Only `image:` lines and `version:` are updated (see Constraint section)

**Unchanged:**
- `.lpk` build and push to `lzcat-artifacts`
- All build strategies (official_image, precompiled_binary, upstream_dockerfile, upstream_with_target_template, target_repo_dockerfile)
- Image build and copy to `registry.lazycat.cloud`

### 3. lzcat-trigger Script Changes

**`collect_targets.py`:**
- Remove use of `repo` field for target determination
- Derive `app_path` from config filename: `paperclip.json` → `apps/paperclip`
- Add validation: assert `apps/<stem>/lzc-manifest.yml` exists; fail fast if not

**`run_build.py`:**
- Remove logic that clones/checks out individual target repos
- Read manifest from already-checked-out `lzcat-apps/apps/<app>/lzc-manifest.yml`
- Update manifest in-place using **regex line replacement** (see Constraint section)
- Write `.lazycat-build.json` to `lzcat-apps/apps/<app>/.lazycat-build.json`
- Do `git pull --rebase origin main` before pushing
- Commit and push to `lzcat-apps` main branch

### 4. `.lazycat-build.json`

Written to `lzcat-apps/apps/<app>/.lazycat-build.json` after each successful build. Committed to the repo as a version tracking artifact.

**Schema:**
```json
{
  "upstream_repo": "paperclipai/paperclip",
  "source_version": "v0.3.1",
  "build_version": "0.3.1",
  "source_commit": "1fd9b4c0d9b9"
}
```

Previously written to individual standalone repos; after this change it lives in `lzcat-apps`.

### 5. Migration Steps

Execute in this order (step 2 before step 1 to avoid a broken window):

1. **Update `lzcat-trigger`**: Deploy new `update-image.yml`, `collect_targets.py`, `run_build.py` that are tolerant of both `repo` present and absent in config JSONs
2. **Verify**: Manually trigger `lzcat-trigger` for one app; confirm it reads/writes `lzcat-apps` correctly and `.lpk` is generated
3. **Remove `repo` field**: Delete `repo` from all `lzcat-apps/registry/repos/*.json` files
4. **Soak period**: Let scheduled builds run for 48 hours; monitor for push conflicts or failures
5. **Archive**: After soak period, archive `lzcat-registry` and all individual app repos on GitHub

## Constraints

**Surgical YAML update (critical):** `run_build.py` must update `lzc-manifest.yml` using **regex line replacement**, not YAML re-serialization. This preserves comments, field ordering, multiline strings, and custom config (e.g., `command:` overrides). The regex targets lines of the form `    image: <value>` within known service blocks, and the `version:` top-level field. All other lines are passed through unchanged.

## Rollback Plan

If verification (step 2) fails:
- Revert `lzcat-trigger` to the previous commit — old behavior is immediately restored
- `lzcat-apps` manifests are unchanged at this point (step 3 has not run yet)

If issues appear during the soak period (step 4):
- Revert `lzcat-trigger` to previous commit
- Run `git revert` on the `lzcat-apps` commits made by the trigger to restore `repo` fields

Individual repos and `lzcat-registry` are **not** archived until step 5, after 48h of successful builds.

## Success Criteria

- `lzcat-trigger` manually triggered build completes for one app
- Updated `lzc-manifest.yml` (image hash + version only, no other changes) committed to `lzcat-apps/apps/<app>/`
- `.lpk` generated and pushed to `lzcat-artifacts`
- No individual app repo touched
- 48h of scheduled builds complete without push conflicts or failures
