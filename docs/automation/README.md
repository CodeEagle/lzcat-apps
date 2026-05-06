# 7×24 Auto-Migration Architecture

**Goal**: Continuous, unattended migration of self-hosted GitHub apps onto LazyCat,
running 24×7 via GitHub Actions. Discovery → Triage → Migrate → Verify → Publish.

## Design constraints

1. **Stateless workers, stateful repo.** All state (queue, candidates, dashboard,
   build metadata, migration progress) lives in `template` and `migration/<slug>`
   branches. Workers are throwaway containers.
2. **Branch-per-slug.** Every migration runs against `migration/<slug>` worktree,
   forked from `template`. No worker ever pushes to `template`.
3. **One source of truth per concern.** GitHub Project = work board. Repo
   `registry/` = data. Discord = human ops/notifications. No duplication.
4. **Reuse what exists.** `auto_migration_service.py`, `scout.py`,
   `discord_codex_control.py`, `discovery_gate.py`, `codex_migration_worker.py`
   are already written and tested — wrap them, don't replace.
5. **Failure is normal.** Every state transition is retriable; nothing requires
   human intervention except `waiting_for_human` and `discovery_review`.

## What we already have on `template`

| Layer | Component | File |
|---|---|---|
| Discovery | GitHub Trending / Search / r.jina.ai / Awesome lists | `scripts/scout.py`, `scout_core.py` |
| Discovery | LazyCat App Store crawler | `scripts/status_sync.py`, `scripts/local_agent_bridge.py` |
| Triage | AI-based filtering | `scripts/codex_discovery_reviewer.py`, `scripts/discovery_gate.py` |
| Queue | JSON queue (`registry/auto-migration/queue.json`) | `scripts/auto_migration_service.py` |
| Migrate | One-click upstream → LZC | `scripts/full_migrate.py`, `scripts/bootstrap_migration.py` |
| Build | Docker / podman bridge, lzc-cli wrapping | `scripts/run_build.py`, `scripts/local_build.sh` |
| Worker (codex) | LLM-driven migration repair | `scripts/codex_migration_worker.py` |
| Worker (discord) | Codex control via Discord | `scripts/discord_codex_control.py` |
| Verify | Browser screenshot capture | `scripts/capture_web_screenshot.py`, `web_probe.py` |
| Verify | Functional check | `scripts/functional_checker.py`, `record_browser_acceptance.py` |
| Publish | Store submission generation | `scripts/prepare_store_submission.py`, `copywriter.py` |
| Notify | Discord notifier | `scripts/discord_migration_notifier.py`, `discord_human_replies.py` |
| Dashboard | Daily summary | `scripts/dashboard_daily_summary.py` |

## Gaps to close

| # | Gap | Solution |
|---|---|---|
| 1 | No container image with `lzc-cli` + Docker + `gh` | **`lzcat-migration-runner`** image, published to GHCR |
| 2 | No browser automation image | **`lzcat-bb-browser`** image (Playwright + bb-browser) |
| 3 | No GitHub Project integration | New `scripts/project_board.py` + GraphQL helpers |
| 4 | No cron-driven workflows | New `.github/workflows/auto-migrate-*.yml` chain |
| 5 | `auto_migration_service` is daemon-mode; CI needs `--once` cycle gating | Already supported (`--once`) — just call from workflow |
| 6 | Browser test results don't feed back into queue | Bridge `record_browser_acceptance.py` ↔ project board |
| 7 | Failed migrations need human fix path | `waiting_for_human` already exists; wire to GH Issue |

## Architecture

