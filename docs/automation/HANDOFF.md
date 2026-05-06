# 7×24 Auto-Migration — Handoff

> **Resume instruction**: read this file end-to-end, then pick up at the
> section marked **Next: F2** below. The previous session locked all 6
> design decisions; do not re-litigate them.

## Status as of 2026-05-06

| Phase | State | Notes |
|---|---|---|
| Branch reorg | DONE | `template` is trunk; 58 `migration/<slug>` branches; 16 `archive/*-pre-reorg` rollbacks; `main` deleted |
| Stray-branch cleanup (Phase F) | DONE | 3 dev branches' WIP adopted, 4 obsolete; `migration/codex-web` discovered & added |
| F1 — runner / browser images + workflow | DONE | `ghcr.io/codeeagle/lzcat-migration-runner:latest` & `…/lzcat-bb-browser:latest` build via `.github/workflows/build-images.yml` |
| **F2 — `project_board.py` + AI auto-approve** | **NEXT** | Previous session blocked on `GH_PAT` (resume-mode env freeze); covered below |
| F3 — `auto-discover.yml` (read-only Inbox) | pending | |
| F4 — dispatcher + worker (1 slug gated) | pending | |
| F5 — `auto-verify.yml` with bb-browser | pending | |
| F6 — `auto-publish.yml` (human-triggered) | pending | |
| F7 — concurrency=2, cron on | pending | |
| F8 — `auto-dashboard.yml` + 24h SLA reminder | pending | |

## Decisions locked — do not change without explicit user OK

| # | Question | Decision |
|---|---|---|
| 1 | Approval gate | AI auto-approve via Codex / Claude. Score ≥ 0.8 → `Inbox → Approved` automatically. Existing `scripts/codex_discovery_reviewer.py` provides scoring; threshold lives in `project-config.json` under `migration.auto_approve_score_threshold`. |
| 2 | Runner | GitHub-hosted `ubuntu-latest`. `lzc-cli` targets the box's public `*.lazycat.cloud` URL — no self-hosted runner needed. |
| 3 | Concurrency | 2 parallel migrations (matches existing `trigger-build.yml`). Raise later. |
| 4 | Dashboard data | **Permanent retention** of `registry/dashboard/daily/*`. No rotation. |
| 5 | `Awaiting-Human` SLA | 24h Discord ping to `#migration-control`. **No** auto-revert. |
| 6 | `codex-web` slug | Excluded — already in App Store review. Goes in `registry/auto-migration/exclude-list.json`. |

## Existing infrastructure to reuse — DO NOT reimplement

The previous session inventoried all of `scripts/`. Nearly every layer of
the pipeline is already implemented; F2+ is mostly *wiring*, not new
business logic. Reuse:

| Layer | Component | Files |
|---|---|---|
| Discovery | scout / GitHub trending / r.jina.ai / appstore | `scripts/scout.py`, `scripts/scout_core.py`, `scripts/status_sync.py` |
| Triage (AI scoring) | Codex-based reviewer | `scripts/codex_discovery_reviewer.py` (output → `registry/auto-migration/discovery-review-tasks/`) |
| Queue & state machine | `PROTECTED_STATES`, queue.json | `scripts/auto_migration_service.py` (1300+ lines, `--once` already supported) |
| One-click migration | upstream → LZC | `scripts/full_migrate.py`, `scripts/bootstrap_migration.py` |
| LLM repair worker | Codex-driven build-failure repair | `scripts/codex_migration_worker.py` |
| Browser verify | screenshot + functional smoke | `scripts/capture_web_screenshot.py`, `scripts/web_probe.py`, `scripts/functional_checker.py`, `scripts/record_browser_acceptance.py` |
| Discord control plane | already wired | `scripts/discord_codex_control.py`, `scripts/discord_migration_notifier.py`, `scripts/discord_local_agent_commands.py` |
| Publication / store | submission package | `scripts/prepare_store_submission.py`, `scripts/copywriter.py` |
| Dashboard | daily summary | `scripts/dashboard_daily_summary.py` |

Full architecture is in `docs/automation/README.md` (read it first).

## Where things live

| What | Branch | Path |
|---|---|---|
| Trunk (automation infra) | `template` | (default branch) |
| Per-app artifacts | `migration/<slug>` × 58 | `apps/<slug>/` + `registry/repos/<slug>.json` + workflow option |
| Architecture docs | `claude/merge-apps-migration-setup-2OrDV` | `docs/automation/README.md` |
| Workflow skeletons | `claude/merge-apps-migration-setup-2OrDV` | `docs/automation/workflows/auto-{discover,migrate-dispatcher,migrate-worker,verify}.yml` |
| `project_board.py` skeleton | `claude/merge-apps-migration-setup-2OrDV` | `docs/automation/scripts/project_board.py.skeleton` |
| F1 deliverables (live) | `template` | `.github/workflows/build-images.yml`, `.github/automation-images/{migration-runner,bb-browser}.Dockerfile`, `scripts/requirements{,-browser}.txt` |
| Branch-reorg history & rollback | `claude/merge-apps-migration-setup-2OrDV` | `docs/branch-reorg/` |
| This handoff | `claude/merge-apps-migration-setup-2OrDV` | `docs/automation/HANDOFF.md` |

## Next: F2

Goal: GitHub Project v2 bootstrap + AI auto-approve gate + per-slug
exclusion list. All deliverables target `template`.

### Deliverables

