# multica Upstream Deployment Checklist

## 已确认字段
- PROJECT_NAME: multica
- PROJECT_SLUG: multica
- UPSTREAM_REPO: multica-ai/multica
- UPSTREAM_URL: https://github.com/multica-ai/multica
- HOMEPAGE: https://multica.ai
- LICENSE: Apache-2.0
- AUTHOR: multica-ai
- VERSION: 0.1.14
- IMAGE: TODO
- PORT: 5432
- AI_POD_SERVICE: 无
- AI_POD_SERVICE_NAME: 无
- AI_POD_SERVICE_PORT: 无
- CHECK_STRATEGY: github_release
- BUILD_STRATEGY: upstream_dockerfile

## 预填环境变量
- `POSTGRES_DB`: From compose service postgres (required=False)
- `POSTGRES_USER`: From compose service postgres (required=False)
- `POSTGRES_PASSWORD`: From compose service postgres (required=False)
- `POSTGRES_PORT`: From .env.example (required=False)
- `DATABASE_URL`: From .env.example (required=False)
- `PORT`: From .env.example (required=False)
- `JWT_SECRET`: From .env.example (required=False)
- `MULTICA_SERVER_URL`: From .env.example (required=False)
- `MULTICA_APP_URL`: From .env.example (required=False)
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
- `RESEND_API_KEY`: From .env.example (required=False)
- `RESEND_FROM_EMAIL`: From .env.example (required=False)
- `GOOGLE_CLIENT_ID`: From .env.example (required=False)
- `GOOGLE_CLIENT_SECRET`: From .env.example (required=False)
- `GOOGLE_REDIRECT_URI`: From .env.example (required=False)
- `S3_BUCKET`: From .env.example (required=False)
- `S3_REGION`: From .env.example (required=False)
- `CLOUDFRONT_KEY_PAIR_ID`: From .env.example (required=False)
- `CLOUDFRONT_PRIVATE_KEY_SECRET`: From .env.example (required=False)
- `CLOUDFRONT_PRIVATE_KEY`: From .env.example (required=False)
- `CLOUDFRONT_DOMAIN`: From .env.example (required=False)
- `COOKIE_DOMAIN`: From .env.example (required=False)
- `FRONTEND_PORT`: From .env.example (required=False)
- `FRONTEND_ORIGIN`: From .env.example (required=False)
- `NEXT_PUBLIC_API_URL`: From .env.example (required=False)
- `NEXT_PUBLIC_WS_URL`: From .env.example (required=False)

## 预填数据路径
- `/var/lib/postgresql/data` <= `/lzcapp/var/db/multica/postgres-v4` (From compose service postgres)

## 预填启动说明
- 自动扫描到 compose 文件：docker-compose.yml
- 主服务推断为 `postgres`，入口端口 `5432`。
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
  binds: `/lzcapp/var/db/multica/postgres-v4:/var/lib/postgresql/data`
  environment: `POSTGRES_DB=multica, POSTGRES_USER=multica, POSTGRES_PASSWORD=multica`

## 退出条件
- [ ] 入口、端口、环境变量、真实写路径、初始化命令、数据库/auth 配置全部确认完毕
- [ ] `lzc-manifest.yml` 中的镜像地址已替换为真实的 `registry.lazycat.cloud/...`
- [ ] 构建策略相关文件（Dockerfile / template / content / overlay）已补齐
- [ ] 可以进入预检、构建、下载 `.lpk`、安装验收阶段
