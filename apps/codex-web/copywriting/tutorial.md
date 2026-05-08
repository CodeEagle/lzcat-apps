# Codex Web 使用教程

## 适用人群

适合希望在懒猫微服中运行 Codex CLI，并通过浏览器进入聊天、项目、插件和自动化界面的用户。

## 安装后第一步

1. 在懒猫微服中安装 Codex Web。
2. 打开 `https://codex-web.<你的盒子域名>/`。
3. 进入服务容器，执行 `codex login --device-auth` 完成 Codex CLI 登录。
4. 回到浏览器页面，确认首页出现 “What should we work on?” 输入区。

## 核心流程

1. 点击 `Project` 选择或确认工作目录。
2. 在首页输入任务描述，或通过输入框左侧按钮添加上下文。
3. 根据需要调整模型和权限模式。
4. 进入 `Plugins` 管理可用插件或技能。
5. 后续重启应用时，Codex 登录状态会从 `/data/home/.codex` 恢复。

## 数据持久化

- `/data/home/.codex` 保存 Codex CLI 登录、配置和会话状态。
- `/data/cache`、`/data/config`、`/data/share`、`/data/tmp` 提供运行时可写目录。
- `/workspace` 是默认工作目录，映射到懒猫应用数据目录。

## 验收记录

Playwright browser opened the installed LazyCat Codex Web 0.1.2 entry URL, rendered chat/project/plugin UI, and recorded no blocking console or network failures.

## 常见问题

- 如果页面打不开，先检查应用状态和容器健康状态。
- 如果页面能打开但无法执行 Codex 会话，确认是否已经完成 `codex login --device-auth`。
- 如果插件页面首次加载较慢，等待插件列表初始化完成后再操作。
- 应用默认信任可访问入口的用户，请保持懒猫入口由系统访问控制保护。
