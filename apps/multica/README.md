# Multica

本目录由 `scripts/bootstrap_migration.py` 生成，用于把上游 `multica-ai/multica` 初始化为懒猫微服迁移项目。

## 上游项目
- Upstream Repo: multica-ai/multica
- Homepage: https://github.com/multica-ai/multica
- License: 
- Author: TODO
- Version Strategy: `github_release` -> 当前初稿版本 `0.1.0`

## 当前迁移骨架
- Build Strategy: `upstream_dockerfile`
- Primary Subdomain: `multica`
- Image Targets: `frontend, backend`
- Service Port: `3000`

### Services
- `multica-postgres` -> `pgvector/pgvector:pg17`
- `multica-backend` -> built from upstream `Dockerfile`
- `multica-frontend` -> built from upstream `Dockerfile.web` with LazyCat build patch

## AIPod

## 登录

Multica 保留上游验证码登录流程。用户输入邮箱后，应用会调用后端发送真实验证码；未配置邮件服务时，可从后端日志查看开发验证码。

## 首次登录
1. 在邮箱字段输入任意邮箱（如 `admin@lazycat.local`）
2. 点击「Continue」发送验证码
3. 输入后端生成的验证码

LazyCat 迁移补丁只修复验证码页 Back 按钮：点击 Back 会返回应用首页，不会绕过或自动填写验证码。

## 数据持久化

| 目录 | 说明 |
|------|------|
| `/lzcapp/var/data/postgres/` | PostgreSQL 数据库文件 |
| `/lzcapp/var/data/uploads/` | 用户上传文件 |

## 环境变量

| 变量名 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- |
| POSTGRES_DB | No | multica | From compose service postgres |
| POSTGRES_USER | No | multica | From compose service postgres |
| POSTGRES_PASSWORD | No | multica | From compose service postgres |
| DATABASE_URL | No | postgres://${POSTGRES_USER:-multica}:${POSTGRES_PASSWORD:-multica}@postgres:5432/${POSTGRES_DB:-multica}?sslmode=disable | From compose service backend |
| PORT | No | 8080 | From compose service backend |
| JWT_SECRET | No | change-me-in-production | From compose service backend |
| FRONTEND_ORIGIN | No | http://localhost:3000 | From compose service backend |
| CORS_ALLOWED_ORIGINS | No | - | From compose service backend |
| RESEND_API_KEY | No | - | From compose service backend |
| RESEND_FROM_EMAIL | No | noreply@multica.ai | From compose service backend |
| GOOGLE_CLIENT_ID | No | - | From compose service backend |
| GOOGLE_CLIENT_SECRET | No | - | From compose service backend |
| GOOGLE_REDIRECT_URI | No | http://localhost:3000/auth/callback | From compose service backend |
| S3_BUCKET | No | - | From compose service backend |
| S3_REGION | No | us-west-2 | From compose service backend |
| CLOUDFRONT_DOMAIN | No | - | From compose service backend |
| CLOUDFRONT_KEY_PAIR_ID | No | - | From compose service backend |
| CLOUDFRONT_PRIVATE_KEY | No | - | From compose service backend |
| COOKIE_DOMAIN | No | - | From compose service backend |
| MULTICA_APP_URL | No | http://localhost:3000 | From compose service backend |
| HOSTNAME | No | 0.0.0.0 | From compose service frontend |
| POSTGRES_PORT | No | 5432 | From .env.example |
| MULTICA_SERVER_URL | No | ws://localhost:8080/ws | From .env.example |
| MULTICA_DAEMON_CONFIG | No | - | From .env.example |
| MULTICA_WORKSPACE_ID | No | - | From .env.example |
| MULTICA_DAEMON_ID | No | - | From .env.example |
| MULTICA_DAEMON_DEVICE_NAME | No | - | From .env.example |
| MULTICA_DAEMON_POLL_INTERVAL | No | 3s | From .env.example |
| MULTICA_DAEMON_HEARTBEAT_INTERVAL | No | 15s | From .env.example |
| MULTICA_CODEX_PATH | No | codex | From .env.example |
| MULTICA_CODEX_MODEL | No | - | From .env.example |
| MULTICA_CODEX_WORKDIR | No | - | From .env.example |
| MULTICA_CODEX_TIMEOUT | No | 20m | From .env.example |
| NEXT_PUBLIC_GOOGLE_CLIENT_ID | No | - | From .env.example |
| CLOUDFRONT_PRIVATE_KEY_SECRET | No | multica/cloudfront-signing-key | From .env.example |
| FRONTEND_PORT | No | 3000 | From .env.example |
| NEXT_PUBLIC_API_URL | No | http://localhost:8080 | From .env.example |
| NEXT_PUBLIC_WS_URL | No | ws://localhost:8080/ws | From .env.example |

## 数据目录

| 宿主路径 | 容器路径 | 说明 |
| --- | --- | --- |
| /lzcapp/var/db/multica/postgres | /var/lib/postgresql/data | From compose service postgres |

## 首次启动/验收提醒

- 自动扫描到 compose 文件：docker-compose.selfhost.yml
- 主服务推断为 `frontend`，入口端口 `3000`。
- 依赖服务镜像已写入 dependencies，首次完整构建时会自动 copy-image。
- 扫描到 env 示例文件：.env.example
- 扫描到 README：README.md, README.zh-CN.md

## 下一步

1. 补完 `UPSTREAM_DEPLOYMENT_CHECKLIST.md`，把真实入口、环境变量、写路径和初始化动作全部核实清楚。
2. 按真实部署拓扑修正 `lzc-manifest.yml`，不要直接沿用占位镜像、端口或命令。
3. 如果是源码构建，补齐 `Dockerfile` / `Dockerfile.template`、`content/`、`overlay_paths` 等资产。
4. 初稿补全后执行 `./scripts/local_build.sh multica --check-only`，再进入实际构建与验收。
