# Crucix

Crucix 是一个本地情报引擎，聚合 27 个 OSINT 数据源，提供实时仪表盘、周期性扫描和可选 LLM 告警。

## 上游项目
- Upstream Repo: calesthio/Crucix
- Homepage: https://github.com/calesthio/Crucix
- License: AGPL-3.0
- Author: Crucix
- Version Strategy: `commit_sha`，当前工作区版本对齐到 `2.0.1`

## 当前迁移骨架
- Build Strategy: `upstream_dockerfile`
- Primary Subdomain: `crucix`
- Image Targets: `crucix`
- Service Port: `3117`

### Services
- `crucix` -> `registry.lazycat.cloud/placeholder/crucix:crucix`

## AIPod

当前未启用 AIPod / AI 服务。

## 环境变量

| 变量名 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- |
| FRED_API_KEY | No | - | From .env.example |
| FIRMS_MAP_KEY | No | - | From .env.example |
| EIA_API_KEY | No | - | From .env.example |
| AISSTREAM_API_KEY | No | - | From .env.example |
| ACLED_EMAIL | No | - | From .env.example |
| ACLED_PASSWORD | No | - | From .env.example |
| CLOUDFLARE_API_TOKEN | No | - | From .env.example |
| PORT | No | 3117 | From .env.example |
| REFRESH_INTERVAL_MINUTES | No | 15 | From .env.example |
| LLM_PROVIDER | No | - | From .env.example |
| LLM_API_KEY | No | - | From .env.example |
| LLM_MODEL | No | - | From .env.example |
| OLLAMA_BASE_URL | No | - | From .env.example |
| TELEGRAM_BOT_TOKEN | No | - | From .env.example |
| TELEGRAM_CHAT_ID | No | - | From .env.example |
| TELEGRAM_CHANNELS | No | - | Optional extra Telegram channels |
| TELEGRAM_POLL_INTERVAL | No | 5000 | Telegram bot polling interval (ms) |
| DISCORD_BOT_TOKEN | No | - | Discord bot token |
| DISCORD_CHANNEL_ID | No | - | Discord alert channel |
| DISCORD_GUILD_ID | No | - | Discord guild ID for instant slash commands |
| DISCORD_WEBHOOK_URL | No | - | Discord webhook fallback |

## 数据目录

| 宿主路径 | 容器路径 | 说明 |
| --- | --- | --- |
| /lzcapp/var/data/crucix/crucix/runs | /app/runs | From compose service crucix |

## 首次启动/验收提醒

- 自动扫描到 compose 文件：docker-compose.yml
- 上游 `Dockerfile`、`docker-compose.yml` 与 `crucix.config.mjs` 均确认服务监听 `3117`。
- 扫描到 env 示例文件：.env.example
- `/api/health` 为官方健康检查端点。
- 运行时写入目录确认是 `/app/runs`。

## 下一步

1. 继续用 `./scripts/local_build.sh crucix --force-build` 做本地 dry-run 构建，确认上游 Dockerfile 能在当前链路下完成镜像构建。
2. 构建通过后让 `run_build.py` 回填真实镜像地址与 `.lazycat-build.json`。
3. 如需上架，再补图标与最终商店文案，并执行安装验收。
