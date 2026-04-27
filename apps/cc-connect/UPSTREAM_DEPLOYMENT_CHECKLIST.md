# cc-connect Upstream Deployment Checklist

## 已确认字段
- PROJECT_NAME: cc-connect
- PROJECT_SLUG: cc-connect
- UPSTREAM_REPO: chenhg5/cc-connect
- UPSTREAM_URL: https://github.com/chenhg5/cc-connect
- HOMEPAGE: https://github.com/chenhg5/cc-connect
- LICENSE: MIT
- AUTHOR: chenhg5
- VERSION: 1.3.2
- IMAGE: workflow 构建后写入 `apps/cc-connect/.lazycat-images.json`
- PORT: 9820
- CHECK_STRATEGY: github_release
- BUILD_STRATEGY: target_repo_dockerfile

## 上游部署清单
- 启动入口：源码构建 `./cmd/cc-connect`，LazyCat 镜像运行 `cc-connect --config /data/config.toml`。
- Web 管理台：上游 `make build` 会先执行 `web` target，将 `web/dist` 嵌入 Go 二进制；管理 API 默认端口为 `9820`。
- Bridge：`[bridge]` 默认端口 `9810`，路径 `/bridge/ws`；管理台也可在同进程路由该路径。
- Webhook：`[webhook]` 默认端口 `9111`，LazyCat 额外把 `/hook` 路由到该端口。
- Docker/Compose：上游未提供官方 Dockerfile 或 compose；迁移使用目标仓库 Dockerfile 从 GitHub release tag 拉取源码构建。
- 构建依赖：Node 22 构建 Web 前端，Go 1.25 构建二进制，运行时基于 Node 22 slim，附带常见 Agent CLI 的 best-effort 安装。
- 环境变量：上游 config 支持 `${VAR_NAME}` 替换；LazyCat 镜像使用 `CC_CONNECT_DATA_DIR`、`CC_CONNECT_CONFIG`、`CC_CONNECT_MANAGEMENT_TOKEN`、`CC_CONNECT_BRIDGE_TOKEN`、`CC_CONNECT_WEBHOOK_TOKEN` 控制默认配置，并固定 `HOME=/data/home`、`CODEX_HOME=/data/home/.codex`。
- 数据目录：`data_dir`、会话、项目状态、CLI home/cache、用户工作区全部放在 `/data` 下。
- 外部依赖：无数据库、Redis、对象存储依赖；聊天平台凭据、LLM provider key 和 agent 配置由 Web 管理台写入 `/data/config.toml`。
- 初始化：首次启动若 `/data/config.toml` 不存在，由 `lazycat/entrypoint.sh` 创建 management-only 配置。
- 登录机制：上游 Web 管理台以 management token 登录；LazyCat 默认 management token 为空，并补丁支持 tokenless 自动登录，依赖 LazyCat 访问控制实现免密。

## 真实写路径与权限
- `/data/config.toml`：entrypoint 首次创建，root 写入，`0600` umask。
- `/data/state`：cc-connect `data_dir`，保存会话、cron、relay、项目状态。
- `/data/home/.config`、`/data/home/.local/share`、`/data/home/.cache`：Agent CLI 与 npm/global CLI 运行时状态。
- `/data/home/.claude`、`/data/home/.codex`、`/data/home/.agents/skills`：可选导入本机 Claude Code/Codex 登录状态、commands 和 skills；这些目录包含敏感凭据，必须由用户手动确认后复制。
- `/data/workspaces`：用户在 Web 管理台创建项目时的默认工作区根目录。
- `/data/bin`：用户可追加安装自定义 agent CLI，已加入 PATH。

## 最小可运行路径
1. GitHub Workflow 构建并推送 `ghcr.io/codeeagle/lazycatimages:ccConnect_<sha>`。
2. `lzc-cli appstore copy-image` 复制到 `registry.lazycat.cloud/...`，写入 `.lazycat-images.json`。
3. 打包阶段把 manifest 中 `services.cc-connect.image` 渲染为 LazyCat 镜像。
4. 安装 `.lpk` 后打开 `https://cc-connect.<box>`，自动进入 Web 管理台。
5. 在 Web 管理台添加 provider、project 和聊天平台凭据，保存后重启/重载服务。

## 风险与限制
- Webhook 型平台需要公网回调；当前仅固定暴露 `/hook`，LINE/WeCom 等自定义 callback 端口需用户另行配置反代或优先使用长连接模式。
- 镜像内常见 Agent CLI 采用 best-effort 安装，若某个 npm 包在构建时不可用，用户仍可在 `/data/bin` 补装或配置外部 ACP agent。
- 首次没有项目时上游默认会拒绝启动；Dockerfile 在构建期打补丁，允许 management-only 配置启动以便通过 Web UI 初始化。

## 退出条件
- [x] 入口、端口、环境变量、真实写路径、初始化命令、数据库/auth 配置已确认
- [x] 构建策略相关文件（Dockerfile、entrypoint、patch 脚本）已补齐
- [ ] workflow 构建后真实镜像地址写入 `.lazycat-images.json`
- [ ] 可以进入预检、构建、下载 `.lpk`、安装验收阶段
