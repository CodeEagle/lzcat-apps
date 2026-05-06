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

Run only after the staged branches have been reviewed.

```bash
# 1. Force-push template = template-clean
git push origin template-clean:template --force

# 2. Rename each staged/migration/<slug> -> migration/<slug>
for br in $(git ls-remote --heads origin 'staged/migration/*' | awk '{print $2}' | sed 's|refs/heads/||'); do
  slug="${br#staged/migration/}"
  git push origin "$br:refs/heads/migration/$slug" --force
  git push origin --delete "$br"
done

# 3. Delete obsolete branches
git push origin --delete migrate/fusion migrate/hermes-webui migration-warp migrate/fix-rebase-conflict

# 4. Switch default branch to "template" in GitHub Settings -> Branches
# 5. Delete main
git push origin --delete main
```

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
