# cultivation-world-simulator

本目录由 `scripts/bootstrap_migration.py` 生成，用于把上游 `4thfever/cultivation-world-simulator` 初始化为懒猫微服迁移项目。

## 上游项目
- Upstream Repo: 4thfever/cultivation-world-simulator
- Homepage: https://github.com/4thfever/cultivation-world-simulator
- License: CC-BY-NC-SA-4.0
- Author: 4thfever
- Version Strategy: `commit_sha` -> 当前初稿版本 `2.4.0`

## 当前迁移骨架
- Build Strategy: `upstream_dockerfile`
- Primary Subdomain: `cultivation-world-simulator`
- Image Targets: `frontend`
- Service Port: `80`

### Services
- `backend` -> `registry.lazycat.cloud/placeholder/cultivation-world-simulator:backend`
- `frontend` -> `registry.lazycat.cloud/placeholder/cultivation-world-simulator:frontend`

## AIPod

当前未启用 AIPod / AI 服务。

## 环境变量

| 变量名 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- |
| PYTHONUNBUFFERED | No | 1 | From compose service backend |
| CWS_DATA_DIR | No | /data | From compose service backend |
| CWS_DISABLE_AUTO_SHUTDOWN | No | 1 | From compose service backend |

## 数据目录

| 宿主路径 | 容器路径 | 说明 |
| --- | --- | --- |
| /lzcapp/var/data/cultivation-world-simulator/backend | /data | Holds settings, secrets, saves, logs, cache, and incompatible backups via `CWS_DATA_DIR`. |

## 首次启动/验收提醒

- 上游是双服务拓扑：FastAPI backend(`8002`) + Nginx frontend(`80`)。
- 前端镜像使用仓库内的 Nginx 模板，并在容器启动时从 `/etc/resolv.conf` 注入 `resolver`，避免 `backend` DNS 在启动瞬间未解析时直接导致 Nginx 退出。
- 当前包不再声明自定义 service healthcheck，避免平台在双服务启动时因容器内探针差异或聚合时序长期停留在 “Standing by until other services are healthy”。
- `frontend` 不再声明 `depends_on: backend`；前端可先独立启动，实际 API / WebSocket 请求再由 Nginx 在运行时解析 `backend`，避免平台把启动完成错误绑定到服务依赖聚合。
- LazyCat `application.upstreams` 只保留 `/ -> frontend`。`/api`、`/ws`、`/assets` 全部交给 frontend 容器内 Nginx 再反代到 backend，避免平台层对 `/api/` 前缀路由做路径改写后导致 backend 收到错误路径并返回 404。
- 首次启动后需要先在设置页配置 LLM provider、API key 和模型，再开始新游戏。
- 后端通过 `CWS_DATA_DIR=/data` 统一持久化 `settings.json`、`secrets.json`、`saves/`、`logs/`、`cache/`、`incompatible/`。
- 无数据库、Redis 或管理员 bootstrap；外部依赖主要是用户自行配置的 LLM/OpenAI 兼容接口。

## 下一步

1. 等待 `scripts/local_build.sh cultivation-world-simulator --no-dry-run --force-build` 完成，产出 `.lazycat-images.json` 和 `.lpk`。
2. 若构建成功，核对 release 包内最终 `manifest.yml` 是否仍保持双服务拓扑和正确镜像映射。
3. 具备设备安装条件后执行安装验收，确认首页可访问、`/api/v1/query/runtime/status` 可用、设置页可保存 LLM 配置。
