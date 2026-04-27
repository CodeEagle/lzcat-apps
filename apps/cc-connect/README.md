# cc-connect

cc-connect 把 Claude Code、Codex、Gemini CLI、OpenCode 等本地 AI coding agent 接入 Feishu/Lark、DingTalk、Slack、Telegram、Discord、LINE、WeCom、Weixin、QQ 等聊天平台。该 LazyCat 迁移版默认启动内置 Web 管理台，用于添加 provider、项目、平台凭据和会话。

## 上游项目
- Upstream Repo: chenhg5/cc-connect
- Homepage: https://github.com/chenhg5/cc-connect
- License: MIT
- Author: chenhg5
- Version Strategy: `github_release`，当前版本 `1.3.2`

## LazyCat 拓扑
- Service: `cc-connect`
- Web 管理台端口: `9820`
- Bridge WebSocket: `/bridge/ws`
- Webhook 路由: `/hook`
- 持久化目录: `/lzcapp/var/data/cc-connect` -> `/data`

首次启动会创建 `/data/config.toml`，默认开启 management、bridge 和 webhook。management token 为空时，构建补丁允许 Web 管理台 tokenless 自动登录，由 LazyCat 访问控制承担入口鉴权。

## 构建说明

`Dockerfile` 从上游 release tag 拉取源码：

1. Node 22 构建 `web/dist`。
2. Go 1.25 构建 `cmd/cc-connect` 并嵌入 Web 资源。
3. 运行时镜像携带 `cc-connect`、Node、git、sqlite3 以及常见 Agent CLI 的 best-effort npm 安装。

正式构建由 `trigger-build.yml` 执行，产物镜像地址通过 `.lazycat-images.json` 管理，仓库内 manifest 保持占位镜像。

## 使用

安装 `.lpk` 后打开应用入口，进入 Web 管理台：

1. 添加全局 provider 或按项目添加 provider。
2. 创建项目，工作目录建议放在 `/data/workspaces/<project>`。
3. 添加 Feishu/Lark、Telegram、Discord、Slack、Weixin 等平台凭据。
4. 保存后按页面提示重启或重载服务。

Webhook 型平台需要公网 callback；当前 LazyCat manifest 只固定暴露 `/hook`，其余自定义 callback 端口建议优先改成长连接模式或另行配置反代。
