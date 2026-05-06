# MarkItDown Web & MCP 上架文案

## 基础信息

- App: MarkItDown Web & MCP
- Slug: `markitdown`
- Package: `fun.selfstudio.app.migration.microsoft.markitdown-mcp`
- Version: `0.1.5`
- Homepage: https://github.com/microsoft/markitdown

## 一句话卖点

（懒猫微服自动构建）同时提供 Web 与 MCP 的 Markdown 转换服务

## 应用商店描述

（懒猫微服自动构建）同时提供 Web 与 MCP 的 Markdown 转换服务

## English Description

(LazyCat Auto-build) Web and MCP service for converting files and URLs to Markdown

## 关键词

`markitdown`, `LazyCat`, `self-hosted`, `自动移植`, `本地部署`

## Browser Use 验收证据

Codex Browser Use rendered MarkItDown, converted https://example.com to Markdown, and reported no console errors.

## README 可复用素材

[MarkItDown](https://github.com/microsoft/markitdown) 是 Microsoft 维护的文件与 URL 转 Markdown 工具。本仓库将它移植到懒猫微服，同时提供可直接在浏览器中使用的 Web 转换界面，以及可接入 MCP 客户端的 Streamable HTTP 与 SSE 入口。
- 上游仓库: https://github.com/microsoft/markitdown
- 上游主页: https://github.com/microsoft/markitdown
- 上游许可证: MIT
- 当前适配版本:
- `source_version`: `v0.1.5`
- `build_version`: `0.1.5`
迁移后的应用同时启动两个服务：
- Web API: `lazycat-markitdown web --host 0.0.0.0 --port 3000`
- MCP 服务: `lazycat-markitdown mcp --http --host 0.0.0.0 --port 3001`
对外提供以下入口：
- 首页: `https://<你的应用域名>/`

## 收益素材清单

- [ ] 应用功能截图：主页、核心操作、成功结果页
- [ ] 1 分钟教程：安装后第一步、核心任务、结果确认
- [ ] 功能亮点：为什么适合懒猫微服、哪些场景能节省时间
- [ ] 验收证据：Browser Use 通过、无阻塞 console/network 错误
- [ ] 上游依据：版本、许可证、主页、关键部署说明
