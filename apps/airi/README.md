# AIRI - 懒猫微服自动构建项目

> [!NOTE]
> 本仓库用于把上游 [moeru-ai/airi](https://github.com/moeru-ai/airi) 迁移到懒猫微服（LazyCat），并保留可持续更新的构建入口。

> [!IMPORTANT]
> 当前上游官方发布到 GHCR 的镜像仅覆盖 `apps/stage-web` 静态前端，不包含 `apps/server` 与 PostgreSQL。这个仓库改为构建单镜像 Web + Server 反代层，并在 LazyCat 内额外声明 PostgreSQL 服务。

## 项目说明

AIRI 是一个自托管的 AI companion / virtual character 项目，支持浏览器端交互、认证与 PostgreSQL 持久化服务端。

本迁移版本采用以下部署结构：

- `airi`：单镜像服务，内部运行：
  - AIRI `apps/server` Hono API，监听容器内 `3000`
  - Nginx 静态站点与反向代理，监听容器内 `8080`
- `postgres`：`ghcr.io/tensorchord/vchord-postgres:pg18-v1.0.0`

## 对应上游

- Upstream Repo: [moeru-ai/airi](https://github.com/moeru-ai/airi)
- Homepage: [https://airi.moeru.ai/docs/](https://airi.moeru.ai/docs/)
- License: MIT
- 当前迁移版本：`v0.9.0-alpha.2`

## 访问方式

安装后通过 LazyCat 分配的应用域名访问根路径 `/`。

迁移后的路由设计：

- `/` -> AIRI Web 前端
- `/api/*` -> AIRI Server API
- `/health` -> 容器健康检查

## 端口与挂载

| 服务 | 容器端口 | 说明 |
|------|----------|------|
| `airi` | `8080` | Nginx 对外入口，代理静态前端与 API |
| `airi` | `3000` | AIRI Server，仅容器内使用 |
| `postgres` | `5432` | PostgreSQL，仅应用内部使用 |

| 宿主机路径 | 容器路径 | 用途 |
|------------|----------|------|
| `/lzcapp/var/log/airi` | `/var/log/airi` | 应用日志目录 |
| `/lzcapp/var/db/airi/postgres` | `/var/lib/postgresql` | PostgreSQL 数据目录 |
| `/lzcapp/var/db/airi/init` | `/lzcapp/var/db/airi/init` | 初始化 SQL 持久化目录 |

## 环境变量

LazyCat manifest 中已提供可运行默认值：

| 变量 | 说明 |
|------|------|
| `DATABASE_URL` | AIRI 服务端数据库连接串 |
| `API_SERVER_URL` | 认证回调与 API 根地址，默认指向 `https://${LAZYCAT_APP_DOMAIN}` |
| `AUTH_GOOGLE_CLIENT_ID` | Google OAuth Client ID，可选但上游服务端要求非空 |
| `AUTH_GOOGLE_CLIENT_SECRET` | Google OAuth Client Secret，可选但上游服务端要求非空 |
| `AUTH_GITHUB_CLIENT_ID` | GitHub OAuth Client ID，可选但上游服务端要求非空 |
| `AUTH_GITHUB_CLIENT_SECRET` | GitHub OAuth Client Secret，可选但上游服务端要求非空 |

说明：

- 上游 `apps/server/src/libs/env.ts` 要求上述四个 OAuth 变量都为非空。
- 为了保证 LazyCat 可启动，manifest 里先给了 `change-me` 默认值。
- 如果你不需要社交登录，这些默认值足够让服务启动；若要使用 OAuth，请改成真实值。

## 已确认的上游运行信息

- 上游服务端示例 Compose：`apps/server/docker-compose.yml`
- 服务端真实监听端口：`3000`
- 健康检查路径：`/health`
- 服务端必需依赖：PostgreSQL
- 上游初始化 SQL：`apps/server/sql/init.sql`
- 上游官方 Docker workflow：`.github/workflows/release-docker.yaml`
  - 仅构建 `apps/stage-web/Dockerfile`

## 构建设计

为了避免前后端分域导致的认证与 API 配置问题，这个仓库构建单个应用镜像：

1. 从上游源码构建 `apps/stage-web`
2. 同时保留 `apps/server` 运行时依赖
3. 在同一容器内用 Nginx 暴露静态资源并把 `/api`、`/health` 反代到本地 Node 服务

这样 LazyCat 只需要暴露一个 Web 入口，前端和服务端保持同源。

## 下一步建议

推荐使用 `lzcat-trigger` 统一触发构建，而不是直接在目标仓库里做完整发布。

1. 先把 `lzc-manifest.yml` 中的占位镜像改成最终会由 `lzcat-trigger` 回写的 LazyCat Registry 地址，或保留占位值等待触发器回写。
2. 在 `lzcat-trigger` 仓库触发 `trigger-build.yml`，目标仓库填当前仓库，`target_workflow` 使用 `update-image.yml`。
3. 当前仓库的 `update-image.yml` 只负责：
   - 拉取上游指定版本源码
   - 构建并推送 `ghcr.io/<owner>/<repo>:<source_version>` 主镜像
   - 记录 `.lazycat-build.json`
4. 后续由 `lzcat-trigger` 继续负责：
   - `copy-image` 到 `registry.lazycat.cloud/...`
   - 回写 `lzc-manifest.yml`
   - 构建 `.lpk`
   - 发布 GitHub Release
   - 按需发布应用商店

## 本地验证

仓库内提供了一个最小本地验证脚本：

```bash
bash ./scripts/validate-local.sh
```

它会执行：

- manifest/build/readme 预检
- `lazycat/start-airi.sh` shell 语法检查
- `lzc-cli project build`

## 当前缺口 / 风险

- 还没有完成真实 `.lpk` 安装验收，因此镜像源最好在交付前切到 `registry.lazycat.cloud/...` 再验证一次。
- 当前工作区机器没有 `docker`，因此这次交付只能完成 `.lpk` 封包与目标仓库工作流适配，不能在本机直接构建 `airi` 镜像。
- `source_version` 保留上游真实 tag（如 `v0.9.0-alpha.2`），但 `version` / `build_version` 统一收敛为纯 `X.Y.Z`（当前为 `0.9.0`），以满足只接受 semver 主版本号的 LPK/商店环境。
- 上游仓库很大，本仓库的工作流采用浅克隆指定 tag 构建，会比单镜像复制更耗时。