1. **`scripts/project_board.py`** — GraphQL wrapper around Projects v2.
   Promote the skeleton at `docs/automation/scripts/project_board.py.skeleton`
   to a real implementation. Subcommands:

   - `bootstrap` — idempotent. Discover or create the `Migration Queue`
     project for `CodeEagle/lzcat-apps`, create the 10 fields per the
     schema in `docs/automation/README.md` (Status, Slug, Upstream, Build
     Strategy, AI Score, Branch, PR, Last Run, Failures, Codex Attempts).
     Cache node IDs in `registry/auto-migration/project-cache.json`.
   - `sync` — reconcile `registry/auto-migration/queue.json` items to
     Project items (idempotent — find by Slug field first).
   - `list-approved -n N --format json` — emit slug list for dispatcher
     matrix.
   - `read <slug> [--field F]` — query.
   - `update <slug> --status=… --field=k=v` — mutate.
   - `upsert <slug> --upstream=URL --strategy=S --score=N` — find or
     create then update.
   - `archive <slug>` — set terminal status (Published / Filtered).

   Implementation calls `gh api graphql` via `subprocess` (existing
   pattern in this repo — no Python GitHub SDK needed). Exponential
   backoff on HTTP 429.

2. **AI auto-approve hook** — extend `scripts/codex_discovery_reviewer.py`
   to write a numeric `score` (0–1) into its review JSON. Add a step to
   `scripts/auto_migration_service.py` (or `project_board.py sync`) that
   reads the score and promotes `Inbox → Approved` when
   `score >= migration.auto_approve_score_threshold` (default 0.8 in
   `project-config.json`).

3. **`registry/auto-migration/exclude-list.json`** — initial:
   ```json
   { "slugs": ["codex-web"] }
   ```
   Both `scripts/discovery_gate.py` and `project_board.py sync` consult
   this list.

4. **pytest** — full coverage for `project_board.py` using mocked
   `subprocess.run` (existing pattern in
   `tests/test_auto_migration_service.py`). Must pass under Python 3.12.

5. **Live bootstrap** — once mock-tested, run once with a real PAT:
   ```bash
   export GH_PAT=github_pat_xxx   # see scopes below
   python3 scripts/project_board.py bootstrap
   ```
   Writes `registry/auto-migration/project-cache.json` (gitignored)
   and any updates to `project-config.json`. Commit + push.

### PAT scopes (fine-grained, owner = user account)

- Repository (`CodeEagle/lzcat-apps`):
  - `Contents`: read+write
  - `Issues`: read+write
  - `Pull requests`: read+write
- Account:
  - **`Projects`: read+write** ← critical
- Expiration: 7 days enough for F2 → F8.

### How to actually get the PAT into the new session

The previous session was stuck because **resume mode freezes env at
session creation** — adding/updating cloud env vars (`GH_PAT`,
`GH_PAT2`, anything) does not propagate into a resume session.

For the next session:
1. Set `GH_PAT` in the cloud-environment UI **before** starting the
   session.
2. Start a **new** (non-resume) session.
3. First thing in the new session, verify:
   ```bash
   echo "${GH_PAT:0:11}"
   ```
   Expect `github_pat_` or `ghp_`. If you see `REPLACE_` or empty, the
   value didn't propagate — open a fresh session again.

### Don't accidentally re-introduce these traps

- **Do not** write GH_PAT into `.claude/settings.local.json`'s `env`
  field. The previous session did, the placeholder shadowed cloud env.
  That file is now gitignored & untracked.
- **Do not** commit `registry/auto-migration/project-cache.json`. It's
  already in `.gitignore` (under `registry/auto-migration/`).

## After F2 — F3 onward (skeletons ready)

Skeletons live at `docs/automation/workflows/`. Order:

- **F3** — `auto-discover.yml`: cron(30m), populates Inbox + AI score; no
  migrations yet.
- **F4** — `auto-migrate-dispatcher.yml` + `auto-migrate-worker.yml`:
  pulls Approved → matrix; gate to 1 slug at first.
- **F5** — `auto-verify.yml`: uses `lzcat-bb-browser` image; hits the
  box's public `*.lazycat.cloud` URL.
- **F6** — `auto-publish.yml`: human-triggered only.
- **F7** — flip cron on; raise concurrency to 2.
- **F8** — `auto-dashboard.yml` + `auto-sla-reminder.yml` (24h ping).

## Rollback if anything breaks

- **Branch reorg**: `docs/branch-reorg/README.md` has the full recipe —
  16 `archive/*-pre-reorg` snapshots can restore template, every
  migration branch, or main.
- **F1 images**: just delete the GHCR tags; rebuild from `template` via
  `gh workflow run build-images.yml`.
- **F2 Project**: `project_board.py archive --all` to terminal-state
  every item, then delete the Project from the GitHub UI; cache file is
  gitignored so no commit needed.

## Open issues to be aware of

- `tests/test_bootstrap_migration.py` and `tests/test_full_migrate.py`
  fail to import on Python 3.11 due to a 3.12+ nested-f-string
  (`scripts/bootstrap_migration.py:1037`). **Not introduced by recent
  work.** CI runs on 3.12, fine.
- 9 tests in `tests/test_discord_codex_control.py` fail on `template`.
  Pre-existing, not introduced by Phase F cherry-picks.
- `bb-browser` is the npm package `bb-browser` (third-party, by
  `epiral/bb-browser`) — **not** a LazyCat-distributed binary. Confirmed
  during F1.
- `lzc-cli` is installed via `npm i -g @lazycatcloud/lzc-cli` — confirmed
  with user.
