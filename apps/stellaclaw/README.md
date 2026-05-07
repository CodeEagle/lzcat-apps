# StellaClaw — LazyCat Migration

Upstream: [JeremyGuo/StellaClaw](https://github.com/JeremyGuo/StellaClaw)

A self-hosted, multi-agent service framework built in Rust. Runs agents as durable long-running services rather than one-shot scripts. Supports Telegram, Web API, and the Stellacode desktop client as conversation surfaces.

## Access

The web channel REST API is exposed at:

```
https://stellaclaw.<your-box>.heiyu.space/
```

API endpoints are available under `/api/`. Authentication uses a Bearer token:

```
Authorization: Bearer <web_token>
```

The `web_token` is generated automatically at install time (random 32-character secret). Retrieve it from the app's deploy parameters in the LazyCat management interface.

## Connecting Stellacode

Configure the Stellacode desktop client to connect to the LazyCat-hosted URL with the `web_token` as the access token.

## Configuring LLM Providers

The default container starts with no LLM models configured. To add providers, mount a custom `config.json` to `/app/config.json` or edit the config inside the container.

Example model entry (add to the `"models"` object in `/app/config.json`):

```json
"main": {
  "provider_type": "open_router_completion",
  "model_name": "openai/gpt-4.1-mini",
  "url": "https://openrouter.ai/api/v1/chat/completions",
  "api_key_env": "OPENROUTER_API_KEY",
  "capabilities": ["chat", "image_in"],
  "token_max_context": 1048576
}
```

Set `available_agent_models` to `["main"]` and pass `OPENROUTER_API_KEY` as an environment variable.

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `STELLACLAW_WEB_TOKEN` | Yes | Bearer token for web channel auth (set via deploy param `web_token`) |
| `STELLACLAW_WORKDIR` | No | Workdir path inside container (default: `/workdir`) |
| `OPENROUTER_API_KEY` | Optional | API key if using OpenRouter models |
| `TELEGRAM_BOT_TOKEN` | Optional | Telegram bot token (requires custom config.json with Telegram channel) |

## Data Paths

| Container path | Host path | Contents |
|---|---|---|
| `/workdir` | `/lzcapp/var/data/stellaclaw` | Conversations, sessions, skills, logs, migration data |

## Build Notes

- Build strategy: `upstream_with_target_template` — Rust workspace compiled from source in a multi-stage Docker build.
- Build time: Expect 10–20 minutes on first build (full Rust workspace compilation).
- check_strategy: `commit_sha` — tracks latest commit; no GitHub releases present.
- Sandbox: disabled (`"mode": "none"`) — bubblewrap is not available inside containers.

## License

**Upstream has no LICENSE file.** Distribution and use terms are undefined. Operator manually approved this migration for E2E testing. Do not publish to the app store until upstream licensing is clarified.
