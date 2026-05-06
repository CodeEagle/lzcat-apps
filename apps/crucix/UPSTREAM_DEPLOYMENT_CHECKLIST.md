# Crucix Upstream Deployment Checklist

## 已确认字段
- PROJECT_NAME: Crucix
- PROJECT_SLUG: crucix
- UPSTREAM_REPO: calesthio/Crucix
- UPSTREAM_URL: https://github.com/calesthio/Crucix
- HOMEPAGE: https://github.com/calesthio/Crucix
- LICENSE: AGPL-3.0
- AUTHOR: Crucix
- VERSION: 2.0.1
- IMAGE: Upstream Dockerfile build -> registry.lazycat.cloud/...（构建后回填）
- PORT: 3117
- AI_POD_SERVICE: 无
- AI_POD_SERVICE_NAME: 无
- AI_POD_SERVICE_PORT: 无
- CHECK_STRATEGY: commit_sha
- BUILD_STRATEGY: upstream_dockerfile

## 预填环境变量
- `FRED_API_KEY`: From .env.example (required=False)
- `FIRMS_MAP_KEY`: From .env.example (required=False)
- `EIA_API_KEY`: From .env.example (required=False)
- `AISSTREAM_API_KEY`: From .env.example (required=False)
- `ACLED_EMAIL`: From .env.example (required=False)
- `ACLED_PASSWORD`: From .env.example (required=False)
- `CLOUDFLARE_API_TOKEN`: From .env.example (required=False)
- `PORT`: From .env.example (required=False)
- `REFRESH_INTERVAL_MINUTES`: From .env.example (required=False)
- `LLM_PROVIDER`: From .env.example (required=False)
- `LLM_API_KEY`: From .env.example (required=False)
- `LLM_MODEL`: From .env.example (required=False)
- `OLLAMA_BASE_URL`: From .env.example (required=False)
- `TELEGRAM_BOT_TOKEN`: From .env.example (required=False)
- `TELEGRAM_CHAT_ID`: From .env.example (required=False)
- `TELEGRAM_CHANNELS`: From README/config (required=False)
- `TELEGRAM_POLL_INTERVAL`: From config default 5000 (required=False)
- `DISCORD_BOT_TOKEN`: From README/config (required=False)
- `DISCORD_CHANNEL_ID`: From README/config (required=False)
- `DISCORD_GUILD_ID`: From README/config (required=False)
- `DISCORD_WEBHOOK_URL`: From README/config (required=False)

## 预填数据路径
- `/app/runs` <= `/lzcapp/var/data/crucix/crucix/runs` (From compose service crucix)

## 预填启动说明
- 自动扫描到 compose 文件：docker-compose.yml
- 上游 `docker-compose.yml` 暴露 `${PORT:-3117}:${PORT:-3117}`。
- 上游 `crucix.config.mjs` 读取 `PORT`，默认值为 `3117`。
- 上游 `server.mjs` 提供 `GET /api/health` 健康检查。
- 扫描到 env 示例文件：.env.example
- 扫描到 README：README.md

## 必扫清单
- [ ] Dockerfile / Containerfile / compose / helm / entrypoint / startup script 的真实启动入口
- [ ] README / 部署文档 / `.env.example` / sample config 中声明的环境变量
- [ ] 数据目录、配置目录、缓存目录、上传目录、日志目录、临时目录的真实读写路径
- [ ] 若启用 AIPod，确认 `ai-pod-service/docker-compose.yml` 中的真实镜像、服务端口、`-ai` Host 规则与 `traefik-shared-network` 配置
- [ ] 首次启动初始化命令、迁移命令、建库建表命令、管理员初始化命令
- [ ] 数据库、Redis、对象存储、auth / OAuth / JWT / callback / secret 等外部依赖配置
- [ ] 每个真实目录是否需要预创建、由谁创建、以什么 owner/group/mode 创建

## 当前服务拓扑初稿
- `crucix`
  image: `registry.lazycat.cloud/placeholder/crucix:crucix`
  port: `3117`
  binds: `/lzcapp/var/data/crucix/crucix/runs:/app/runs`

## 退出条件
- [ ] 入口、端口、环境变量、真实写路径、初始化命令、数据库/auth 配置全部确认完毕
- [ ] `lzc-manifest.yml` 中的镜像地址已替换为真实的 `registry.lazycat.cloud/...`
- [ ] 构建策略相关文件（Dockerfile / template / content / overlay）已补齐
- [ ] 可以进入预检、构建、下载 `.lpk`、安装验收阶段
