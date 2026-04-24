# copilot-api-plus

本目录用于把上游 `CodeEagle/copilot-api-plus` 移植为懒猫微服应用。

## 上游项目
- Upstream Repo: CodeEagle/copilot-api-plus
- Homepage: https://github.com/CodeEagle/copilot-api-plus
- License: MIT
- Author: CodeEagle
- Version Strategy: `commit_sha` -> 当前基线版本 `1.2.14`

## 当前迁移骨架
- Build Strategy: `upstream_dockerfile`
- Primary Subdomain: `copilot-api-plus`
- Image Targets: `copilot-api-plus`
- Service Port: `4141`

### Services
- `copilot-api-plus` -> 构建时由 `.lazycat-images.json` 渲染为 LazyCat 加速镜像

## Overlay

- `pages/index.html`：覆盖上游 Web UI，修复 `/usage` 成功返回后 `mode is not defined` 导致概览区停留在 loading 状态的问题，并修复「运行统计」标签无法切换的问题。

## AIPod

当前未启用 AIPod / AI 服务。

## 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `PORT` | `4141` | Web/API 服务监听端口 |
| `COPILOT_API_DATA_DIR` | `/lzcapp/var/data/copilot-api-plus` | LazyCat 持久化数据目录 |
| `HTTP_PROXY` / `HTTPS_PROXY` / `NO_PROXY` | 空 | 可选代理配置 |
| `VERBOSE` | 空 | 可选详细日志 |

## 数据目录

| 宿主路径 | 容器路径 | 内容 |
| --- | --- | --- |
| `/lzcapp/var/data/copilot-api-plus` | `/lzcapp/var/data/copilot-api-plus` | `github_token`、`accounts.json`、`config.json` |

## 首次启动/验收提醒

- 上游 Dockerfile 构建后运行 `/entrypoint.sh`，默认执行 `bun run dist/main.js start`。
- 应用自身没有本地账号密码登录；GitHub Copilot 账号在 Web UI 中通过 Device Code 流程添加。
- 未添加账号前，首页和管理接口可访问，需要 Copilot 账号的模型/API 调用会按上游逻辑返回未认证状态。

## 下一步

1. 执行 `python3 scripts/full_migrate.py https://github.com/CodeEagle/copilot-api-plus --repo-root . --resume-from 7 --build-mode reinstall`。
2. 安装生成的 `.lpk` 并确认首页、管理接口和 OpenAI/Anthropic 兼容端点可达。
