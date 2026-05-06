# hermes Upstream Deployment Checklist

## 已确认字段
- PROJECT_NAME: hermes
- PROJECT_SLUG: hermes
- UPSTREAM_REPO: CodeEagle/hermes
- UPSTREAM_URL: https://github.com/CodeEagle/hermes
- HOMEPAGE: https://github.com/CodeEagle/hermes
- LICENSE: 
- AUTHOR: CodeEagle
- VERSION: 0.1.0
- IMAGE: TODO
- PORT: 80
- AI_POD_SERVICE: 无
- AI_POD_SERVICE_NAME: 无
- AI_POD_SERVICE_PORT: 无
- CHECK_STRATEGY: commit_sha
- BUILD_STRATEGY: upstream_dockerfile

## 预填环境变量
- `CHECK_INTERVAL`: From compose service hermes (required=False)
- `WATCHED_REPOS`: From compose service hermes (required=False)
- `HERMES_WEBUI_AGENT_DIR`: Bundled Hermes agent source path for hermes-webui (required=False)
- `OPENAI_API_KEY`: From .env.example (required=False)
- `OPENAI_BASE_URL`: From .env.example (required=False)
- `OPENAI_MODEL`: From .env.example (required=False)
- `OPENROUTER_API_KEY`: From .env.example (required=False)
- `OPENROUTER_MODEL`: From .env.example (required=False)
- `GEMINI_API_KEY`: From .env.example (required=False)
- `GEMINI_BASE_URL`: From .env.example (required=False)
- `GEMINI_MODEL`: From .env.example (required=False)
- `GLM_API_KEY`: From .env.example (required=False)
- `GLM_BASE_URL`: From .env.example (required=False)
- `GLM_MODEL`: From .env.example (required=False)
- `KIMI_API_KEY`: From .env.example (required=False)
- `KIMI_BASE_URL`: From .env.example (required=False)
- `KIMI_MODEL`: From .env.example (required=False)
- `KIMI_CN_API_KEY`: From .env.example (required=False)
- `ARCEEAI_API_KEY`: From .env.example (required=False)
- `ARCEE_BASE_URL`: From .env.example (required=False)
- `ARCEE_MODEL`: From .env.example (required=False)
- `MINIMAX_API_KEY`: From .env.example (required=False)
- `MINIMAX_BASE_URL`: From .env.example (required=False)
- `MINIMAX_MODEL`: From .env.example (required=False)
- `MINIMAX_CN_API_KEY`: From .env.example (required=False)
- `MINIMAX_CN_BASE_URL`: From .env.example (required=False)
- `OPENCODE_ZEN_API_KEY`: From .env.example (required=False)
- `OPENCODE_ZEN_BASE_URL`: From .env.example (required=False)
- `OPENCODE_ZEN_MODEL`: From .env.example (required=False)
- `OPENCODE_GO_API_KEY`: From .env.example (required=False)
- `OPENCODE_GO_BASE_URL`: From .env.example (required=False)
- `OPENCODE_GO_MODEL`: From .env.example (required=False)
- `HF_TOKEN`: From .env.example (required=False)
- `HF_MODEL`: From .env.example (required=False)
- `HERMES_QWEN_BASE_URL`: From .env.example (required=False)
- `QWEN_MODEL`: From .env.example (required=False)
- `XIAOMI_API_KEY`: From .env.example (required=False)
- `XIAOMI_BASE_URL`: From .env.example (required=False)
- `XIAOMI_MODEL`: From .env.example (required=False)
- `EXA_API_KEY`: From .env.example (required=False)
- `PARALLEL_API_KEY`: From .env.example (required=False)
- `FIRECRAWL_API_KEY`: From .env.example (required=False)
- `FAL_KEY`: From .env.example (required=False)
- `HONCHO_API_KEY`: From .env.example (required=False)
- `TERMINAL_ENV`: From .env.example (required=False)
- `TERMINAL_DOCKER_IMAGE`: From .env.example (required=False)
- `TERMINAL_SINGULARITY_IMAGE`: From .env.example (required=False)
- `TERMINAL_MODAL_IMAGE`: From .env.example (required=False)
- `TERMINAL_CWD`: From .env.example (required=False)
- `TERMINAL_TIMEOUT`: From .env.example (required=False)
- `TERMINAL_LIFETIME_SECONDS`: From .env.example (required=False)
- `TERMINAL_SSH_HOST`: From .env.example (required=False)
- `TERMINAL_SSH_USER`: From .env.example (required=False)
- `TERMINAL_SSH_PORT`: From .env.example (required=False)
- `TERMINAL_SSH_KEY`: From .env.example (required=False)
- `SUDO_PASSWORD`: From .env.example (required=False)
- `BROWSERBASE_API_KEY`: From .env.example (required=False)
- `BROWSERBASE_PROJECT_ID`: From .env.example (required=False)
- `BROWSERBASE_PROXIES`: From .env.example (required=False)
- `BROWSERBASE_ADVANCED_STEALTH`: From .env.example (required=False)
- `BROWSER_SESSION_TIMEOUT`: From .env.example (required=False)
- `BROWSER_INACTIVITY_TIMEOUT`: From .env.example (required=False)
- `VOICE_TOOLS_OPENAI_KEY`: From .env.example (required=False)
- `GROQ_API_KEY`: From .env.example (required=False)
- `SLACK_BOT_TOKEN`: From .env.example (required=False)
- `SLACK_APP_TOKEN`: From .env.example (required=False)
- `SLACK_ALLOWED_USERS`: From .env.example (required=False)
- `TELEGRAM_BOT_TOKEN`: From .env.example (required=False)
- `TELEGRAM_ALLOWED_USERS`: From .env.example (required=False)
- `TELEGRAM_HOME_CHANNEL`: From .env.example (required=False)
- `TELEGRAM_HOME_CHANNEL_NAME`: From .env.example (required=False)
- `TELEGRAM_WEBHOOK_URL`: From .env.example (required=False)
- `TELEGRAM_WEBHOOK_PORT`: From .env.example (required=False)
- `TELEGRAM_WEBHOOK_SECRET`: From .env.example (required=False)
- `WHATSAPP_ENABLED`: From .env.example (required=False)
- `WHATSAPP_ALLOWED_USERS`: From .env.example (required=False)
- `EMAIL_ADDRESS`: From .env.example (required=False)
- `EMAIL_PASSWORD`: From .env.example (required=False)
- `EMAIL_IMAP_HOST`: From .env.example (required=False)
- `EMAIL_IMAP_PORT`: From .env.example (required=False)
- `EMAIL_SMTP_HOST`: From .env.example (required=False)
- `EMAIL_SMTP_PORT`: From .env.example (required=False)
- `EMAIL_POLL_INTERVAL`: From .env.example (required=False)
- `EMAIL_ALLOWED_USERS`: From .env.example (required=False)
- `EMAIL_HOME_ADDRESS`: From .env.example (required=False)
- `GATEWAY_ALLOW_ALL_USERS`: From .env.example (required=False)
- `GITHUB_TOKEN`: From .env.example (required=False)
- `GITHUB_APP_ID`: From .env.example (required=False)
- `GITHUB_APP_PRIVATE_KEY_PATH`: From .env.example (required=False)
- `GITHUB_APP_INSTALLATION_ID`: From .env.example (required=False)
- `TINKER_API_KEY`: From .env.example (required=False)
- `WANDB_API_KEY`: From .env.example (required=False)
- `HOST_PORT`: From .env.example (required=False)

