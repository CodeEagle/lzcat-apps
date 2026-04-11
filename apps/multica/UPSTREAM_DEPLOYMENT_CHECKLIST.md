# Multica Upstream Deployment Checklist

## 已确认字段
- PROJECT_NAME: Multica
- PROJECT_SLUG: multica
- UPSTREAM_REPO: multica-ai/multica
- UPSTREAM_URL: https://github.com/multica-ai/multica
- HOMEPAGE: https://github.com/multica-ai/multica
- LICENSE: 
- AUTHOR: TODO
- VERSION: 0.1.0
- IMAGE: TODO
- PORT: 3000
- AI_POD_SERVICE: 无
- AI_POD_SERVICE_NAME: 无
- AI_POD_SERVICE_PORT: 无
- CHECK_STRATEGY: github_release
- BUILD_STRATEGY: upstream_dockerfile

## 预填环境变量
- `POSTGRES_DB`: From compose service postgres (required=False)
- `POSTGRES_USER`: From compose service postgres (required=False)
- `POSTGRES_PASSWORD`: From compose service postgres (required=False)
- `DATABASE_URL`: From compose service backend (required=False)
- `PORT`: From compose service backend (required=False)
- `JWT_SECRET`: From compose service backend (required=False)
- `FRONTEND_ORIGIN`: From compose service backend (required=False)
- `CORS_ALLOWED_ORIGINS`: From compose service backend (required=False)
- `RESEND_API_KEY`: From compose service backend (required=False)
- `RESEND_FROM_EMAIL`: From compose service backend (required=False)
- `GOOGLE_CLIENT_ID`: From compose service backend (required=False)
- `GOOGLE_CLIENT_SECRET`: From compose service backend (required=False)
- `GOOGLE_REDIRECT_URI`: From compose service backend (required=False)
- `S3_BUCKET`: From compose service backend (required=False)
- `S3_REGION`: From compose service backend (required=False)
- `CLOUDFRONT_DOMAIN`: From compose service backend (required=False)
- `CLOUDFRONT_KEY_PAIR_ID`: From compose service backend (required=False)
- `CLOUDFRONT_PRIVATE_KEY`: From compose service backend (required=False)
- `COOKIE_DOMAIN`: From compose service backend (required=False)
- `MULTICA_APP_URL`: From compose service backend (required=False)
- `HOSTNAME`: From compose service frontend (required=False)
- `POSTGRES_PORT`: From .env.example (required=False)
- `MULTICA_SERVER_URL`: From .env.example (required=False)
- `MULTICA_DAEMON_CONFIG`: From .env.example (required=False)
- `MULTICA_WORKSPACE_ID`: From .env.example (required=False)
- `MULTICA_DAEMON_ID`: From .env.example (required=False)
- `MULTICA_DAEMON_DEVICE_NAME`: From .env.example (required=False)
- `MULTICA_DAEMON_POLL_INTERVAL`: From .env.example (required=False)
- `MULTICA_DAEMON_HEARTBEAT_INTERVAL`: From .env.example (required=False)
- `MULTICA_CODEX_PATH`: From .env.example (required=False)
- `MULTICA_CODEX_MODEL`: From .env.example (required=False)
- `MULTICA_CODEX_WORKDIR`: From .env.example (required=False)
- `MULTICA_CODEX_TIMEOUT`: From .env.example (required=False)
- `NEXT_PUBLIC_GOOGLE_CLIENT_ID`: From .env.example (required=False)
- `CLOUDFRONT_PRIVATE_KEY_SECRET`: From .env.example (required=False)
- `FRONTEND_PORT`: From .env.example (required=False)
- `NEXT_PUBLIC_API_URL`: From .env.example (required=False)
- `NEXT_PUBLIC_WS_URL`: From .env.example (required=False)

## 预填数据路径
- `/var/lib/postgresql/data` <= `/lzcapp/var/db/multica/postgres` (From compose service postgres)

## 预填启动说明
- 自动扫描到 compose 文件：docker-compose.selfhost.yml
- 主服务推断为 `frontend`，入口端口 `3000`。
- 依赖服务镜像已写入 dependencies，首次完整构建时会自动 copy-image。
- 扫描到 env 示例文件：.env.example
- 扫描到 README：README.md, README.zh-CN.md

## 必扫清单
- [ ] Dockerfile / Containerfile / compose / helm / entrypoint / startup script 的真实启动入口
- [ ] README / 部署文档 / `.env.example` / sample config 中声明的环境变量
- [ ] 数据目录、配置目录、缓存目录、上传目录、日志目录、临时目录的真实读写路径
- [ ] 若启用 AIPod，确认 `ai-pod-service/docker-compose.yml` 中的真实镜像、服务端口、`-ai` Host 规则与 `traefik-shared-network` 配置
- [ ] 首次启动初始化命令、迁移命令、建库建表命令、管理员初始化命令
- [ ] 数据库、Redis、对象存储、auth / OAuth / JWT / callback / secret 等外部依赖配置
- [ ] 每个真实目录是否需要预创建、由谁创建、以什么 owner/group/mode 创建

## 当前服务拓扑初稿
- `postgres`
  image: `registry.lazycat.cloud/placeholder/multica:postgres`
  binds: `/lzcapp/var/db/multica/postgres:/var/lib/postgresql/data`
  environment: `POSTGRES_DB=multica, POSTGRES_USER=multica, POSTGRES_PASSWORD=multica`
- `backend`
  image: `registry.lazycat.cloud/placeholder/multica:backend`
  depends_on: `postgres`
  environment: `DATABASE_URL=postgres://${POSTGRES_USER:-multica}:${POSTGRES_PASSWORD:-multica}@postgres:5432/${POSTGRES_DB:-multica}?sslmode=disable, PORT=8080, JWT_SECRET=change-me-in-production, FRONTEND_ORIGIN=http://localhost:3000, CORS_ALLOWED_ORIGINS=, RESEND_API_KEY=, RESEND_FROM_EMAIL=noreply@multica.ai, GOOGLE_CLIENT_ID=, GOOGLE_CLIENT_SECRET=, GOOGLE_REDIRECT_URI=http://localhost:3000/auth/callback, S3_BUCKET=, S3_REGION=us-west-2, CLOUDFRONT_DOMAIN=, CLOUDFRONT_KEY_PAIR_ID=, CLOUDFRONT_PRIVATE_KEY=, COOKIE_DOMAIN=, MULTICA_APP_URL=http://localhost:3000`
- `frontend`
  image: `registry.lazycat.cloud/placeholder/multica:frontend`
  depends_on: `backend`
  environment: `HOSTNAME=0.0.0.0`

## 退出条件
- [ ] 入口、端口、环境变量、真实写路径、初始化命令、数据库/auth 配置全部确认完毕
- [ ] 构建后真实镜像地址已写入 `.lazycat-images.json`，打包阶段从该文件渲染临时 manifest
- [ ] 构建策略相关文件（Dockerfile / template / content / overlay）已补齐
- [ ] 可以进入预检、构建、下载 `.lpk`、安装验收阶段
