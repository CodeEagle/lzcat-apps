# Codex Web 上架文案

## 基础信息

- App: Codex Web
- Slug: `codex-web`
- Package: `fun.selfstudio.app.migration.codex-web`
- Version: `0.1.2`
- Homepage: https://github.com/0xcaff/codex-web
- License: MIT
- Source author: 0xcaff
- Original/source-author declaration: `false`

## 一句话卖点

在懒猫微服里打开一个可持久化的 Codex CLI 浏览器工作台。

## 应用商店描述

Codex Web 将上游 `0xcaff/codex-web` 打包为可直接安装的懒猫微服应用，让你在浏览器中使用运行于自己设备上的 Codex CLI 工作台。应用提供聊天入口、项目工作区、插件管理和自动化入口，并把 Codex 登录状态、会话数据、缓存和工作目录持久化到懒猫应用数据目录。

适合希望把 Codex 会话放在自有设备中运行、通过浏览器随时接入、并保留项目上下文和插件配置的用户。首次使用前，需要在服务容器内执行 `codex login --device-auth` 完成 Codex CLI 登录；之后登录状态会保存在 `/data/home/.codex` 中并随应用重启保留。

## English Description

Codex Web packages the upstream `0xcaff/codex-web` project as a LazyCat Microserver app. It gives you a browser workspace for Codex CLI running on your own device, with chat, project workspace access, plugin management, automation entry points, and persistent Codex session data.

Before starting real sessions, sign in to Codex CLI inside the service container with `codex login --device-auth`. The login state is stored under `/data/home/.codex` and survives app restarts.

## 使用须知

- 首次使用需要完成 Codex CLI 设备登录。
- 应用默认信任能访问懒猫入口的用户，请保持入口受懒猫访问控制保护。
- `/data/home/.codex` 保存 Codex 登录和会话状态，`/workspace` 是默认工作目录。
- 该应用为上游开源项目移植包，不声明为原创应用。

## 关键词

`codex-web`, `Codex`, `Codex CLI`, `LazyCat`, `self-hosted`, `浏览器工作台`, `本地部署`

## Browser Use 验收证据

Playwright browser opened the installed LazyCat Codex Web 0.1.2 entry URL, rendered chat/project/plugin UI, and recorded no blocking console or network failures.

## README 可复用素材

Codex Web is a browser frontend for Codex Desktop. This LazyCat package builds the upstream `0xcaff/codex-web` project from source, bundles the Codex CLI, and exposes the Fastify/WebSocket bridge on port `8214`.

- Repository: https://github.com/0xcaff/codex-web
- License: MIT
- Author: 0xcaff
- Version strategy: upstream commit SHA, packaged as `0.1.2`
- Service: `codex-web`
- Internal port: `8214`
- Public entry: `/`
- Runtime command: `node /opt/codex-web/src/server/main.js --host 0.0.0.0 --port 8214`
- Persistent Codex data: `/data/home/.codex`
- Workspace path: `/workspace`

## 截图素材

- `apps/codex-web/store-submission/assets/screenshots/01-desktop-overview.png`
- `apps/codex-web/store-submission/assets/screenshots/02-desktop-plugins.png`
- `apps/codex-web/store-submission/assets/screenshots/03-mobile-overview.png`
- `apps/codex-web/store-submission/assets/screenshots/04-mobile-project.png`
- `apps/codex-web/store-submission/assets/screenshots/05-mobile-model.png`
