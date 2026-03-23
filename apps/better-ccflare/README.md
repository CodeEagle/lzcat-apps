# better-ccflare - 懒猫微服自动构建项目

> [!NOTE]
> 本项目是 [tombii/better-ccflare](https://github.com/tombii/better-ccflare) 的懒猫微服（LazyCat）移植版本，构建时会在应用专属 Dockerfile 中按版本拉取上游源码并执行 `bun run build`，避免直接依赖当前 release 二进制。

## 关于本项目

`better-ccflare` 是一个面向 Claude / Anthropic 生态的 API 代理，提供账号负载均衡、请求级日志、统计分析和 Web Dashboard。

本移植项目在 LazyCat 中保留了上游的单容器拓扑：

- 根路径 `/` 提供 dashboard
- `/v1/*` 提供代理接口
- `/api/*` 提供配置、账号和统计 API
- `/health` 提供健康检查

## 首次启动

应用首次启动后可以直接打开 dashboard，但要真正开始代理请求，仍需在应用内完成至少一种账号配置：

1. 进入 dashboard 的 `Accounts` 页面
2. 添加 Claude OAuth、Console API Key 或其他兼容 provider 账号
3. 如需远程访问，可在应用内生成 better-ccflare 自己的 API key

如果未配置任何账号，服务仍会启动，但上游会记录 “No active accounts available” 的提示。

## 环境变量

推荐保留默认值，只在有明确需求时修改：

- `LB_STRATEGY=session`
- `SESSION_DURATION_MS=18000000`
- `LOG_LEVEL=INFO`
- `LOG_FORMAT=pretty`
- `DATA_RETENTION_DAYS=7`
- `REQUEST_RETENTION_DAYS=365`

可选高级配置：

- `CLIENT_ID`：覆盖默认 OAuth client ID
- `DATABASE_URL`：改用 PostgreSQL；未设置时默认使用本地 SQLite
- `SSL_KEY_PATH` / `SSL_CERT_PATH`：启用 HTTPS

## 数据目录

LazyCat 中将以下内容统一持久化到 `/lzcapp/var/data/better-ccflare`：

- `better-ccflare.db`：SQLite 数据库
- `better-ccflare.json`：运行时配置文件
- `logs/`：应用日志目录

容器内对应挂载点为 `/home/bun/.config/better-ccflare`，同时保留 `/data` 兼容软链指向该目录。

## 迁移说明

- 上游项目：<https://github.com/tombii/better-ccflare>
- 上游文档：<https://github.com/tombii/better-ccflare/blob/main/docs/README.md>
- Docker 文档：<https://github.com/tombii/better-ccflare/blob/main/DOCKER.md>

当前构建配置锁定为 `linux/amd64`，以匹配现有 LazyCat 打包链路和源码编译目标。
