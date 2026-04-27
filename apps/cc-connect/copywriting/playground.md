# cc-connect Playground 图文攻略

## 标题

把 AI 编程 Agent 接进聊天平台：cc-connect 懒猫微服上手

## 摘要

cc-connect 可以把 Claude Code、Codex、Gemini CLI 等本地 Agent 连接到 Discord、Telegram、Slack、飞书等聊天平台。这个 LazyCat 版本已经内置 Web 管理台、默认 Agent CLI、持久化 home 目录和 Web Terminal，适合把远程 Agent 会话长期放在自己的微服上运行。

## 第一步：打开 Dashboard

安装后打开应用，先确认 Dashboard 能显示版本、运行时长、平台数量和项目数量。

![Dashboard](../acceptance/cc-connect-desktop-home.png)

这一步的意义是确认三件事：

- Web 管理台已经启动。
- 后端管理 API 可用。
- LazyCat 路由已经进入真实应用，而不是平台错误页。

## 第二步：准备模型 Provider

进入 Providers 页面，添加 OpenAI、Anthropic 或兼容中转服务。Provider 是 Agent 执行任务时调用模型的入口。

![Providers](../acceptance/cc-connect-mobile-providers.png)

截图或分享教程时，不要展示 API Key、私有 endpoint、账号邮箱或任何 token。

## 第三步：创建项目工作区

进入 Projects 页面，为你的仓库或任务创建项目。推荐工作目录使用 `/data/workspaces/<project>`，这样后续 CLI 登录态、项目文件和任务上下文都留在微服上。

![Projects](../acceptance/cc-connect-mobile-projects.png)

项目粒度建议保持清晰：一个长期仓库、一个自动化任务或一个聊天平台入口，对应一个项目。

## 第四步：用 Terminal 登录 CLI

打开 Terminal 页面，可以看到完整容器 shell 和常用 CLI 登录按钮。

![Terminal](../acceptance/cc-connect-desktop-terminal.png)

常见命令：

```bash
claude login
codex login
gemini
```

登录后，凭据保存在 `/data/home` 下。这个目录会持久化，但也意味着其中内容很敏感，不要随意打包或公开。

## 第五步：调整系统设置

System 页面可以调整语言、附件发送、空闲超时、流式预览、限流和日志等级。

![System](../acceptance/cc-connect-mobile-system.png)

修改配置后，如果页面提示需要重载，可以点击 Reload config；如果 Agent CLI 或底层进程需要完整重启，则点击 Restart。

## 适合玩法

- 在 Discord 里创建项目线程，让 cc-connect 把消息转给 Codex 或 Claude Code。
- 在 Telegram 中发送简单维护任务，远程触发微服里的 Agent。
- 把常用项目放到 `/data/workspaces`，让不同电脑都能继续同一套远程工作流。
- 通过 Terminal 手动维护 CLI 登录态、检查版本或运行一次性命令。

## 安全提醒

cc-connect 面向开发者自动化场景。接入聊天平台和 CLI Agent 前，请先确认：

- 平台 bot token 和 Provider API Key 不会出现在公开截图中。
- Terminal 页面只开放给可信用户。
- 项目工作区中没有不应被 Agent 读取的私密文件。
- Webhook callback 只配置给你信任的平台。

## 一句话结尾

如果你想让 AI 编程 Agent 长期运行在自己的微服上，并通过聊天平台随时触发任务，cc-connect 是一个直接可用的桥接入口。
