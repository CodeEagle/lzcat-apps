# cc-connect 上架文案

## 基础信息

- App: cc-connect
- Slug: `cc-connect`
- Package: `fun.selfstudio.app.migration.cc-connect`
- Version: `1.3.2`
- Homepage: https://github.com/chenhg5/cc-connect
- License: MIT
- Source Author: chenhg5

## 一句话卖点

把 Claude Code、Codex、Gemini CLI 等本地 AI 编程 Agent 接入 Discord、Telegram、Slack、飞书等聊天平台。

## 应用商店描述

cc-connect 是一个面向开发者和自动化用户的多平台 Agent 桥接服务。安装到懒猫微服后，可以在浏览器中进入管理台，统一配置项目、Provider、Skills、聊天平台凭据和会话状态，把 Claude Code、Codex、Gemini CLI、OpenCode 等命令行 Agent 接入 Discord、Telegram、Slack、飞书、钉钉、企业微信、微信、QQ 等平台。

这个 LazyCat 迁移版默认开启 Web 管理台、Bridge WebSocket 和 Webhook 入口，并把运行数据、Agent home、CLI 登录态和工作区持久化到 `/data`。镜像内默认带有 Claude Code、Codex、Gemini CLI、iFlow CLI、OpenCode、Kimi CLI 和 Qoder CLI；容器重启时会在后台尝试更新这些 CLI，避免阻塞主服务启动。

为方便处理订阅制或浏览器登录式 CLI，本版本额外集成了 Web Terminal 页面。用户可以直接在管理台中打开完整容器 shell，手动执行 `claude login`、`codex login`、`gemini` 等登录流程，也可以在 `/data/workspaces` 下运行普通开发命令。对需要远程维护 Agent 会话的用户，这比在每个客户端单独配置 CLI 更稳定。

本次验收已确认应用入口可访问，管理台 Dashboard、Projects、Providers、System 和 Terminal 页面可渲染，`/api/v1/status` 返回正常，Web Terminal WebSocket 能打开 shell 并执行命令。

## English Description

cc-connect is a self-hosted bridge for connecting local AI coding agents such as Claude Code, Codex, Gemini CLI, OpenCode, and other command-line agents to chat platforms including Discord, Telegram, Slack, Lark, DingTalk, WeCom, WeChat, QQ, and more. The LazyCat package includes the web admin dashboard, bridge WebSocket, webhook endpoint, persistent agent home directories, bundled CLI tools, background CLI updates, and a full web terminal for manual login flows.

## 关键词

`cc-connect`, `Claude Code`, `Codex`, `Gemini CLI`, `AI Agent`, `Coding Agent`, `Discord`, `Telegram`, `Slack`, `飞书`, `自托管`, `LazyCat`, `懒猫微服`, `开发者工具`

## 适合截图的收益点

- Dashboard：展示版本、运行时长、平台数、项目数和最近会话。
- Terminal：展示完整容器 shell、CLI 登录快捷入口和 `/data/workspaces` 工作目录。
- Providers：展示全局 Provider 配置入口，适合说明可集中接入模型供应商。
- Projects：展示项目管理入口，适合说明可为不同仓库或任务配置不同 Agent。
- System：展示语言、附件、流式预览、限流、日志等级和原始 TOML 配置。

## Browser Use 验收证据

Chrome acceptance rendered the installed LazyCat entry for cc-connect, showed the CC-Connect Admin dashboard with version 1.3.2, confirmed Projects, Providers, Skills, Chat, Cron, System, and Terminal routes, and `/api/v1/status` returned `ok:true` with version `1.3.2`. A direct WebSocket check for `/api/v1/terminal/ws` returned `101 Switching Protocols`, opened a shell in `/data/workspaces`, and executed a harmless command successfully.

## 上架前核对清单

- [x] GitHub Workflow 构建成功。
- [x] Release LPK 已下载并核对 sha256。
- [x] LPK 内部 `manifest.yml` 包名和版本与仓库 manifest 一致。
- [x] `icon.png` 来自上游 `web/public/favicon.svg` 转换，包内 icon hash 与本地一致。
- [x] LazyCat 安装成功，应用状态为 `Status_Running`。
- [x] app 容器和 cc-connect 容器均为 healthy。
- [x] 管理台入口、状态 API 和 Web Terminal 通过验收。
- [x] 上架截图为网页内容截图，不含浏览器或桌面外框。
