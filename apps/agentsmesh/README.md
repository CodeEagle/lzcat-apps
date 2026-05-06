# AgentsMesh

本目录由 `scripts/bootstrap_migration.py` 生成，用于把上游 `AgentsMesh/AgentsMesh` 初始化为懒猫微服迁移项目。

## 上游项目
- Upstream Repo: AgentsMesh/AgentsMesh
- Homepage: https://agentsmesh.ai
- License: 
- Author: AgentsMesh
- Version Strategy: `github_release` -> 当前初稿版本 `0.29.0`

## 当前迁移骨架
- Build Strategy: `upstream_dockerfile`
- Primary Subdomain: `agentsmesh`
- Image Targets: `relay`
- Service Port: `80`

### Services
- `backend` -> `registry.lazycat.cloud/placeholder/agentsmesh:backend`
- `minio` -> `registry.lazycat.cloud/placeholder/agentsmesh:minio`
- `postgres` -> `registry.lazycat.cloud/placeholder/agentsmesh:postgres`
- `redis` -> `registry.lazycat.cloud/placeholder/agentsmesh:redis`
- `relay` -> `registry.lazycat.cloud/placeholder/agentsmesh:relay`
- `traefik` -> `registry.lazycat.cloud/placeholder/agentsmesh:traefik`
- `web` -> `registry.lazycat.cloud/placeholder/agentsmesh:web`
- `web-admin` -> `registry.lazycat.cloud/placeholder/agentsmesh:web-admin`

## AIPod

当前未启用 AIPod / AI 服务。

## 环境变量

| 变量名 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- |
| POSTGRES_USER | No | agentsmesh | From compose service postgres |
| POSTGRES_PASSWORD | No | __CHANGE_ME__ | From compose service postgres |
| POSTGRES_DB | No | agentsmesh | From compose service postgres |
| MINIO_ROOT_USER | No | minioadmin | From compose service minio |
| MINIO_ROOT_PASSWORD | No | __CHANGE_ME__ | From compose service minio |
| MINIO_API_CORS_ALLOW_ORIGIN | No | * | From compose service minio |
| PRIMARY_DOMAIN | No | _PRIMARY_DOMAIN_ | From compose service relay |
| USE_HTTPS | No | false | From compose service relay |
| DB_HOST | No | postgres | From compose service backend |
| DB_PORT | No | 5432 | From compose service backend |
| DB_USER | No | agentsmesh | From compose service backend |
| DB_PASSWORD | No | __CHANGE_ME__ | From compose service backend |
| DB_NAME | No | agentsmesh | From compose service backend |
| DB_SSLMODE | No | disable | From compose service backend |
| REDIS_URL | No | redis://redis:6379 | From compose service backend |
| JWT_SECRET | No | __CHANGE_ME__ | From compose service relay |
| INTERNAL_API_SECRET | No | __CHANGE_ME__ | From compose service relay |
| SERVER_ADDRESS | No | :8090 | From compose service relay |
| DEBUG | No | false | From compose service relay |
| CORS_ALLOWED_ORIGINS | No | * | From compose service backend |
| LOG_LEVEL | No | info | From compose service backend |
| LOG_FORMAT | No | json | From compose service backend |
| LOG_FILE | No | /dev/stdout | From compose service backend |
| EMAIL_PROVIDER | No | console | From compose service backend |
| STORAGE_ENDPOINT | No | minio:9000 | From compose service backend |
| STORAGE_PUBLIC_ENDPOINT | No | ${SERVER_HOST}:${MINIO_API_PORT:-9000} | From compose service backend |
| STORAGE_REGION | No | us-east-1 | From compose service backend |
| STORAGE_BUCKET | No | agentsmesh | From compose service backend |
| STORAGE_ACCESS_KEY | No | minioadmin | From compose service backend |
| STORAGE_SECRET_KEY | No | __CHANGE_ME__ | From compose service backend |
| STORAGE_USE_SSL | No | false | From compose service backend |
| STORAGE_USE_PATH_STYLE | No | true | From compose service backend |
| STORAGE_MAX_FILE_SIZE | No | 10 | From compose service backend |
| STORAGE_ALLOWED_TYPES | No | image/jpeg,image/png,image/gif,image/webp,application/pdf | From compose service backend |
| PKI_CA_CERT_FILE | No | /app/ssl/ca.crt | From compose service backend |
| PKI_CA_KEY_FILE | No | /app/ssl/ca.key | From compose service backend |
| PKI_VALIDITY_DAYS | No | 365 | From compose service backend |
| GRPC_ADDRESS | No | :9090 | From compose service backend |
| GRPC_PUBLIC_ENDPOINT | No | grpc://${SERVER_HOST}:${GRPC_PORT:-9443} | From compose service backend |
| ADMIN_ENABLED | No | true | From compose service backend |
| NODE_ENV | No | production | From compose service web-admin |
| WS_READ_BUFFER_SIZE | No | 4096 | From compose service relay |
| WS_WRITE_BUFFER_SIZE | No | 4096 | From compose service relay |
| BACKEND_URL | No | http://backend:8080 | From compose service relay |
| RELAY_ID | No | selfhost-relay-1 | From compose service relay |
| RELAY_REGION | No | local | From compose service relay |
| RELAY_CAPACITY | No | 1000 | From compose service relay |
| SESSION_KEEP_ALIVE_DURATION | No | 30s | From compose service relay |
| JWT_EXPIRATION_HOURS | No | 24 | From .env.example |
| DEPLOYMENT_TYPE | No | global | From .env.example |
| ALIPAY_SANDBOX | No | false | From .env.example |
| WECHAT_SANDBOX | No | false | From .env.example |
| NEXT_PUBLIC_GITLAB_SSO_URL | No | https://gitlab.com | From .env.example |
| SERVER_HOST | No | __SERVER_HOST__ | From .env.example |
| HTTP_PORT | No | 80 | From .env.example |
| GRPC_PORT | No | 9443 | From .env.example |
| VERSION | No | latest | From .env.example |
| COMPOSE_PROJECT_NAME | No | agentsmesh | From .env.example |
| MINIO_CONSOLE_PORT | No | 9001 | From .env.example |
| MINIO_API_PORT | No | 9000 | From .env.example |

## 数据目录

| 宿主路径 | 容器路径 | 说明 |
| --- | --- | --- |
| /lzcapp/var/db/agentsmesh/postgres | /var/lib/postgresql/data | From compose service postgres |
| /lzcapp/var/data/agentsmesh/redis | /data | From compose service redis |
| /lzcapp/var/data/agentsmesh/minio | /data | From compose service minio |

## 首次启动/验收提醒

- 自动扫描到 compose 文件：deploy/selfhost/docker-compose.yml
- 主服务推断为 `traefik`，入口端口 `80`。
- 依赖服务镜像已写入 dependencies，首次完整构建时会自动 copy-image。
- 扫描到 env 示例文件：.env.example, .env.example, .env.example
- 扫描到 README：README.md, README.md, README.md
- 扫描到上游图标：web/public/icons/icon-512.png

## 下一步

1. 补完 `UPSTREAM_DEPLOYMENT_CHECKLIST.md`，把真实入口、环境变量、写路径和初始化动作全部核实清楚。
2. 按真实部署拓扑修正 `lzc-manifest.yml`，不要直接沿用占位镜像、端口或命令。
3. 如果是源码构建，补齐 `Dockerfile` / `Dockerfile.template`、`content/`、`overlay_paths` 等资产。
4. 初稿补全后执行 `./scripts/local_build.sh agentsmesh --check-only`，再进入实际构建与验收。
