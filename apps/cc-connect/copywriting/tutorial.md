# cc-connect 图文使用教程

## 适用人群

cc-connect 适合希望把 AI 编程 Agent 放到自己的懒猫微服中长期运行，并通过聊天平台远程触发任务的用户。它不是普通聊天机器人，而是一个 Agent 桥接层：一边连接 Discord、Telegram、Slack、飞书等平台，一边管理 Claude Code、Codex、Gemini CLI 等本地命令行 Agent。

## 01 打开管理台

安装完成后，在懒猫微服中打开 cc-connect，或访问：

```text
https://cc-connect.<你的盒子域名>/
```

正常启动后会进入 Dashboard。这里可以看到当前版本、运行时长、平台数量、项目数量和最近会话。

![cc-connect Dashboard](../acceptance/cc-connect-desktop-home.png)

如果页面一直空白、显示平台错误页或返回 5xx，先检查应用状态和容器日志。正常验收时，`/api/v1/status` 应返回 `ok:true`。

## 02 配置 Provider

进入 Providers 页面，添加你的模型供应商配置。可以添加 OpenAI、Anthropic 或兼容中转服务。Provider 是后续项目和 Agent 调用模型的基础。

![Provider 配置入口](../acceptance/cc-connect-mobile-providers.png)

公开截图时不要展示真实 API Key、账号名、私有模型地址或中转服务密钥。

## 03 创建项目

进入 Projects 页面，点击 Add project。建议把项目工作目录放在：

```text
/data/workspaces/<project>
```

这样项目文件、会话状态和 CLI 运行数据都能跟随 LazyCat 持久化目录保存。

![项目管理入口](../acceptance/cc-connect-mobile-projects.png)

每个项目可以选择不同 Agent 类型，例如 Claude Code、Codex 或其他 CLI Agent，并绑定对应 Provider。

## 04 打开 Terminal 完成 CLI 登录

某些 CLI 需要交互式登录或浏览器授权。cc-connect 的 LazyCat 版本内置了 Terminal 页面，可以在浏览器中打开完整容器 shell。

![Web Terminal](../acceptance/cc-connect-desktop-terminal.png)

常用登录命令包括：

```bash
claude login
codex login
gemini
iflow login
opencode auth login
kimi login
qodercli login
```

Terminal 默认工作目录是 `/data/workspaces`。登录态会保存在 `/data/home` 下，例如 `/data/home/.claude` 和 `/data/home/.codex`。这些目录包含敏感凭据，不要公开截图。

## 05 配置平台入口

根据你要接入的平台，在管理台中填写对应 token、webhook、slash command 或 bot 凭据。Webhook 类型的平台可以使用 LazyCat 暴露的 `/hook` 入口；长连接类型的平台则按上游说明配置。

## 06 系统设置

System 页面提供语言、附件转发、Agent 空闲超时、流式预览、限流、日志等级和原始 TOML 配置等选项。

![系统设置](../acceptance/cc-connect-mobile-system.png)

配置变更后，可以在 System 页面执行 Reload config 或 Restart。重启时，容器会在后台尝试更新默认 Agent CLI，不会阻塞主服务启动。

## 验收记录

本次迁移已完成以下验收：

- LazyCat 安装成功，应用状态为 `Status_Running`。
- `app` 与 `cc-connect` 容器均为 healthy。
- Web 管理台 Dashboard 渲染成功，版本显示为 `1.3.3`。
- `/api/v1/status` 返回 `ok:true`。
- Terminal WebSocket 返回 `101 Switching Protocols`。
- Terminal shell 位于 `/data/workspaces`，可执行普通命令。
- 上架截图由 Playwright 页面截图脚本生成，不包含浏览器外框。

## 常见问题

**看不到本机 Claude Code 或 Codex 登录状态**

LazyCat 容器不会自动读取你电脑上的 `~/.claude` 或 `~/.codex`。推荐在 Terminal 页面中重新登录；如果要复制本机凭据，请确认你接受把 token 上传到微服后再执行。

**Provider 配好了但 Agent 没有回复**

检查项目是否绑定了正确 Provider、模型名是否可用、平台消息是否已经进入 cc-connect 会话。

**Webhook 平台回调失败**

确认平台配置的 callback 路径指向 LazyCat 应用的 `/hook`，并检查平台 token 与 cc-connect 配置是否一致。

**重启后 CLI 更新很久**

CLI 更新在后台执行，日志写入 `/data/state/agent-cli-update.log`。更新失败只记录 warning，不影响管理台启动。
