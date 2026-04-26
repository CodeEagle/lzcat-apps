# AgentsMesh Upstream Deployment Checklist

## 已确认字段
- PROJECT_NAME: AgentsMesh
- PROJECT_SLUG: agentsmesh
- UPSTREAM_REPO: AgentsMesh/AgentsMesh
- UPSTREAM_URL: https://github.com/AgentsMesh/AgentsMesh
- HOMEPAGE: https://agentsmesh.ai
- LICENSE: 
- AUTHOR: AgentsMesh
- VERSION: 0.29.0
- IMAGE: TODO
- PORT: 80
- AI_POD_SERVICE: 无
- AI_POD_SERVICE_NAME: 无
- AI_POD_SERVICE_PORT: 无
- CHECK_STRATEGY: github_release
- BUILD_STRATEGY: upstream_dockerfile

## 预填环境变量
- `POSTGRES_USER`: From compose service postgres (required=False)
- `POSTGRES_PASSWORD`: From compose service postgres (required=False)
- `POSTGRES_DB`: From compose service postgres (required=False)
- `MINIO_ROOT_USER`: From compose service minio (required=False)
- `MINIO_ROOT_PASSWORD`: From compose service minio (required=False)
- `MINIO_API_CORS_ALLOW_ORIGIN`: From compose service minio (required=False)
- `PRIMARY_DOMAIN`: From compose service relay (required=False)
- `USE_HTTPS`: From compose service relay (required=False)
- `DB_HOST`: From compose service backend (required=False)
- `DB_PORT`: From compose service backend (required=False)
- `DB_USER`: From compose service backend (required=False)
- `DB_PASSWORD`: From compose service backend (required=False)
- `DB_NAME`: From compose service backend (required=False)
- `DB_SSLMODE`: From compose service backend (required=False)
- `REDIS_URL`: From compose service backend (required=False)
- `JWT_SECRET`: From compose service relay (required=False)
- `INTERNAL_API_SECRET`: From compose service relay (required=False)
- `SERVER_ADDRESS`: From compose service relay (required=False)
- `DEBUG`: From compose service relay (required=False)
- `CORS_ALLOWED_ORIGINS`: From compose service backend (required=False)
- `LOG_LEVEL`: From compose service backend (required=False)
- `LOG_FORMAT`: From compose service backend (required=False)
- `LOG_FILE`: From compose service backend (required=False)
- `EMAIL_PROVIDER`: From compose service backend (required=False)
- `STORAGE_ENDPOINT`: From compose service backend (required=False)
- `STORAGE_PUBLIC_ENDPOINT`: From compose service backend (required=False)
- `STORAGE_REGION`: From compose service backend (required=False)
- `STORAGE_BUCKET`: From compose service backend (required=False)
- `STORAGE_ACCESS_KEY`: From compose service backend (required=False)
- `STORAGE_SECRET_KEY`: From compose service backend (required=False)
- `STORAGE_USE_SSL`: From compose service backend (required=False)
- `STORAGE_USE_PATH_STYLE`: From compose service backend (required=False)
- `STORAGE_MAX_FILE_SIZE`: From compose service backend (required=False)
- `STORAGE_ALLOWED_TYPES`: From compose service backend (required=False)
- `PKI_CA_CERT_FILE`: From compose service backend (required=False)
- `PKI_CA_KEY_FILE`: From compose service backend (required=False)
- `PKI_VALIDITY_DAYS`: From compose service backend (required=False)
- `GRPC_ADDRESS`: From compose service backend (required=False)
- `GRPC_PUBLIC_ENDPOINT`: From compose service backend (required=False)
- `ADMIN_ENABLED`: From compose service backend (required=False)
- `NODE_ENV`: From compose service web-admin (required=False)
- `WS_READ_BUFFER_SIZE`: From compose service relay (required=False)
- `WS_WRITE_BUFFER_SIZE`: From compose service relay (required=False)
- `BACKEND_URL`: From compose service relay (required=False)
- `RELAY_ID`: From compose service relay (required=False)
- `RELAY_REGION`: From compose service relay (required=False)
- `RELAY_CAPACITY`: From compose service relay (required=False)
- `SESSION_KEEP_ALIVE_DURATION`: From compose service relay (required=False)
- `JWT_EXPIRATION_HOURS`: From .env.example (required=False)
- `DEPLOYMENT_TYPE`: From .env.example (required=False)
- `ALIPAY_SANDBOX`: From .env.example (required=False)
- `WECHAT_SANDBOX`: From .env.example (required=False)
- `NEXT_PUBLIC_GITLAB_SSO_URL`: From .env.example (required=False)
- `SERVER_HOST`: From .env.example (required=False)
- `HTTP_PORT`: From .env.example (required=False)
- `GRPC_PORT`: From .env.example (required=False)
- `VERSION`: From .env.example (required=False)
- `COMPOSE_PROJECT_NAME`: From .env.example (required=False)
- `MINIO_CONSOLE_PORT`: From .env.example (required=False)
- `MINIO_API_PORT`: From .env.example (required=False)

