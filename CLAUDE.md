# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

LazyCat Apps monorepo — manages 40+ containerized applications migrated to the LazyCat (懒猫微服) platform. Each app is packaged as `.lpk` (LazyCat Package) with deployment manifests, build configs, and Docker images.

## Common Commands

### Local Build (most frequent)
```bash
# Dry-run build (default, no remote side effects)
./scripts/local_build.sh <app-name>

# Check version only, no build
./scripts/local_build.sh <app-name> --check-only

# Force rebuild with Docker
./scripts/local_build.sh <app-name> --force-build

# Quick repackage + install to device (no Docker rebuild)
./scripts/local_build.sh <app-name> --install

# Repackage with Docker rebuild + install
./scripts/local_build.sh <app-name> --install --with-docker

# Pin a specific version
./scripts/local_build.sh <app-name> --target-version 0.3.2

# Full non-dry-run (requires LZC_CLI_TOKEN)
./scripts/local_build.sh <app-name> --no-dry-run
```

### Migration
```bash
# One-click migration from upstream (GitHub URL, owner/repo, docker-compose, Docker image, or local dir)
python3 scripts/full_migrate.py <upstream-address>

# Generate skeleton for new app
./scripts/bootstrap_migration.py --slug <name> --project-name "Name" --upstream-repo owner/repo --build-strategy official_image --service-port 8080

# Complex multi-service: use a JSON spec
./scripts/bootstrap_migration.py --spec docs/migration-spec.example.json
```

### Tests
```bash
pytest tests/                                    # all tests
pytest tests/test_full_migrate.py                # single test file
pytest tests/test_full_migrate.py -k "test_name" # single test
```

### CI
The `trigger-build.yml` workflow runs on workflow_dispatch, repository_dispatch, and on a 12-hour schedule. It builds up to 2 apps in parallel. The app list in the workflow is auto-synced by `scripts/sync_trigger_build_options.py`.

## Architecture

### Directory Layout
- `apps/<name>/` — per-app directory (manifest, build config, Dockerfile, icon, README)
- `registry/repos/` — build configuration JSONs + `index.json` master list
- `scripts/` — Python/Bash build and migration automation
- `.github/workflows/` — CI/CD (trigger-build, update-image, validation)
- `dist/` — build output (.lpk files)

### Per-App Required Files
| File | Purpose |
|------|---------|
| `lzc-manifest.yml` | Deployment manifest (services, env, volumes, healthchecks, proxies) |
| `lzc-build.yml` | Build config (SDK version, manifest path, package output) |
| `icon.png` | App icon |
| `README.md` | Migration notes |

Auto-generated during build:
- `.lazycat-build.json` — build metadata/cache
- `.lazycat-images.json` — built image references

### Registry Config (`registry/repos/<app>.json`)
Key fields: `enabled`, `upstream_repo`, `check_strategy` (github_release / commit_sha), `build_strategy`, `publish_to_store`, `image_targets`, `dependencies`.

### Build Strategies
| Strategy | When |
|----------|------|
| `official_image` | Use upstream's published Docker image directly |
| `upstream_dockerfile` | Clone upstream, use its Dockerfile |
| `target_repo_dockerfile` | Use custom Dockerfile in `apps/<name>/` |
| `upstream_with_target_template` | Clone upstream, apply a Dockerfile.template from `apps/<name>/` |
| `precompiled_binary` | Package precompiled binaries into a container |

### Build Pipeline Flow
1. Detect upstream version (GitHub release/tag/commit SHA)
2. Compare with current build version → skip if unchanged
3. Build Docker image(s) per strategy
4. Copy images to registry (GHCR / registry.lazycat.cloud)
5. Package `.lpk` artifact
6. Optionally publish to LazyCat App Store
7. Update manifest with new image refs, commit changes

### Key Scripts
| Script | Purpose |
|--------|---------|
| `full_migrate.py` | End-to-end migration SOP from upstream to packaged LazyCat app |
| `bootstrap_migration.py` | Generate new app skeleton from CLI args or JSON spec |
| `run_build.py` | Core build orchestrator (version detect, Docker build, package, publish) |
| `collect_targets.py` | Generate GitHub Actions job matrix from registry |
| `local_build.sh` | Local dev build wrapper with dry-run default |

### Environment Variables
Set in `scripts/.env.local` (gitignored):
- `GH_PAT` / `GH_TOKEN` — GitHub API + GHCR push
- `LZC_CLI_TOKEN` — LazyCat CLI token (required for `--no-dry-run` and `--install`)
- `GHCR_USERNAME` — defaults to `GITHUB_REPOSITORY_OWNER`

### Container Engine
Scripts prefer `docker`; if absent, auto-bridge to `podman` (starts podman machine if needed, creates a docker shim).

## Adding a New App

1. Create `apps/<slug>/` with manifest, build config, icon
2. Create `registry/repos/<slug>.json`
3. Append filename to `registry/repos/index.json`
4. Run `python3 scripts/sync_trigger_build_options.py` to update CI workflow options

Or use the one-click migration: `python3 scripts/full_migrate.py <upstream-address>`
