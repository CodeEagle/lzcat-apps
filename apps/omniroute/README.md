# OmniRoute

OmniRoute 是一个统一的 AI 网关，提供 Web 仪表盘、OpenAI 兼容 API、MCP 和 A2A 能力。本目录用于把上游项目移植到懒猫微服并接入 `lzcat-apps` monorepo。

## 上游项目

- GitHub: https://github.com/diegosouzapw/OmniRoute
- Homepage: https://omniroute.online
- Docker Hub: https://hub.docker.com/r/diegosouzapw/omniroute
- License: MIT
- 当前对齐的上游 release: `v2.9.2`（2026-03-21 发布）

## 访问方式

- 管理界面: `https://omniroute.${LAZYCAT_BOX_DOMAIN}`
- API Base URL: `https://omniroute.${LAZYCAT_BOX_DOMAIN}/v1`
- 健康检查: `https://omniroute.${LAZYCAT_BOX_DOMAIN}/api/monitoring/health`

## 首次启动

首次启动时，OmniRoute 会自动在数据目录中生成并持久化以下密钥文件：

- `server.env`
- `storage.sqlite`
- `db_backups/`
- `call_logs/`
- `logs/application/app.log`

默认登录密码为 `123456`。首次登录后请在 Settings 中立即修改密码。

## 环境变量说明

基础运行所需变量已经在 `lzc-manifest.yml` 中预置：

- `PORT=20128`
- `DATA_DIR=/app/data`
- `BASE_URL=http://omniroute:20128`
- `NEXT_PUBLIC_BASE_URL=https://${LAZYCAT_APP_DOMAIN}`
- `LOG_FILE_PATH=/app/data/logs/application/app.log`

以下变量按需配置：

- `ANTIGRAVITY_OAUTH_CLIENT_ID`
- `ANTIGRAVITY_OAUTH_CLIENT_SECRET`
- `GEMINI_OAUTH_CLIENT_ID`
- `GEMINI_OAUTH_CLIENT_SECRET`
- `GEMINI_CLI_OAUTH_CLIENT_SECRET`
- `IFLOW_OAUTH_CLIENT_SECRET`
- `CLOUD_URL`

说明：

- 大多数模型 provider 连接信息可以在 OmniRoute Dashboard 中添加，不必预先写入 manifest。
- 如果要在远程环境中使用 Google OAuth 相关 provider，必须配置你自己的 OAuth Client ID / Secret；内置 localhost-only 凭据不适用于懒猫公开域名。

## 数据目录

本应用将所有持久化数据统一保存在 `/lzcapp/var/data`，容器内映射到 `/app/data`。关键内容包括：

- `/lzcapp/var/data/storage.sqlite`
- `/lzcapp/var/data/server.env`
- `/lzcapp/var/data/db_backups`
- `/lzcapp/var/data/call_logs`
- `/lzcapp/var/data/log.txt`
- `/lzcapp/var/data/logs/application/app.log`

## 移植说明

- 移植路线: 单服务 Web 应用
- 构建方式: 按 upstream release tag 使用上游 Dockerfile 源码构建
- 容器监听端口: `20128`
- 数据存储: 内置 SQLite，无外部数据库或 Redis 强依赖
- OAuth / Cloud Sync: 依赖 `BASE_URL` 与 `NEXT_PUBLIC_BASE_URL`，已分别指向容器内地址和懒猫公开域名
