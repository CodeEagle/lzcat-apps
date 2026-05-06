# hermes

本目录由 `scripts/bootstrap_migration.py` 生成，用于把上游 `CodeEagle/hermes` 初始化为懒猫微服迁移项目。

## 上游项目
- Upstream Repo: CodeEagle/hermes
- Homepage: https://github.com/CodeEagle/hermes
- License: 
- Author: CodeEagle
- Version Strategy: `commit_sha` -> 当前初稿版本 `0.1.0`

## 当前迁移骨架
- Build Strategy: `upstream_dockerfile`
- Primary Subdomain: `hermes`
- Image Targets: `hermes`
- Service Port: `80`

### Services
- `hermes` -> `registry.lazycat.cloud/placeholder/hermes:hermes`

## AIPod

当前未启用 AIPod / AI 服务。

## 环境变量

| 变量名 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- |
| CHECK_INTERVAL | No | 1800 | From compose service hermes |
| WATCHED_REPOS | No | NousResearch/hermes-agent,nesquena/hermes-webui | From compose service hermes |
| HERMES_WEBUI_AGENT_DIR | No | /opt/hermes-agent | Bundled Hermes agent source path for hermes-webui |
| OPENAI_API_KEY | No | - | From .env.example |
| OPENAI_BASE_URL | No | - | From .env.example |
| OPENAI_MODEL | No | - | From .env.example |
| OPENROUTER_API_KEY | No | - | From .env.example |
| OPENROUTER_MODEL | No | - | From .env.example |
| GEMINI_API_KEY | No | - | From .env.example |
| GEMINI_BASE_URL | No | - | From .env.example |
| GEMINI_MODEL | No | - | From .env.example |
| GLM_API_KEY | No | - | From .env.example |
| GLM_BASE_URL | No | - | From .env.example |
| GLM_MODEL | No | - | From .env.example |
| KIMI_API_KEY | No | - | From .env.example |
| KIMI_BASE_URL | No | - | From .env.example |
| KIMI_MODEL | No | - | From .env.example |
| KIMI_CN_API_KEY | No | - | From .env.example |
| ARCEEAI_API_KEY | No | - | From .env.example |
| ARCEE_BASE_URL | No | - | From .env.example |
| ARCEE_MODEL | No | - | From .env.example |
| MINIMAX_API_KEY | No | - | From .env.example |
| MINIMAX_BASE_URL | No | - | From .env.example |
| MINIMAX_MODEL | No | - | From .env.example |
| MINIMAX_CN_API_KEY | No | - | From .env.example |
| MINIMAX_CN_BASE_URL | No | - | From .env.example |
| OPENCODE_ZEN_API_KEY | No | - | From .env.example |
| OPENCODE_ZEN_BASE_URL | No | - | From .env.example |
| OPENCODE_ZEN_MODEL | No | - | From .env.example |
| OPENCODE_GO_API_KEY | No | - | From .env.example |
| OPENCODE_GO_BASE_URL | No | - | From .env.example |
| OPENCODE_GO_MODEL | No | - | From .env.example |
| HF_TOKEN | No | - | From .env.example |
| HF_MODEL | No | - | From .env.example |
| HERMES_QWEN_BASE_URL | No | - | From .env.example |
| QWEN_MODEL | No | - | From .env.example |
| XIAOMI_API_KEY | No | - | From .env.example |
| XIAOMI_BASE_URL | No | - | From .env.example |
| XIAOMI_MODEL | No | - | From .env.example |
| EXA_API_KEY | No | - | From .env.example |
| PARALLEL_API_KEY | No | - | From .env.example |
| FIRECRAWL_API_KEY | No | - | From .env.example |
| FAL_KEY | No | - | From .env.example |
| HONCHO_API_KEY | No | - | From .env.example |
| TERMINAL_ENV | No | - | From .env.example |
| TERMINAL_DOCKER_IMAGE | No | - | From .env.example |
| TERMINAL_SINGULARITY_IMAGE | No | - | From .env.example |
| TERMINAL_MODAL_IMAGE | No | - | From .env.example |
| TERMINAL_CWD | No | - | From .env.example |
| TERMINAL_TIMEOUT | No | - | From .env.example |
| TERMINAL_LIFETIME_SECONDS | No | - | From .env.example |
| TERMINAL_SSH_HOST | No | - | From .env.example |
| TERMINAL_SSH_USER | No | - | From .env.example |
| TERMINAL_SSH_PORT | No | - | From .env.example |
| TERMINAL_SSH_KEY | No | - | From .env.example |
| SUDO_PASSWORD | No | - | From .env.example |
| BROWSERBASE_API_KEY | No | - | From .env.example |
| BROWSERBASE_PROJECT_ID | No | - | From .env.example |
| BROWSERBASE_PROXIES | No | - | From .env.example |
| BROWSERBASE_ADVANCED_STEALTH | No | - | From .env.example |
| BROWSER_SESSION_TIMEOUT | No | - | From .env.example |
| BROWSER_INACTIVITY_TIMEOUT | No | - | From .env.example |
| VOICE_TOOLS_OPENAI_KEY | No | - | From .env.example |
| GROQ_API_KEY | No | - | From .env.example |
| SLACK_BOT_TOKEN | No | - | From .env.example |
| SLACK_APP_TOKEN | No | - | From .env.example |
| SLACK_ALLOWED_USERS | No | - | From .env.example |
| TELEGRAM_BOT_TOKEN | No | - | From .env.example |
| TELEGRAM_ALLOWED_USERS | No | - | From .env.example |
| TELEGRAM_HOME_CHANNEL | No | - | From .env.example |
| TELEGRAM_HOME_CHANNEL_NAME | No | - | From .env.example |
| TELEGRAM_WEBHOOK_URL | No | - | From .env.example |
| TELEGRAM_WEBHOOK_PORT | No | - | From .env.example |
| TELEGRAM_WEBHOOK_SECRET | No | - | From .env.example |
| WHATSAPP_ENABLED | No | - | From .env.example |
| WHATSAPP_ALLOWED_USERS | No | - | From .env.example |
| EMAIL_ADDRESS | No | - | From .env.example |
| EMAIL_PASSWORD | No | - | From .env.example |
| EMAIL_IMAP_HOST | No | - | From .env.example |
| EMAIL_IMAP_PORT | No | - | From .env.example |
| EMAIL_SMTP_HOST | No | - | From .env.example |
| EMAIL_SMTP_PORT | No | - | From .env.example |
| EMAIL_POLL_INTERVAL | No | - | From .env.example |
| EMAIL_ALLOWED_USERS | No | - | From .env.example |
| EMAIL_HOME_ADDRESS | No | - | From .env.example |
| GATEWAY_ALLOW_ALL_USERS | No | - | From .env.example |
| GITHUB_TOKEN | No | - | From .env.example |
| GITHUB_APP_ID | No | - | From .env.example |
| GITHUB_APP_PRIVATE_KEY_PATH | No | - | From .env.example |
| GITHUB_APP_INSTALLATION_ID | No | - | From .env.example |
| TINKER_API_KEY | No | - | From .env.example |
| WANDB_API_KEY | No | - | From .env.example |
| HOST_PORT | No | 80 | From .env.example |

## 数据目录

| 宿主路径 | 容器路径 | 说明 |
| --- | --- | --- |
| /lzcapp/var/data/hermes/hermes | /data | From compose service hermes |

## 首次启动/验收提醒

- 自动扫描到 compose 文件：docker-compose.yml
- 主服务推断为 `hermes`，入口端口 `80`。
- 扫描到 env 示例文件：.env.example
- 未扫描到 README

## 下一步

1. 补完 `UPSTREAM_DEPLOYMENT_CHECKLIST.md`，把真实入口、环境变量、写路径和初始化动作全部核实清楚。
2. 按真实部署拓扑修正 `lzc-manifest.yml`，不要直接沿用占位镜像、端口或命令。
3. 如果是源码构建，补齐 `Dockerfile` / `Dockerfile.template`、`content/`、`overlay_paths` 等资产。
4. 初稿补全后执行 `./scripts/local_build.sh hermes --check-only`，再进入实际构建与验收。