```
                                      cron(30m)
                                          │
                    ┌─────────────────────┴──────────────────────┐
                    │  workflow: auto-discover.yml                │
                    │  image: lzcat-migration-runner              │
                    │  steps:                                     │
                    │    scout.py + scripts/status_sync.py        │
                    │      → registry/candidates/latest.json      │
                    │    discovery_gate.py + codex_discovery_     │
                    │      reviewer.py                            │
                    │      → registry/auto-migration/queue.json   │
                    │    project_board.py sync                    │
                    │      → GitHub Project items (Inbox)         │
                    └─────────────────────┬──────────────────────┘
                                          │
                                  human approval
                                  (Project: Inbox→Approved)
                                          │
                                      cron(10m)
                                          │
                    ┌─────────────────────┴──────────────────────┐
                    │  workflow: auto-migrate-dispatcher.yml      │
                    │  steps:                                     │
                    │    project_board.py pull-approved (≤2)      │
                    │    → matrix dispatch auto-migrate-worker    │
                    └─────────────────────┬──────────────────────┘
                                          │
                                          ▼
       ┌─────────────────────────────────────────────────────────────┐
       │  workflow: auto-migrate-worker.yml (per slug, max-parallel=2)│
       │  image: lzcat-migration-runner                                │
       │  state machine drives steps:                                 │
       │                                                              │
       │   inbox      ─►  discovery_review (codex_discovery_reviewer) │
       │     │              │                                         │
       │     │              ▼                                         │
       │   approved  ─►  scaffolded   (full_migrate.py / bootstrap)   │
       │     │              │                                         │
       │     │              ▼                                         │
       │     │         build_failed ─► codex_migration_worker.py      │
       │     │              │             (LLM-driven repair)         │
       │     │              ▼                                         │
       │     │          installed (lzc-cli install / podman bridge)   │
       │     │              │                                         │
       │     │              ▼                                         │
       │     │       browser_pending ─► trigger auto-verify.yml       │
       │     │              │                                         │
       │     │      ┌───────┴────────┐                                │
       │     │      ▼                ▼                                │
       │     │ browser_failed    browser_passed                       │
       │     │      │                │                                │
       │     │      └────► waiting_for_human                          │
       │     │                       │                                │
       │     │                       ▼                                │
       │     │                  copy_ready  (copywriter.py)           │
       │     │                       │                                │
       │     │                       ▼                                │
       │     │                publish_ready (prepare_store_submission)│
       │     │                       │                                │
       │     │                       ▼                                │
       │     │                  published                             │
       │     │                                                        │
       │     └─► filtered_out / already_migrated                      │
       └─────────────────────────────────────────────────────────────┘
                                          │
                                          ▼
                    ┌─────────────────────┴──────────────────────┐
                    │  workflow: auto-verify.yml                  │
                    │  image: lzcat-bb-browser                    │
                    │  steps:                                     │
                    │    capture_web_screenshot.py                │
                    │    record_browser_acceptance.py             │
                    │    → updates apps/<slug>/.browser-          │
                    │      acceptance.json                        │
                    │    → posts back to project + Discord        │
                    └─────────────────────────────────────────────┘
                                          │
                            ┌─────────────┴─────────────┐
                            ▼                           ▼
                  trigger-build.yml             dashboard cron
                  (existing,            workflow: auto-dashboard.yml
                   for non-auto-migrate            cron(daily 09:00)
                   manual builds)            dashboard_daily_summary.py
                                              → Discord post
```

## Container images

### `lzcat-migration-runner` — universal worker

```dockerfile
FROM python:3.12-slim

# Build-time inputs
ARG LZC_CLI_VERSION=latest
ARG GH_VERSION=latest
ARG NODE_VERSION=20

# Core toolchain
RUN apt-get update && apt-get install -y --no-install-recommends \
      git curl ca-certificates jq xz-utils \
      build-essential pkg-config \
      docker.io podman buildah skopeo \
    && rm -rf /var/lib/apt/lists/*

# gh CLI
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
      | gpg --dearmor -o /usr/share/keyrings/githubcli.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli.gpg] https://cli.github.com/packages stable main" \
      | tee /etc/apt/sources.list.d/github-cli.list \
    && apt-get update && apt-get install -y gh && rm -rf /var/lib/apt/lists/*

# lzc-cli
RUN curl -fsSL https://lazycat.cloud/install/lzc-cli.sh | bash

# Node (for scripts that need it)
RUN curl -fsSL https://deb.nodesource.com/setup_${NODE_VERSION}.x | bash - \
    && apt-get install -y nodejs

# Claude Code CLI (used by codex_migration_worker for LLM repair)
RUN npm install -g @anthropic-ai/claude-code

# Python deps for scripts/
COPY scripts/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

WORKDIR /repo
ENTRYPOINT ["bash"]
```

Published to: `ghcr.io/codeeagle/lzcat-migration-runner:latest`
Rebuild trigger: weekly cron + on-push to `Dockerfile`.

### `lzcat-bb-browser` — UI verification

```dockerfile
FROM mcr.microsoft.com/playwright:v1.50.0-jammy

# bb-browser binary (installation per LazyCat docs)
ARG BB_BROWSER_VERSION=latest
RUN curl -fsSL "https://lazycat.cloud/install/bb-browser-${BB_BROWSER_VERSION}.tgz" \
      | tar -xz -C /opt/

# ffmpeg for screenshot/video
RUN apt-get update && apt-get install -y ffmpeg python3-pip \
    && rm -rf /var/lib/apt/lists/*

COPY scripts/requirements-browser.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements-browser.txt

WORKDIR /repo
ENTRYPOINT ["bash"]
```

