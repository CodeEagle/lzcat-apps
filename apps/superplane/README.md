# SuperPlane

SuperPlane 的 LazyCat 移植，基于上游仓库 `superplanehq/superplane` 的官方 single-host 路线构建，使用官方应用镜像加上独立的 PostgreSQL 和 RabbitMQ 服务。

## 访问方式

- 安装后访问 `https://<your-app-domain>/`
- 健康检查接口：`https://<your-app-domain>/health`
- 首次启动会自动执行数据库初始化和迁移，然后进入 Owner setup 流程

## 上游部署清单

- 上游入口：上游 `ghcr.io/superplanehq/superplane:v0.12.0` 镜像的默认 `docker-entrypoint.sh`
- 实际监听端口：`8000`（`PUBLIC_API_PORT=8000`，健康检查走 `/health`）
- 初始化动作：
  - 上游启动时执行 `createdb`
  - 上游启动时执行 `migrate -source file:///app/db/migrations`
  - 上游启动时执行 `migrate -source file:///app/db/data_migrations`
- 实际写路径：
  - `/app/data/oidc-keys`
- 外部依赖：PostgreSQL 和 RabbitMQ，均作为单独服务由 LazyCat 提供

## 数据与配置

- 持久化目录：
  - `/lzcapp/var/data/oidc-keys -> /app/oidc-keys`
  - `/lzcapp/var/db/superplane/postgres -> /var/lib/postgresql/data`
- `BASE_URL` 与 `WEBHOOKS_BASE_URL` 默认指向 LazyCat 分配域名
- 走官方 single-host 逻辑，不启用 `caddy` 或 `localtunnel`

## 上游信息

- Upstream Repo: https://github.com/superplanehq/superplane
- Homepage: https://superplane.com
- Docs: https://docs.superplane.com
- Latest verified upstream release: `v0.12.0` (2026-03-15)
