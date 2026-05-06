# Fusion Upstream Deployment Checklist

## 已确认字段

- PROJECT_NAME: Fusion
- PROJECT_SLUG: fusion
- UPSTREAM_REPO: Runfusion/Fusion
- UPSTREAM_URL: https://github.com/Runfusion/Fusion
- HOMEPAGE: https://runfusion.ai
- LICENSE: MIT
- AUTHOR: Runfusion
- VERSION: 0.9.1
- IMAGE: workflow 构建后写入 `apps/fusion/.lazycat-images.json`
- PORT: 4040
- CHECK_STRATEGY: github_release
- BUILD_STRATEGY: upstream_with_target_template

## 上游部署清单

- Dockerfile: 上游根目录 `Dockerfile`
- 官方 Docker 文档: `docs/docker.md`
- 官方启动入口: `ENTRYPOINT ["node", "packages/cli/dist/bin.js"]` + `CMD ["dashboard"]`
- LazyCat 启动入口: `node /opt/fusion/packages/cli/dist/bin.js dashboard --host 0.0.0.0 --port 4040 --no-auth`
- 服务监听: `PORT=4040`，LazyCat upstream 指向 `http://fusion:4040/`
- 健康检查: `GET /api/tasks`
- 初始化命令: 无独立数据库迁移；首次启动会创建 `/project/.fusion` 与 `~/.fusion`
- 外部依赖: 无数据库、Redis、对象存储依赖
- 登录机制: Dashboard 默认 bearer token；LazyCat 包使用 `--no-auth` 关闭应用内 token 登录，由 LazyCat 入口承担访问控制，避免首次打开手工复制 token

## 环境变量

- `NODE_ENV=production`
- `PORT=4040`
- `HOME=/home/node`
- `XDG_CONFIG_HOME=/home/node/.config`
- `XDG_CACHE_HOME=/home/node/.cache`
- `XDG_DATA_HOME=/home/node/.local/share`
- `XDG_STATE_HOME=/home/node/.local/state`
- `OPENAI_API_KEY`（可选，部署参数注入）
- `ANTHROPIC_API_KEY`（可选，部署参数注入）
- `OPENROUTER_API_KEY`（可选，部署参数注入）
- `GITHUB_TOKEN`（可选，部署参数注入）

## 数据路径与权限

- `/project`: 持久化项目工作区，包含用户仓库、`.fusion` 项目数据库、任务目录、附件与 `.worktrees`
- `/home/node`: 持久化 Fusion 全局设置、provider auth、模型 registry、SSH 配置、cache 与本地状态
- 写入用户: `node`，UID/GID `1000:1000`
- 预创建: 启动命令在执行 `gosu node` 前创建 `/project`, `/project/.fusion`, `/project/.worktrees`, `/home/node/.fusion`, `/home/node/.ssh`, `/home/node/.config`, `/home/node/.cache`, `/home/node/.local/share`, `/home/node/.local/state`
- 目录模式: `/project` 0755；home 内认证/配置目录 0700

## 构建修正

- 上游 Dockerfile 当前生产安装过滤器仍引用旧包名 `@gsxdsm/fusion`；LazyCat 模板改为 `@runfusion/fusion...`
- 上游 dashboard `./planning` 子路径导出指向 TypeScript source；模板在构建和运行镜像中把 runtime import 修正为 `./dist/planning.js`
- 上游 CLI 启动时会 import `typebox`，但当前包元数据未把它放入 production dependencies；runner 阶段保留选中 workspace 的 dev dependencies，避免启动时报 `ERR_MODULE_NOT_FOUND`
- 构建方式为克隆上游 tag 后用 `Dockerfile.template` 覆盖根 Dockerfile，不直接修改上游仓库

## 最小可运行路径

1. GitHub workflow 执行 `scripts/run_build.py fusion --force-build`
2. workflow 克隆 `Runfusion/Fusion` 最新 release/tag，应用 `Dockerfile.template` 构建 GHCR 镜像
3. workflow 复制镜像到 `registry.lazycat.cloud` 并生成 `.lpk`
4. 安装 `.lpk` 后容器启动，创建持久化目录，监听 `4040`
5. LazyCat 入口打开 `/`，Dashboard 可访问并展示首屏/项目初始化流程

## 当前风险

- Fusion 完整自动执行能力依赖用户在 `/project` 中准备真实 git 仓库，并配置模型 provider 凭据
- 未完成 workflow 构建、`.lpk` 下载和真实 LazyCat Browser Use 验收前，`migration_status` 保持 `in_progress`