Published to: `ghcr.io/codeeagle/lzcat-bb-browser:latest`

### Image build workflow

`.github/workflows/build-images.yml` — manual / weekly cron:
- Builds both images, multi-arch (amd64 + arm64)
- Pushes to GHCR with `:latest` and `:sha-<short>` tags
- Optionally tag `:stable` after smoke test passes

## GitHub Project schema

**Project name**: `Migration Queue`

**Fields**:

| Field | Type | Source | Notes |
|---|---|---|---|
| Status | Single select | manual + bot | `Inbox` `Approved` `In-Progress` `Browser-Test` `Awaiting-Human` `Published` `Blocked` `Filtered` |
| Slug | Text | bot | mirrors `migration/<slug>` |
| Upstream | URL | bot | github repo |
| Build Strategy | Single select | bot | one of the 5 strategies in CLAUDE.md |
| AI Score | Number | bot (`codex_discovery_reviewer`) | 0–100 |
| Branch | URL | bot | link to `migration/<slug>` |
| PR | URL | bot | link to publish PR (if any) |
| Last Run | Date | bot | last worker timestamp |
| Failures | Text | bot | latest error summary |
| Codex Attempts | Number | bot | `0/N` of `--max-codex-attempts` |

**Automation rules** (set in Project UI):
- New item with `Status=Inbox` not edited in 7 days → auto-set `Status=Filtered`
- `Status=Approved` → triggers worker (via `project_board.py` poll)
- `Status=Awaiting-Human` → notifies Discord `#migration-control`

## State machine ↔ Project Status mapping

The repo's existing state machine (in `auto_migration_service.PROTECTED_STATES`)
maps cleanly to Project columns:

| Repo state | Project Status | Action |
|---|---|---|
| (new candidate) | Inbox | wait for human approval or AI auto-approve threshold |
| `discovery_review` | Inbox | `codex_discovery_reviewer.py` writes back |
| `filtered_out` / `already_migrated*` | Filtered | terminal, retained for audit |
| (approved) | Approved | dispatcher picks up |
| `scaffolded` | In-Progress | scaffold committed to `migration/<slug>` |
| `build_failed` | In-Progress | retry up to `--max-codex-attempts` |
| `installed` | In-Progress | `lzc-cli install` succeeded on dev box |
| `browser_pending` | Browser-Test | dispatched to `auto-verify.yml` |
| `browser_failed` | Awaiting-Human | Discord ping; manual triage |
| `browser_passed` | Awaiting-Human | screenshots + functional check OK; await human go |
| `copy_ready` | Awaiting-Human | copywriting drafted, await human edit |
| `publish_ready` | Awaiting-Human | submission package ready; await human green-light |
| `published` | Published | terminal |
| `waiting_for_human` | Awaiting-Human | catch-all stuck state |

## Workflows to add

All under `template:.github/workflows/`. They use the runner image and `gh` for
Project mutations.

```
auto-discover.yml          cron(30m), workflow_dispatch
  ├─ pulls scout sources, runs discovery_gate
  ├─ writes registry/candidates/latest.json + queue.json
  ├─ commits to template (branch-protected commit via PR-less push token)
  └─ syncs new items to Project (Status=Inbox)

auto-migrate-dispatcher.yml cron(10m)
  ├─ project_board.py list-approved --limit 2
  └─ for slug in approved: gh workflow run auto-migrate-worker --ref template --field slug=<slug>

auto-migrate-worker.yml     workflow_dispatch (input: slug)
  ├─ checkout migration/<slug> in worktree
  ├─ run auto_migration_service --once --slug <slug>
  │     advances state up through `installed`
  ├─ on build_failure: invoke codex_migration_worker (max N attempts)
  ├─ on success: gh workflow run auto-verify --field slug=<slug>
  └─ project_board.py update <slug> Status=...

auto-verify.yml             workflow_dispatch (input: slug)
  ├─ image: lzcat-bb-browser
  ├─ run capture_web_screenshot + record_browser_acceptance
  ├─ commits screenshots to migration/<slug>
  └─ project_board.py update <slug> Status=Browser-Test → Awaiting-Human

auto-publish.yml            workflow_dispatch (input: slug, requires human-trigger)
  ├─ run prepare_store_submission + copywriter
  └─ creates PR migration/<slug> → release notes

auto-dashboard.yml          cron(daily 09:00 CST)
  └─ dashboard_daily_summary.py, post to Discord

build-images.yml            cron(weekly), workflow_dispatch
  └─ builds & pushes lzcat-migration-runner + lzcat-bb-browser
```