## 预填数据路径
- `/var/lib/postgresql/data` <= `/lzcapp/var/db/agentsmesh/postgres` (From compose service postgres)
- `/data` <= `/lzcapp/var/data/agentsmesh/redis` (From compose service redis)
- `/data` <= `/lzcapp/var/data/agentsmesh/minio` (From compose service minio)

## 预填启动说明
- 自动扫描到 compose 文件：deploy/selfhost/docker-compose.yml
- 主服务推断为 `traefik`，入口端口 `80`。
- 依赖服务镜像已写入 dependencies，首次完整构建时会自动 copy-image。
- 扫描到 env 示例文件：.env.example, .env.example, .env.example
- 扫描到 README：README.md, README.md, README.md
- 扫描到上游图标：web/public/icons/icon-512.png

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
  image: `registry.lazycat.cloud/placeholder/agentsmesh:backend`
  depends_on: `postgres, redis`
  environment: `PRIMARY_DOMAIN, USE_HTTPS=false, DB_HOST=postgres, DB_PORT=5432, DB_USER=agentsmesh, DB_PASSWORD, DB_NAME=agentsmesh, DB_SSLMODE=disable, REDIS_URL=redis://redis:6379, JWT_SECRET, INTERNAL_API_SECRET, SERVER_ADDRESS=:8080, DEBUG=false, CORS_ALLOWED_ORIGINS=*, LOG_LEVEL=info, LOG_FORMAT=json, LOG_FILE=/dev/stdout, EMAIL_PROVIDER=console, STORAGE_ENDPOINT=minio:9000, STORAGE_PUBLIC_ENDPOINT=${SERVER_HOST}:${MINIO_API_PORT:-9000}, STORAGE_REGION=us-east-1, STORAGE_BUCKET=agentsmesh, STORAGE_ACCESS_KEY=minioadmin, STORAGE_SECRET_KEY=__CHANGE_ME__, STORAGE_USE_SSL=false, STORAGE_USE_PATH_STYLE=true, STORAGE_MAX_FILE_SIZE=10, STORAGE_ALLOWED_TYPES=image/jpeg,image/png,image/gif,image/webp,application/pdf, PKI_CA_CERT_FILE=/app/ssl/ca.crt, PKI_CA_KEY_FILE=/app/ssl/ca.key, PKI_VALIDITY_DAYS=365, GRPC_ADDRESS=:9090, GRPC_PUBLIC_ENDPOINT=grpc://${SERVER_HOST}:${GRPC_PORT:-9443}, ADMIN_ENABLED=true`
- `minio`
  image: `registry.lazycat.cloud/placeholder/agentsmesh:minio`
  binds: `/lzcapp/var/data/agentsmesh/minio:/data`
  environment: `MINIO_ROOT_USER=minioadmin, MINIO_ROOT_PASSWORD, MINIO_API_CORS_ALLOW_ORIGIN=*`
- `postgres`
  image: `registry.lazycat.cloud/placeholder/agentsmesh:postgres`
  binds: `/lzcapp/var/db/agentsmesh/postgres:/var/lib/postgresql/data`
  environment: `POSTGRES_USER=agentsmesh, POSTGRES_PASSWORD=__CHANGE_ME__, POSTGRES_DB=agentsmesh`
- `redis`
  image: `registry.lazycat.cloud/placeholder/agentsmesh:redis`
  binds: `/lzcapp/var/data/agentsmesh/redis:/data`
- `relay`
  image: `registry.lazycat.cloud/placeholder/agentsmesh:relay`
  depends_on: `backend`
  environment: `SERVER_ADDRESS=:8090, WS_READ_BUFFER_SIZE=4096, WS_WRITE_BUFFER_SIZE=4096, JWT_SECRET, BACKEND_URL=http://backend:8080, INTERNAL_API_SECRET, RELAY_ID=selfhost-relay-1, RELAY_REGION=local, RELAY_CAPACITY=1000, PRIMARY_DOMAIN, USE_HTTPS=false, SESSION_KEEP_ALIVE_DURATION=30s, DEBUG=false`
- `traefik`
  image: `registry.lazycat.cloud/placeholder/agentsmesh:traefik`
  depends_on: `backend`
  binds: `/lzcapp/pkg/content/traefik.yml:/etc/traefik/traefik.yml`
- `web`
  image: `registry.lazycat.cloud/placeholder/agentsmesh:web`
  depends_on: `backend`
  environment: `NODE_ENV=production, PRIMARY_DOMAIN, USE_HTTPS=false, POSTHOG_KEY=, POSTHOG_HOST=`
- `web-admin`
  image: `registry.lazycat.cloud/placeholder/agentsmesh:web-admin`
  depends_on: `backend`
  environment: `NODE_ENV=production, PRIMARY_DOMAIN, USE_HTTPS=false`

## 退出条件
- [ ] 入口、端口、环境变量、真实写路径、初始化命令、数据库/auth 配置全部确认完毕
- [ ] 构建后真实镜像地址已写入 `.lazycat-images.json`，打包阶段从该文件渲染临时 manifest
- [ ] 构建策略相关文件（Dockerfile / template / content / overlay）已补齐
- [ ] 可以进入预检、构建、下载 `.lpk`、安装验收阶段
