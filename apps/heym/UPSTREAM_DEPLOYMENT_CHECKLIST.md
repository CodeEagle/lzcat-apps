# heym Upstream Deployment Checklist

## 已确认字段
- PROJECT_NAME: heym
- PROJECT_SLUG: heym
- UPSTREAM_REPO: heymrun/heym
- UPSTREAM_URL: https://github.com/heymrun/heym
- HOMEPAGE: https://heym.run
- LICENSE: 
- AUTHOR: heymrun
- VERSION: 0.0.16
- IMAGE: TODO
- PORT: 4017
- AI_POD_SERVICE: 无
- AI_POD_SERVICE_NAME: 无
- AI_POD_SERVICE_PORT: 无
- CHECK_STRATEGY: github_release
- BUILD_STRATEGY: upstream_dockerfile

## 预填环境变量
- `TZ`: From compose service frontend (required=False)
- `POSTGRES_USER`: From compose service postgres (required=False)
- `POSTGRES_PASSWORD`: From compose service postgres (required=False)
- `POSTGRES_DB`: From compose service postgres (required=False)
- `TIMEZONE`: From compose service backend (required=False)
- `DATABASE_URL`: From compose service backend (required=False)
- `SECRET_KEY`: From compose service backend (required=False)
- `ENCRYPTION_KEY`: From compose service backend (required=False)
- `JWT_ALGORITHM`: From compose service backend (required=False)
- `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`: From compose service backend (required=False)
- `JWT_REFRESH_TOKEN_EXPIRE_DAYS`: From compose service backend (required=False)
- `CORS_ORIGINS`: From compose service backend (required=False)
- `FRONTEND_URL`: From compose service backend (required=False)
- `ALLOW_REGISTER`: From compose service backend (required=False)
- `VITE_API_TARGET`: From compose service frontend (required=False)
- `POSTGRES_HOST`: From .env.example (required=False)
- `POSTGRES_PORT`: From .env.example (required=False)
- `BACKEND_PORT`: From .env.example (required=False)
- `BACKEND_BIND_HOST`: From .env.example (required=False)
- `BACKEND_PROXY_HOST`: From .env.example (required=False)
- `AUTO_REWRITE_LOCAL_DATABASE_HOST`: From .env.example (required=False)
- `FRONTEND_PORT`: From .env.example (required=False)

## 预填数据路径
- `/var/lib/postgresql/data` <= `/lzcapp/var/db/heym/postgres` (From compose service postgres)
- `/app/data/files` <= `/lzcapp/var/data/heym/backend/files` (From compose service backend)

## 预填启动说明
- 自动扫描到 compose 文件：docker-compose.yml
- 主服务推断为 `frontend`，入口端口 `4017`。
- 依赖服务镜像已写入 dependencies，首次完整构建时会自动 copy-image。
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
- `backend`
  image: `registry.lazycat.cloud/placeholder/heym:backend`
  depends_on: `postgres`
  binds: `/lzcapp/var/data/heym/backend/files:/app/data/files`
  environment: `TZ=Europe/Berlin, TIMEZONE=Europe/Berlin, DATABASE_URL=postgresql+asyncpg://${POSTGRES_USER:-postgres}:${POSTGRES_PASSWORD:-postgres}@postgres:5432/${POSTGRES_DB:-heym}, SECRET_KEY, ENCRYPTION_KEY, JWT_ALGORITHM=HS256, JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30, JWT_REFRESH_TOKEN_EXPIRE_DAYS=7, CORS_ORIGINS=http://localhost:4017  # pragma: allowlist secret, FRONTEND_URL=http://localhost:4017  # pragma: allowlist secret, ALLOW_REGISTER=true, OAUTH_ISSUER`
- `frontend`
  image: `registry.lazycat.cloud/placeholder/heym:frontend`
  depends_on: `backend`
  environment: `TZ=Europe/Berlin, VITE_API_TARGET=http://backend:10105`
- `postgres`
  image: `registry.lazycat.cloud/placeholder/heym:postgres`
  binds: `/lzcapp/var/db/heym/postgres:/var/lib/postgresql/data`
  environment: `TZ=Europe/Berlin, POSTGRES_USER=postgres, POSTGRES_PASSWORD=postgres, POSTGRES_DB=heym`

## 退出条件
- [ ] 入口、端口、环境变量、真实写路径、初始化命令、数据库/auth 配置全部确认完毕
- [ ] 构建后真实镜像地址已写入 `.lazycat-images.json`，打包阶段从该文件渲染临时 manifest
- [ ] 构建策略相关文件（Dockerfile / template / content / overlay）已补齐
- [ ] 可以进入预检、构建、下载 `.lpk`、安装验收阶段