## New script: `scripts/project_board.py`

GraphQL wrapper around GitHub Projects v2. Surface:

```bash
project_board.py sync               # candidates/queue → Project items (idempotent)
project_board.py list-approved -n 2 # emit approved slugs (one per line) for matrix
project_board.py update <slug> --status=<status> --field=<key>=<value>
project_board.py upsert <slug> --upstream=<url> --strategy=<s> --score=<n>
project_board.py archive <slug>     # move to Published or Filtered (terminal)
```

Backed by `registry/auto-migration/project-cache.json` so calls are idempotent
across runs (avoids creating duplicate items if API rate-limits hit).

## Required secrets / repo settings

| Secret | Used by | Purpose |
|---|---|---|
| `LZC_CLI_TOKEN` | runner | publish to LazyCat App Store, install on dev box |
| `GH_PAT` (`repo`, `project`, `packages:write`) | runner | push to `migration/*`, mutate Project, push GHCR |
| `ANTHROPIC_API_KEY` | runner | `codex_migration_worker` (LLM repair) |
| `OPENAI_API_KEY` | runner | `codex_discovery_reviewer` (triage) |
| `DISCORD_BOT_TOKEN` | runner | notifications, control plane |
| `LAZYCAT_BOX_DOMAIN` | runner | functional_check, install URL |
| `BB_BROWSER_LICENSE` | bb-browser | if needed |

Repo settings:
- Branch protection on `template`: require PR + status checks for non-bot commits
- Allow `github-actions[bot]` direct push to `template` and `migration/*` for
  state updates (use `GH_PAT` with `contents:write`)
- Enable GitHub Projects v2 at the repo level

## Phased rollout

| Phase | Scope | Time |
|---|---|---|
| **F1** | Build & publish `lzcat-migration-runner` image | 1d |
| **F2** | Write `project_board.py` + GitHub Project setup | 1–2d |
| **F3** | Wire `auto-discover.yml` (read-only — populates Inbox; no migrations yet) | 1d |
| **F4** | Wire `auto-migrate-dispatcher.yml` + `auto-migrate-worker.yml`, gated to 1 slug | 2d |
| **F5** | Build & publish `lzcat-bb-browser` image; wire `auto-verify.yml` | 2–3d |
| **F6** | Wire `auto-publish.yml` (human-triggered only) | 1d |
| **F7** | Raise dispatcher concurrency to 2; turn on cron | 1d |
| **F8** | `auto-dashboard.yml` + Discord control plane wiring | 1d |

Total: ~10 working days from F1 to fully unattended.

## Failure & recovery

| Failure | Detection | Recovery |
|---|---|---|
| Worker container OOM / crash | GHA `failure()` | Project status → `Blocked`, Discord ping |
| `lzc-cli` flaky | `run_build.py` retry loop | Re-run worker via dispatcher next cycle |
| LLM repair exhausted | `codex_attempts >= max` | Project status → `Awaiting-Human` |
| Project API rate limit | GraphQL 429 | `project_board.py` exponential backoff; cache writes |
| Wrong source-of-truth | Discord `/audit <slug>` | Restore from `archive/migration-<slug>-pre-reorg` (still exists) |
| Branch protection block | push 403 | Workflow uses `GH_PAT`, not `GITHUB_TOKEN` |

## Open questions for you to decide

1. **Approval gate**: do we want **AI auto-approve** (above an `AI Score`
   threshold) for trusted source authors, or always require human click to
   move `Inbox`→`Approved`? Suggest: human-only for first month, then
   threshold-based.
2. **Self-hosted runner vs GH-hosted**: `lzc-cli install` on a real LazyCat
   box requires network reach. Do we have a self-hosted runner registered to
   the box's network, or should the runner SSH into the box?
3. **Concurrency**: starting at 2 parallel migrations matches `trigger-build.yml`
   today; bump later?
4. **`registry/dashboard/daily/*` data lifecycle**: keep all daily snapshots
   forever, or rotate/keep last 30 days?
5. **`waiting_for_human` SLA**: Discord ping after 4h? 24h? Auto-revert to
   `Filtered` after a week of no action?
6. **codex-web slug**: do we want it in the migration queue right away or
   leave it as a manual demo?

Once you answer these (or pick the suggested defaults), F1 image build can start.
