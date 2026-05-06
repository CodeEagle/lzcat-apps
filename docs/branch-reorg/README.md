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
| 2 | Force-push each `staged/migration/<slug>` → `migration/<slug>` | DONE (57 branches; later +1 for `codex-web` discovered in stray cleanup → 58) |
| 3 | Switch default branch to `template` in GitHub Settings → Branches | DONE |
| 4 | Delete `migrate/fusion`, `migrate/hermes-webui`, `migration-warp`, `migrate/fix-rebase-conflict`, `template-clean`, all `staged/migration/*`, and `main` | DONE |

## Stray-branch cleanup (Phase F)

After cutover, 13 leftover `codex/*`, `feature/*`, `fix/*`, and
`lazycat/*` branches were audited and resolved:

- **5 already merged** into `template` + `migration/<slug>` at cutover.
- **1 discovered new slug** (`codex-web` from `codex/codex-web-lazycat`):
  built `migration/codex-web`. Total: **58 migration branches**.
- **3 had genuine WIP that was adopted** in Phase F follow-up:
  - `codex/migrate-cc-connect` — full `apps/cc-connect` (v1.3.3, LazyCat
    fork, copywriting, store-submission) adopted onto `migration/cc-connect`.
  - `fix/app-profile-env-filter-image-state-validate` — full `apps/hermes`
    (auto-update + hot-update-compat scripts, manifest fixes) adopted
    onto `migration/hermes`.
  - `codex/multica-oidc` — `patch-login-build.js` (Google icon removal)
    merged into `migration/multica`.
- **3 infra commits** from `codex/codex-web-lazycat` cherry-picked onto
  `template`: `35047e8` (AgentHub dashboard takeover), `2e2da31` (build
  metadata branch resolver), `8fe9227` (LocalAgent store search;
  conflicts resolved by keeping fusion + dashboard work).
- **4 confirmed obsolete** (superseded on the new `migration/<slug>`):
  `codex/multica-schema-readiness`, `codex/htmly-build-fix`,
  `codex/htmly-install-fix`, `codex/deer-flow-official-deploy-params`
  (deer-flow migration is 9 versions newer).

All 13 stray dev branches are now safe to delete:

```bash
bash docs/branch-reorg/cleanup_stray_branches.sh
```

`16 archive/*-pre-reorg` retained as rollback. Drop with
`bash docs/branch-reorg/cleanup_stray_branches.sh --drop-archives`
once you're confident the reorg is stable.

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
