# Codex Web

Codex Web is a browser frontend for Codex Desktop. This LazyCat package builds the upstream `0xcaff/codex-web` project from source, bundles the Codex CLI, and exposes the Fastify/WebSocket bridge on port `8214`.

## Upstream

- Repository: https://github.com/0xcaff/codex-web
- License: MIT
- Author: 0xcaff
- Version strategy: upstream commit SHA, packaged as `0.1.2`

## LazyCat Topology

- Service: `codex-web`
- Internal port: `8214`
- Public entry: `/`
- Build strategy: custom Dockerfile from upstream source
- Runtime command: `node /opt/codex-web/src/server/main.js --host 0.0.0.0 --port 8214`

## Persistent Data

- `/lzcapp/var/data/codex-web:/data`
  - `/data/home/.codex` stores Codex CLI authentication and session state.
  - `/data/cache`, `/data/config`, `/data/share`, and `/data/tmp` provide writable XDG and upload paths.
- `/lzcapp/var/data/codex-web/workspace:/workspace`
  - Default working directory visible to Codex sessions inside the container.

## Environment

- `HOME=/data/home`
- `CODEX_HOME=/data/home/.codex`
- `CODEX_CLI_PATH=/usr/local/bin/codex`
- `XDG_CACHE_HOME=/data/cache`
- `XDG_CONFIG_HOME=/data/config`
- `XDG_DATA_HOME=/data/share`
- `TMPDIR=/data/tmp`

Codex Web trusts anyone who can reach the UI. Keep the LazyCat route private or protect it with an external authentication layer.

## First Run

The container includes the Codex CLI, but the CLI still needs to be signed in before real sessions can run. Use a shell inside the installed service and run:

```bash
codex login --device-auth
```

The login state is stored under `/data/home/.codex` and survives package restarts.
