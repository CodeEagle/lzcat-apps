# CliRelay

AI CLI Relay - Unified API for Gemini CLI, Claude Code, OpenAI Codex and more.

## Description

CliRelay lets you proxy requests from AI coding tools (Claude Code, Gemini CLI, OpenAI Codex, Amp CLI, etc.) through a single local endpoint. Authenticate once with OAuth, add your API keys — or both — and CliRelay handles the rest.

This is the LazyCat Auto-build version, automatically built from the upstream [kittors/CliRelay](https://github.com/kittors/CliRelay) repository.

## Features

- Advanced API Key Management with CRUD operations
- Precision Tracking with latency tracking
- Multi-Provider Support (OpenAI, Gemini, Claude, Codex, Qwen, iFlow, Vertex)
- Load Balancing & Failover
- Redis Data Persistence
- Management Dashboard

## Usage

After installation, open the LazyCat app entrypoint. The root page serves a static landing page that links to the WebUI hosted behind the `api-` prefixed route.

### Configuration

Edit the persisted config file at: `/lzcapp/var/data/clirelay/config.yaml`

Management UI defaults:

- App entrypoint: `/`
- Dashboard URL: `https://api-<your-app-domain>/management.html`
- Initial management key: `change-me-clirelay-admin-key`
- `remote-management.secret-key` is stored in `/lzcapp/var/data/clirelay/config.yaml`

### Ports

| Port | Description |
|------|-------------|
| 8317 | Main API port |

### Persisted data

- Config: `/lzcapp/var/data/clirelay/config.yaml`
- Auth cache: `/lzcapp/var/data/clirelay/auths`
- Logs: `/lzcapp/var/data/clirelay/logs`

## License

MIT License - See [LICENSE](LICENSE) for details.
