# heym

本目录由 `scripts/bootstrap_migration.py` 生成，用于把上游 `heymrun/heym` 初始化为懒猫微服迁移项目。

## 上游项目
- Upstream Repo: heymrun/heym
- Homepage: https://heym.run
- License: 
- Author: heymrun
- Version Strategy: `github_release` -> 当前初稿版本 `0.0.16`

## 当前迁移骨架
- Build Strategy: `upstream_dockerfile`
- Primary Subdomain: `heym`
- Image Targets: `backend, frontend`
- Service Port: `4017`

### Services
- `backend` -> `registry.lazycat.cloud/placeholder/heym:backend`
- `frontend` -> `registry.lazycat.cloud/placeholder/heym:frontend`
- `postgres` -> `registry.lazycat.cloud/placeholder/heym:postgres`

## AIPod

当前未启用 AIPod / AI 服务。

## 环境变量

| 变量名 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- |
| TZ | No | Europe/Berlin | From compose service frontend |
| POSTGRES_USER | No | postgres | From compose service postgres |
| POSTGRES_PASSWORD | No | postgres | From compose service postgres |
| POSTGRES_DB | No | heym | From compose service postgres |
| TIMEZONE | No | Europe/Berlin | From compose service backend |
| DATABASE_URL | No | postgresql+asyncpg://${POSTGRES_USER:-postgres}:${POSTGRES_PASSWORD:-postgres}@postgres:5432/${POSTGRES_DB:-heym} | From compose service backend |
| SECRET_KEY | No | your-super-secret-key-change-in-production-min-32-chars | From compose service backend |
| ENCRYPTION_KEY | No | change_this_to_a_random_32_byte_hex_value | From compose service backend |
| JWT_ALGORITHM | No | HS256 | From compose service backend |
| JWT_ACCESS_TOKEN_EXPIRE_MINUTES | No | 30 | From compose service backend |
| JWT_REFRESH_TOKEN_EXPIRE_DAYS | No | 7 | From compose service backend |
| CORS_ORIGINS | No | http://localhost:4017 | From compose service backend |
| FRONTEND_URL | No | http://localhost:4017  # pragma: allowlist secret | From compose service backend |
| ALLOW_REGISTER | No | false | From compose service backend |
| VITE_API_TARGET | No | http://backend:10105 | From compose service frontend |
| POSTGRES_HOST | No | localhost | From .env.example |
| POSTGRES_PORT | No | 6543 | From .env.example |
| BACKEND_PORT | No | 10105 | From .env.example |
| BACKEND_BIND_HOST | No | 127.0.0.1 | From .env.example |
| BACKEND_PROXY_HOST | No | 127.0.0.1 | From .env.example |
| AUTO_REWRITE_LOCAL_DATABASE_HOST | No | true | From .env.example |
| FRONTEND_PORT | No | 4017 | From .env.example |

## 数据目录

| 宿主路径 | 容器路径 | 说明 |
| --- | --- | --- |
| /lzcapp/var/db/heym/postgres | /var/lib/postgresql/data | From compose service postgres |
| /lzcapp/var/data/heym/backend/files | /app/data/files | From compose service backend |

## 首次启动/验收提醒

- 自动扫描到 compose 文件：docker-compose.yml
- 主服务推断为 `frontend`，入口端口 `4017`。
- 依赖服务镜像已写入 dependencies，首次完整构建时会自动 copy-image。
- 扫描到 env 示例文件：.env.example
- 扫描到 README：README.md

## 下一步

1. 补完 `UPSTREAM_DEPLOYMENT_CHECKLIST.md`，把真实入口、环境变量、写路径和初始化动作全部核实清楚。
2. 按真实部署拓扑修正 `lzc-manifest.yml`，不要直接沿用占位镜像、端口或命令。
3. 如果是源码构建，补齐 `Dockerfile` / `Dockerfile.template`、`content/`、`overlay_paths` 等资产。
4. 初稿补全后执行 `./scripts/local_build.sh heym --check-only`，再进入实际构建与验收。
