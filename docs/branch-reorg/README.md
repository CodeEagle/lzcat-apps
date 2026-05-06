# Branch reorganization (May 2026)

Goal: deprecate `main`, make `template` the trunk for automation infrastructure
only, and put every per-app artifact on its own `migration/<slug>` branch
forked from `template`.

## Pre-cutover state on origin (all additive, safe)

| Namespace | Count | Purpose |
|---|---|---|
| `archive/<name>-pre-reorg` | 16 | Snapshot of every branch we plan to overwrite or delete |
| `template-clean` | 1 | Proposed new `template`: empty `apps/`, empty registry, single workflow option |
| `staged/migration/<slug>` | 57 | Proposed new `migration/<slug>` branches — each contains exactly one app |

## Source-of-truth per slug

See `manifest.json`. Three buckets:

- **from_main** (44): main has the newer build state for these
- **from_migration_branch** (9): only exist (or are richer) on `migration/<slug>`
- **from_special** (3): `fusion` ← `migrate/fusion`; `hermes-webui` ← `migrate/hermes-webui`; `warp` ← `migration-warp`
- **skipped**: `airi` (already done as proof-of-concept), `ebook2audiobook`, `moltis` (registry stubs only — no apps yet)

## Cutover plan (Phase E)

Steps 1 and 2 ran from the agent session; step 3 (deletions) was blocked by
the sandbox proxy and must be finished locally with `finish_cutover.sh`.

| # | Action | Status |
|---|---|---|
| 1 | Force-push `template` = `template-clean` | DONE |
| 2 | Force-push each `staged/migration/<slug>` → `migration/<slug>` | DONE (57 branches) |
| 3 | Switch default branch to `template` in GitHub Settings → Branches | TODO (run `finish_cutover.sh` step 1, requires `gh auth`) |
| 4 | Delete `migrate/fusion`, `migrate/hermes-webui`, `migration-warp`, `migrate/fix-rebase-conflict`, `template-clean`, all `staged/migration/*`, and `main` | TODO (run `finish_cutover.sh`) |

## Rollback (any time before or after cutover)

```bash
# Restore template
git push origin archive/template-pre-reorg:refs/heads/template --force

# Restore each migration/<slug>
for br in $(git ls-remote --heads origin 'archive/migration-*-pre-reorg' | awk '{print $2}'); do
  base=$(echo "$br" | sed 's|refs/heads/archive/||; s|-pre-reorg$||')
  slug=$(echo "$base" | sed 's|^migration-||')
  git push origin "$br:refs/heads/migration/$slug" --force
done

# Restore main
git push origin archive/main-pre-reorg:refs/heads/main
```

## Why two registry-only stubs are skipped

`ebook2audiobook` and `moltis` are listed in `registry/repos/index.json` but
have no `apps/<slug>/` content yet. The auto-migration pipeline (Phase F,
proposal pending) will create their `migration/<slug>` branches when work
actually starts.
