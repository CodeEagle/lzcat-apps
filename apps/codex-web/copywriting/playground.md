# 在懒猫微服上使用 Codex Web

![Codex Web 首页](../acceptance/01-desktop-overview.png)

## 为什么值得装

Codex Web 把 Codex CLI 的工作台搬进浏览器，并运行在自己的懒猫微服上。你可以从任意受信入口打开聊天界面，选择项目目录，管理插件，并让 Codex 的登录状态和会话数据随应用重启保留。

## 安装后先做这件事

1. 安装 Codex Web。
2. 打开应用入口，确认首页出现 “What should we work on?”。
3. 进入服务容器执行 `codex login --device-auth`。
4. 回到浏览器，开始创建聊天或进入项目工作区。

![插件管理界面](../acceptance/02-desktop-plugins.png)

## 适合这些场景

- 希望把 Codex CLI 会话放在自己的设备上运行。
- 希望通过浏览器进入 Codex 工作台，而不是只依赖本地桌面。
- 希望保留插件、项目和会话状态，减少重复配置。

![移动端首页](../acceptance/03-mobile-overview.png)

![移动端紧凑视图](../acceptance/04-mobile-compact.png)

![移动端高屏视图](../acceptance/05-mobile-tall.png)

## 我们验证了什么

已在真实安装的懒猫应用实例中打开 `https://codex-web.rx79.heiyu.space`，页面渲染出聊天、项目和插件 UI；截图覆盖桌面与移动视口；浏览器验收未发现阻塞 console 或 network 错误。

## 上游信息

- 项目主页：https://github.com/0xcaff/codex-web
- 上游作者：0xcaff
- License: MIT
- 懒猫版本：0.1.2

Codex Web 懒猫版是上游开源项目的移植包，不把移植包声明为原创应用。
