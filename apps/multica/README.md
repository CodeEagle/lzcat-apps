# multica

本目录由 `scripts/bootstrap_migration.py` 生成，用于把上游 `multica-ai/multica` 初始化为懒猫微服迁移项目。

## 上游项目
- Upstream Repo: multica-ai/multica
- Homepage: https://multica.ai
- License: Apache-2.0
- Author: multica-ai
- Version Strategy: `github_release` -> 当前初稿版本 `0.1.14`

## 当前迁移骨架
- Build Strategy: `upstream_dockerfile`
- Primary Subdomain: `multica`
- Image Targets: `postgres`
- Service Port: `5432`

### Services
- `postgres` -> `registry.lazycat.cloud/placeholder/multica:postgres`

## AIPod

当前未启用 AIPod / AI 服务。

## 环境变量

| 变量名 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- |
| POSTGRES_DB | No | multica | From compose service postgres |
| POSTGRES_USER | No | multica | From compose service postgres |
| POSTGRES_PASSWORD | No | multica | From compose service postgres |
| POSTGRES_PORT | No | 5432 | From .env.example |
| DATABASE_URL | No | postgres://multica:multica@localhost:5432/multica?sslmode=disable | From .env.example |
| PORT | No | 8080 | From .env.example |
| JWT_SECRET | No | change-me-in-production | From .env.example |
| MULTICA_SERVER_URL | No | ws://localhost:8080/ws | From .env.example |
| MULTICA_APP_URL | No | http://localhost:3000 | From .env.example |
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
| RESEND_API_KEY | No | - | From .env.example |
| RESEND_FROM_EMAIL | No | noreply@multica.ai | From .env.example |
| GOOGLE_CLIENT_ID | No | - | From .env.example |
| GOOGLE_CLIENT_SECRET | No | - | From .env.example |
| GOOGLE_REDIRECT_URI | No | http://localhost:3000/auth/callback | From .env.example |
| S3_BUCKET | No | - | From .env.example |
| S3_REGION | No | us-west-2 | From .env.example |
| CLOUDFRONT_KEY_PAIR_ID | No | - | From .env.example |
| CLOUDFRONT_PRIVATE_KEY_SECRET | No | multica/cloudfront-signing-key | From .env.example |
| CLOUDFRONT_PRIVATE_KEY | No | - | From .env.example |
| CLOUDFRONT_DOMAIN | No | - | From .env.example |
| COOKIE_DOMAIN | No | - | From .env.example |
| FRONTEND_PORT | No | 3000 | From .env.example |
| FRONTEND_ORIGIN | No | http://localhost:3000 | From .env.example |
| NEXT_PUBLIC_API_URL | No | http://localhost:8080 | From .env.example |
| NEXT_PUBLIC_WS_URL | No | ws://localhost:8080/ws | From .env.example |

## 部署参数（manifest render）

本应用已接入 `lzc-deploy-params.yml`，安装/重配置时可填写：

- `resend_api_key`
- `resend_from_email`

用途：
- 配置后：验证码通过邮件发送。
- 未配置：后端不会实际发邮件，验证码需要在应用日志里查看。

## 数据目录

| 宿主路径 | 容器路径 | 说明 |
| --- | --- | --- |
| /lzcapp/var/db/multica/postgres-v4 | /var/lib/postgresql/data | From compose service postgres |

## 首次启动/验收提醒

- 自动扫描到 compose 文件：docker-compose.yml
- 主服务推断为 `postgres`，入口端口 `5432`。
- 扫描到 env 示例文件：.env.example
- 扫描到 README：README.md, README.zh-CN.md

## 下一步

1. 补完 `UPSTREAM_DEPLOYMENT_CHECKLIST.md`，把真实入口、环境变量、写路径和初始化动作全部核实清楚。
2. 按真实部署拓扑修正 `lzc-manifest.yml`，不要直接沿用占位镜像、端口或命令。
3. 如果是源码构建，补齐 `Dockerfile` / `Dockerfile.template`、`content/`、`overlay_paths` 等资产。
4. 初稿补全后执行 `./scripts/local_build.sh multica --check-only`，再进入实际构建与验收。
