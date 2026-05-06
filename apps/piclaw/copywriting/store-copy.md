# PiClaw 上架文案

## 基础信息

- App: PiClaw
- Slug: `piclaw`
- Package: `fun.selfstudio.app.migration.piclaw`
- Version: `2.0.1`
- Homepage: https://github.com/CodeEagle/piclaw
- License: MIT

## 一句话卖点

把 Pi Coding Agent 放进懒猫微服，在浏览器里管理本地 AI 编程会话、项目工作区和长期任务记录。

## 应用商店描述

PiClaw 是面向开发者的自托管 AI 编程工作台。安装到懒猫微服后，可以通过浏览器访问聊天式编程界面，管理 `@piclaw` 会话、搜索历史任务，并把配置与工作区持久化保存在微服上。

这个移植版适合想把 AI 编程助手从个人电脑搬到家庭/团队微服的用户：常用项目、会话状态、运行日志和模型配置可以集中放在盒子里，局域网或远程访问时打开网页即可继续工作。对上架审核而言，本次验收已确认应用不是空白页、平台错误页或循环启动页，而是进入了真实 PiClaw 主界面。

## English Description

PiClaw is a self-hosted Pi Coding Agent workspace for LazyCat. It provides a browser-based coding-agent chat UI, session controls, search, and persistent project storage so developers can keep AI coding workflows running on their own microserver.

## 关键词

`PiClaw`, `piclaw`, `AI 编程`, `Coding Agent`, `自托管`, `LazyCat`, `懒猫微服`, `开发者工具`, `项目工作区`

## 适合截图的收益点

- 主界面：展示 `@piclaw` 会话、消息输入框、会话管理和搜索入口。
- 首次配置：展示打开设置后可配置 AI providers/models，说明安装后可接入用户自己的模型。
- 工作区价值：突出 `/workspace` 持久化，适合长期项目、文档和任务记录。
- 审核证据：展示 Browser Use 验收通过，证明应用启动、路由、静态资源和后端连接正常。

## 推荐宣传角度

- 对个人开发者：把 AI 编程助手常驻在自己的微服里，换设备也能继续同一个工作区。
- 对小团队：把演示项目、自动化脚本和协作记录沉淀到统一入口，减少每台电脑重复配置。
- 对 LazyCat 用户：安装后即可通过 `https://piclaw.<盒子域名>/` 使用，不需要自己准备 Docker、Bun、Node 或系统依赖。

## Browser Use 验收证据

Codex Browser Use opened the installed LazyCat app at https://piclaw.rx79.heiyu.space/. The app rendered the PiClaw main chat UI instead of the LazyCat startup page, showed the message composer/session controls, and browser console logs contained no errors or warnings. LazyCat containers were running with funselfstudioappmigrationpiclaw-app-1 healthy and the supervisor-managed piclaw process entered RUNNING state.

## 上架前核对清单

- [x] 安装后入口可访问：`https://piclaw.rx79.heiyu.space/`
- [x] 主界面渲染成功：页面标题 `PiClaw`，可见消息输入框、会话管理、搜索、菜单等控件
- [x] 浏览器错误检查：Browser Use console error/warn 为空
- [x] 容器状态：`funselfstudioappmigrationpiclaw-app-1` healthy，`pibox` 运行中
- [x] Supervisor 状态：`piclaw` 进入 RUNNING 状态
- [ ] 补充上架截图：主页、设置页、一次成功会话
- [ ] 补充运营素材：1 分钟安装后上手短视频
