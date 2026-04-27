# cc-connect

cc-connect 把 Claude Code、Codex、Gemini CLI、OpenCode 等本地 AI coding agent 接入 Feishu/Lark、DingTalk、Slack、Telegram、Discord、LINE、WeCom、Weixin、QQ 等聊天平台。该 LazyCat 迁移版默认启动内置 Web 管理台，用于添加 provider、项目、平台凭据和会话。

## 上游项目
- Upstream Repo: chenhg5/cc-connect
- LazyCat Source Fork: CodeEagle/cc-connect
- Homepage: https://github.com/chenhg5/cc-connect
- License: MIT
- Author: chenhg5
- Version Strategy: `github_release`，当前版本 `1.3.3`

## LazyCat 拓扑
- Service: `cc-connect`
- Web 管理台端口: `9820`
- Bridge WebSocket: `/bridge/ws`
- Webhook 路由: `/hook`
- 持久化目录: `/lzcapp/var/data/cc-connect` -> `/data`

首次启动会创建 `/data/config.toml`，默认开启 management、bridge 和 webhook。management token 为空时，LazyCat source fork 允许 Web 管理台 tokenless 自动登录，由 LazyCat 访问控制承担入口鉴权。

## 构建说明

`Dockerfile` 从 `CodeEagle/cc-connect` LazyCat source fork 的 release tag 拉取源码。fork 基于上游 `v1.3.2`，并内置 Web Terminal、tokenless 管理台入口、Feishu 扫码保存修复和管理模式下的平台配置容错。

1. Node 22 构建 `web/dist`。
2. Go 1.25 构建 `cmd/cc-connect` 并嵌入 Web 资源。
3. 运行时镜像携带 `cc-connect`、Node、git、sqlite3，并默认安装 Claude Code、Codex、Gemini CLI、iFlow CLI、OpenCode、Kimi CLI 和 Qoder CLI。构建期安装失败会让 GitHub Workflow 失败，避免产出缺少默认 Agent 的 LPK。
4. 容器每次启动时会在后台重新执行 Agent CLI 更新，日志写入 `/data/state/agent-cli-update.log`。更新失败只记录 warning，不阻塞 cc-connect 启动；如需关闭，设置 `CC_CONNECT_UPDATE_AGENT_CLIS_ON_START=0`。

正式构建由 `trigger-build.yml` 执行，产物镜像地址通过 `.lazycat-images.json` 管理，仓库内 manifest 保持占位镜像。

## 使用

安装 `.lpk` 后打开应用入口，进入 Web 管理台：

1. 添加全局 provider 或按项目添加 provider。
2. 创建项目，工作目录建议放在 `/data/workspaces/<project>`。
3. 添加 Feishu/Lark、Telegram、Discord、Slack、Weixin 等平台凭据。
4. 保存后按页面提示重启或重载服务。

## Claude Code / Codex 接入

LazyCat 版运行在容器里，镜像已默认带上 Claude Code、Codex、Gemini CLI、iFlow CLI、OpenCode、Kimi CLI 和 Qoder CLI，但不能直接读取你电脑上的 `~/.claude`、`~/.codex` 或已登录的本地 CLI 状态。推荐做法是在 Web 管理台重新配置 Provider：

1. 在 `Providers` 添加 Anthropic/OpenAI 或兼容中转 Provider。
2. 在 `Projects` 创建项目，Agent 类型选择 `claudecode` 或 `codex`。
3. 工作目录使用 `/data/workspaces/<project>`。

这种方式不需要导入本机 CLI 凭据。cc-connect 会把 Provider API Key 注入 Claude Code/Codex；Codex 还会自动写入 `/data/home/.codex/auth.json`。

也可以直接在 Web 管理台打开 `Terminal` 页面。该页面是容器内的完整交互式 shell，支持手动执行 `claude login`、`codex login`、`gemini` 等登录流程，也可以执行普通开发命令。页面里的快捷按钮只负责把常用登录命令写入终端，不会限制你使用 shell。

如果必须复用本机已经登录的 Claude Code/Codex，请手动把本机配置复制进 LazyCat 容器的 `/data/home`。这些目录包含登录 token 和 API Key，只在确认接受把凭据上传到 LazyCat 盒子时执行：

```bash
cd /Volumes/ORICO/Development/Github/lzcat/lzcat-apps-cc-connect/apps/cc-connect

# Claude Code: OAuth/API 配置、commands、skills 等
lzc-cli project cp -s cc-connect --release ~/.claude /data/home/.claude
[ -f ~/.claude.json ] && lzc-cli project cp -s cc-connect --release ~/.claude.json /data/home/.claude.json

# Codex: auth.json、config.toml、skills、sessions 等
lzc-cli project cp -s cc-connect --release ~/.codex /data/home/.codex

# 可选：Codex 兼容的全局 skills 目录
[ -d ~/.agents/skills ] && lzc-cli project cp -s cc-connect --release ~/.agents/skills /data/home/.agents/skills

# 检查容器内 CLI 是否可见
lzc-cli project exec -s cc-connect --release -- bash -lc 'HOME=/data/home CODEX_HOME=/data/home/.codex claude --version && codex --version'
```

复制后在 System 页面执行 `Restart`，或重新安装/重启应用。Web 管理台的 Skills 页面会从 `/data/home/.claude/skills`、`/data/home/.codex/skills` 和 `/data/home/.agents/skills` 读取可用技能。

Webhook 型平台需要公网 callback；当前 LazyCat manifest 只固定暴露 `/hook`，其余自定义 callback 端口建议优先改成长连接模式或另行配置反代。
