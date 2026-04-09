# cultivation-world-simulator Upstream Deployment Checklist

## 已确认字段
- PROJECT_NAME: cultivation-world-simulator
- PROJECT_SLUG: cultivation-world-simulator
- UPSTREAM_REPO: 4thfever/cultivation-world-simulator
- UPSTREAM_URL: https://github.com/4thfever/cultivation-world-simulator
- HOMEPAGE: https://github.com/4thfever/cultivation-world-simulator
- LICENSE: CC-BY-NC-SA-4.0
- AUTHOR: 4thfever
- VERSION: 2.4.0
- IMAGE: TODO
- PORT: 80
- AI_POD_SERVICE: 无
- AI_POD_SERVICE_NAME: 无
- AI_POD_SERVICE_PORT: 无
- CHECK_STRATEGY: commit_sha
- BUILD_STRATEGY: upstream_dockerfile

## 预填环境变量
- `PYTHONUNBUFFERED`: From compose service backend (required=False)
- `CWS_DATA_DIR`: From compose service backend (required=False)
- `CWS_DISABLE_AUTO_SHUTDOWN`: From compose service backend (required=False)

## 预填数据路径
- `/data` <= `/lzcapp/var/data/cultivation-world-simulator/backend` (compose backend bind root)
- `/data/settings.json` 由后端设置服务自动创建
- `/data/secrets.json` 由后端设置服务自动创建
- `/data/saves/` 由后端运行时自动创建
- `/data/logs/` 由后端运行时自动创建
- `/data/cache/` 由后端运行时自动创建
- `/data/incompatible/` 用于保存损坏配置备份，由后端自动创建

## 预填启动说明
- 上游 compose 入口是 `frontend`(80) + `backend`(8002)
- `frontend` 使用 `deploy/nginx.conf` 提供静态页面，并把 `/api`、`/ws`、`/assets` 代理到 `backend:8002`
- `backend` 使用 `uvicorn src.server.main:app --host 0.0.0.0 --port 8002`
- 首次启动后必须在设置页写入 LLM provider、模型名和 API key，再开始新游戏
- 无 `.env.example`，当前上游显式环境变量仅发现 `PYTHONUNBUFFERED`、`CWS_DATA_DIR`、`CWS_DISABLE_AUTO_SHUTDOWN`

## 必扫清单
- [x] Dockerfile / Containerfile / compose / helm / entrypoint / startup script 的真实启动入口
- [x] README / 部署文档 / `.env.example` / sample config 中声明的环境变量
- [x] 数据目录、配置目录、缓存目录、上传目录、日志目录、临时目录的真实读写路径
- [x] 若启用 AIPod，确认 `ai-pod-service/docker-compose.yml` 中的真实镜像、服务端口、`-ai` Host 规则与 `traefik-shared-network` 配置
- [x] 首次启动初始化命令、迁移命令、建库建表命令、管理员初始化命令
- [x] 数据库、Redis、对象存储、auth / OAuth / JWT / callback / secret 等外部依赖配置
- [x] 每个真实目录是否需要预创建、由谁创建、以什么 owner/group/mode 创建

## 已确认的上游部署清单
- 真实启动入口
  - `deploy/Dockerfile.backend`: `uvicorn src.server.main:app --host 0.0.0.0 --port 8002`
  - `deploy/Dockerfile.frontend`: Node 22 构建静态资源，运行阶段为 `nginx:alpine`
  - `deploy/nginx.conf`: `/` 提供前端静态页，`/api`、`/ws`、`/assets` 反代到 `backend:8002`
- 环境变量
  - `PYTHONUNBUFFERED=1`
  - `CWS_DATA_DIR=/data`
  - `CWS_DISABLE_AUTO_SHUTDOWN=1`
- 数据与配置路径
  - `settings.json`, `secrets.json`, `saves/`, `logs/`, `cache/`, `incompatible/` 全部位于 `CWS_DATA_DIR`
  - 上游测试 `tests/test_data_paths_runtime_contract.py` 明确要求上述路径均归属 `CWS_DATA_DIR`
- 初始化与健康检查
  - 无数据库迁移、无管理员 bootstrap、无单独初始化命令
  - 健康检查使用 `GET /api/v1/query/runtime/status`
  - 首次有效使用前需在 `/api/settings/llm` 或 UI 设置页保存模型配置
- 外部依赖
  - 无 PostgreSQL、Redis、对象存储
  - 需要用户自备兼容的 LLM API endpoint 与 key
- 目录预创建规则
  - 后端镜像未设置 `USER`，默认 root 运行
  - `src/config/data_paths.py` 会在启动时自动创建 `root/saves/logs/cache/incompatible`
  - LazyCat 侧仍应预创建宿主挂载根目录 `/lzcapp/var/data/cultivation-world-simulator/backend`

## 当前服务拓扑初稿
- `backend`
  image: `registry.lazycat.cloud/placeholder/cultivation-world-simulator:backend`
  binds: `/lzcapp/var/data/cultivation-world-simulator/backend:/data`
  environment: `PYTHONUNBUFFERED=1, CWS_DATA_DIR=/data, CWS_DISABLE_AUTO_SHUTDOWN=1`
- `frontend`
  image: `registry.lazycat.cloud/placeholder/cultivation-world-simulator:frontend`
  depends_on: 无（LazyCat 包内移除，避免平台聚合健康等待）

## 退出条件
- [ ] 入口、端口、环境变量、真实写路径、初始化命令、数据库/auth 配置全部确认完毕
- [ ] 构建后真实镜像地址已写入 `.lazycat-images.json`，打包阶段从该文件渲染临时 manifest
- [ ] 构建策略相关文件（Dockerfile / template / content / overlay）已补齐
- [ ] 可以进入预检、构建、下载 `.lpk`、安装验收阶段
