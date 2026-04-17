# Copilot API Plus

将 GitHub Copilot 订阅转换为 OpenAI/Anthropic 兼容 API 代理，支持多账号管理和使用量监控。

## 上游项目

- Upstream Repo: CodeEagle/copilot-api-plus (fork of imbuxiangnan-cyber/copilot-api-plus)
- Homepage: https://github.com/imbuxiangnan-cyber/copilot-api-plus
- License: MIT
- Build Strategy: `upstream_dockerfile` (CodeEagle fork)
- Version Strategy: `github_release` → current `1.2.25`

## 访问入口

安装后通过微服地址访问：`https://copilot-api-plus.<your-device>.lazycat.cloud`

## 首次使用

1. 打开 Web 管理界面（访问上方地址）→「账号管理」标签
2. 点击「添加账号」，通过 GitHub Device Code 授权
3. 授权成功后，API 服务即可使用

## API 配置

将以下地址配置到 Claude Code、OpenCode 等工具：
- **OpenAI Base URL**: `https://copilot-api-plus.<device>.lazycat.cloud/v1`
- **Anthropic Base URL**: `https://copilot-api-plus.<device>.lazycat.cloud`

## 数据目录

| 宿主路径 | 容器路径 | 说明 |
|----------|----------|------|
| /lzcapp/var/data | /lzcapp/var/data | 账号信息 + GitHub Token 持久化 |

持久化文件：
- `github_token` — 单账号 Token（向后兼容）
- `accounts.json` — 多账号配置

## Fork 修改内容

CodeEagle fork 相对上游做了以下 LazyCat 适配：

- `entrypoint.sh`：移除强制 GH_TOKEN，允许无 Token 启动
- `src/lib/paths.ts`：支持 `COPILOT_API_DATA_DIR` 环境变量覆盖数据目录
- `src/start.ts`：启动时无 Token 时优雅跳过认证，避免设备码流程阻塞容器
- `src/server.ts`：`/` 路由提供内嵌 Web 管理 UI
- `Dockerfile`：将 `pages/` 打包进运行镜像
