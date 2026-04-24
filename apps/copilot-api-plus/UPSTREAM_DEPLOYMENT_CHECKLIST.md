# copilot-api-plus Upstream Deployment Checklist

## 已确认字段
- PROJECT_NAME: copilot-api-plus
- PROJECT_SLUG: copilot-api-plus
- UPSTREAM_REPO: CodeEagle/copilot-api-plus
- UPSTREAM_URL: https://github.com/CodeEagle/copilot-api-plus
- HOMEPAGE: https://github.com/CodeEagle/copilot-api-plus
- LICENSE: MIT
- AUTHOR: CodeEagle
- VERSION: 1.2.14
- SOURCE_VERSION: 54c525f
- IMAGE: 由 `scripts/run_build.py` 从上游 Dockerfile 构建后写入 `.lazycat-images.json`
- PORT: 4141
- AI_POD_SERVICE: 无
- AI_POD_SERVICE_NAME: 无
- AI_POD_SERVICE_PORT: 无
- CHECK_STRATEGY: commit_sha
- BUILD_STRATEGY: upstream_dockerfile

## 上游部署清单

### 启动入口
- 上游 Dockerfile 使用多阶段 Bun 构建：`bun install --frozen-lockfile`、`bun run build`，最终运行镜像为 `oven/bun:1.2.19-alpine`。
- 当前移植使用 `overlay_paths` 覆盖 `pages/index.html`，修复用量页 `renderContent()` 中 `mode` 未定义导致的浏览器运行时错误，以及「运行统计」标签无法切换的问题。
- 容器入口：`ENTRYPOINT ["/entrypoint.sh"]`。
- 上游 `entrypoint.sh` 默认执行 `bun run dist/main.js start "$@"`；传入 `--auth` 时才进入 CLI 认证流程。
- 服务真实监听端口：`4141`，LazyCat `application.upstreams[].backend` 指向 `http://copilot-api-plus:4141/`。
- 官方 healthcheck：`wget --spider -q http://localhost:4141/ || exit 1`。

### 环境变量
- `PORT=4141`：服务监听端口。
- `COPILOT_API_DATA_DIR=/lzcapp/var/data/copilot-api-plus`：上游 `src/lib/paths.ts` 支持的 LazyCat 数据目录覆盖项。
- `VERBOSE=true`：可选，启用详细日志。
- `HTTP_PROXY` / `HTTPS_PROXY` / `NO_PROXY`：可选代理配置。
- `GEMINI_API_KEY`：可选，仅 Antigravity 模式需要。
- `ANTIGRAVITY_CLIENT_ID` / `ANTIGRAVITY_CLIENT_SECRET`：可选，仅自定义 Google OAuth 时需要。

### 数据目录和写路径
- 上游默认数据目录：`~/.local/share/copilot-api-plus`。
- LazyCat 运行时数据目录：`/lzcapp/var/data/copilot-api-plus`，通过 `COPILOT_API_DATA_DIR` 显式指定。
- 持久化文件：`github_token`、`accounts.json`、`config.json`。
- 目录创建：应用启动时 `ensurePaths()` 会创建数据目录和 `github_token`；LazyCat 同时通过 bind 预留可写目录。
- 运行用户：上游 Bun Alpine 镜像默认 root；挂载目录由容器进程直接写入。

### 初始化、数据库和外部依赖
- 不需要数据库、Redis、对象存储或迁移命令。
- 首次打开 Web UI 后，可在账号管理页通过 GitHub Device Code 授权添加 Copilot 账号。
- API 兼容端点包括 `/v1/chat/completions`、`/v1/models`、`/v1/embeddings`、`/v1/messages`、`/usage`、`/token` 和 `/api/*` 管理接口。

### 登录机制
- 应用自身没有固定用户名/密码登录页。
- 上游授权对象是 GitHub Copilot 账号，需由用户在 Web UI 中发起 GitHub Device Code 流程。
- LazyCat 免密登录不适用：没有应用本地账号密码，也没有 OIDC/OAuth2 登录回调可接入 LazyCat 账号体系。

## 预填启动说明
- 从上游 Dockerfile 构建镜像，不再使用本目录旧的二次封装 Dockerfile。
- 构建时会把 `apps/copilot-api-plus/pages/index.html` 覆盖到上游源码，修复首页用量面板渲染。
- 启动后首页是内置 Web 管理 UI。
- 未添加 GitHub 账号前，UI 可打开，`/v1/models` 等需要 Copilot 账号的接口可能返回无账号/未认证状态，这是上游预期行为。

## 必扫清单
- [x] Dockerfile / Containerfile / compose / helm / entrypoint / startup script 的真实启动入口
- [x] README / 部署文档 / `.env.example` / sample config 中声明的环境变量
- [x] 数据目录、配置目录、缓存目录、上传目录、日志目录、临时目录的真实读写路径
- [x] AIPod 不适用
- [x] 首次启动初始化命令、迁移命令、建库建表命令、管理员初始化命令
- [x] 数据库、Redis、对象存储、auth / OAuth / JWT / callback / secret 等外部依赖配置
- [x] 每个真实目录是否需要预创建、由谁创建、以什么 owner/group/mode 创建

## 当前服务拓扑初稿
- `copilot-api-plus`
  image: `registry.lazycat.cloud/placeholder/copilot-api-plus:bootstrap`

## 退出条件
- [x] 入口、端口、环境变量、真实写路径、初始化命令、数据库/auth 配置全部确认完毕
- [ ] 构建后真实镜像地址已写入 `.lazycat-images.json`，打包阶段从该文件渲染临时 manifest
- [x] 构建策略相关文件已补齐：直接复用上游 Dockerfile
- [ ] 可以进入预检、构建、下载 `.lpk`、安装验收阶段