## 预填数据路径
- `/data` <= `/lzcapp/var/data/hermes/hermes` (From compose service hermes)

## 预填启动说明
- 自动扫描到 compose 文件：docker-compose.yml
- 主服务推断为 `hermes`，入口端口 `80`。
- 扫描到 env 示例文件：.env.example
- 未扫描到 README

## 必扫清单
- [ ] Dockerfile / Containerfile / compose / helm / entrypoint / startup script 的真实启动入口
- [ ] README / 部署文档 / `.env.example` / sample config 中声明的环境变量
- [ ] 数据目录、配置目录、缓存目录、上传目录、日志目录、临时目录的真实读写路径
- [ ] 若启用 AIPod，确认 `ai-pod-service/docker-compose.yml` 中的真实镜像、服务端口、`-ai` Host 规则与 `traefik-shared-network` 配置
- [ ] 首次启动初始化命令、迁移命令、建库建表命令、管理员初始化命令
- [ ] 数据库、Redis、对象存储、auth / OAuth / JWT / callback / secret 等外部依赖配置
- [ ] 每个真实目录是否需要预创建、由谁创建、以什么 owner/group/mode 创建

## 当前服务拓扑初稿
- `hermes`
  image: `registry.lazycat.cloud/placeholder/hermes:hermes`
  binds: `/lzcapp/var/data/hermes/hermes:/data`
  environment: `CHECK_INTERVAL=1800, WATCHED_REPOS=NousResearch/hermes-agent,joeynyc/hermes-hudui,nesquena/hermes-webui`

## 退出条件
- [ ] 入口、端口、环境变量、真实写路径、初始化命令、数据库/auth 配置全部确认完毕
- [ ] 构建后真实镜像地址已写入 `.lazycat-images.json`，打包阶段从该文件渲染临时 manifest
- [ ] 构建策略相关文件（Dockerfile / template / content / overlay）已补齐
- [ ] 可以进入预检、构建、下载 `.lpk`、安装验收阶段
