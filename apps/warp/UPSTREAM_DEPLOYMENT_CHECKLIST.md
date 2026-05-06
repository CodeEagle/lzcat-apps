# warp Upstream Deployment Checklist

## 已确认字段

- PROJECT_NAME: Warp
- PROJECT_SLUG: warp
- UPSTREAM_REPO: warpdotdev/warp
- UPSTREAM_URL: https://github.com/warpdotdev/warp
- HOMEPAGE: https://www.warp.dev
- LICENSE: AGPL-3.0-or-later for most code; MIT for `warpui_core` and `warpui`
- AUTHOR: warpdotdev
- VERSION: source package `0.2026.04.27.15.32.stable.02`; LazyCat semver `2026.4.27`
- IMAGE: self-built LazyCat image from `apps/warp/Dockerfile`
- PORT: 8080
- CHECK_STRATEGY: commit_sha
- BUILD_STRATEGY: target_repo_dockerfile

## 上游部署清单

- 官方仓库没有生产 Web 服务 compose；`docker/linux-dev/Dockerfile` 是 Linux 开发容器，只暴露 SSH 22，并依赖外部 XQuartz/X11。
- `docker/agent-dev/Dockerfile` 是 agent/build/test 开发环境，不是 Warp 终端运行镜像。
- 官方 Linux 分发形态是 `.deb` / `.rpm` / `.pkg.tar.zst` / AppImage；本迁移使用 Debian apt 仓库安装 `warp-terminal`。
- 真实启动入口：容器内 `warp-terminal`，通过 `Xvfb` + `fluxbox` + `x11vnc` + `noVNC` 暴露给 LazyCat 浏览器入口。
- 首次启动初始化：无需数据库迁移；启动前创建 `/home/warp`、`/workspace`、`/tmp/runtime-warp` 和 XDG 目录，并将 owner 调整为 uid/gid 1000。
- 数据库/Redis/对象存储：无本地外部依赖；Warp 云端/AI 功能仍调用上游服务并由用户登录。
- 登录机制：Warp 自身登录发生在上游桌面 UI 内，本包没有新增 LazyCat 免密登录层。

## 真实写路径

- `/home/warp/.warp`: Warp 用户可见配置、skills、MCP 配置等，持久化在 `/lzcapp/var/data/warp/home`。
- `/home/warp/.config/warp-terminal`: Linux 本地配置，持久化在 `/lzcapp/var/data/warp/home`。
- `/home/warp/.local/share/warp-terminal`: Linux 数据目录，持久化在 `/lzcapp/var/data/warp/home`。
- `/home/warp/.local/state/warp-terminal`: Linux state 目录，持久化在 `/lzcapp/var/data/warp/home`。
- `/home/warp/.cache/warp-terminal`: Warp cache，持久化在 `/lzcapp/var/data/warp/home`。
- `/home/warp/.ssh`、shell dotfiles: 终端使用所需用户文件，持久化在 `/lzcapp/var/data/warp/home`。
- `/workspace`: 用户项目目录，持久化在 `/lzcapp/var/data/warp/workspace`。
- `/tmp/runtime-warp`: XDG runtime 目录，运行期创建，非持久化。

## 当前服务拓扑

- `warp`
  - image: `registry.lazycat.cloud/placeholder/warp:bootstrap`
  - backend: `http://warp:8080/`
  - command: image entrypoint starts supervisor
  - persistent binds: `/home/warp`, `/workspace`
  - healthcheck: `GET /vnc.html`

## 脚本缺口记录

`scripts/full_migrate.py` 已执行并在 `[2/10]` 停止，原因是上游被识别为原生桌面/CLI/SDK 项目而非 HTTP 微服。当前 noVNC 桌面封装需要自定义 apt 安装、X11/noVNC 运行时和持久化 home 设计，本轮先手工落地应用文件；后续如要复用到更多桌面应用，再抽象为通用 native-desktop noVNC 路线。

## 退出条件

- [x] 入口、端口、启动方式、真实写路径已确认
- [x] AGPL/MIT 许可证与商标风险已记录
- [x] `lzc-manifest.yml`、`lzc-build.yml`、Dockerfile、README、图标已补齐
- [ ] GitHub Workflow 构建成功
- [ ] `.lpk` 下载并核对
- [ ] LazyCat 安装验收和 Browser Use 功能验收通过
