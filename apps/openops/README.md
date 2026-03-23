# OpenOps

OpenOps 是一个开源的无代码 FinOps 自动化平台，提供工作流编排、OpenOps Tables 和 OpenOps Analytics，适合做成本优化、异常治理、资源回收与报表协作。

## 上游项目

- 项目地址: https://github.com/openops-cloud/openops
- 官方网站: https://openops.com
- 官方文档: https://docs.openops.com
- 最新移植基线: `0.6.23`（上游 release，2026-03-18）

## LazyCat 部署拓扑

本移植保留上游官方 docker-compose 的核心服务拆分：

- `openops-app`: 主 Web UI 与 API
- `openops-engine`: 工作流执行引擎
- `openops-tables`: OpenOps Tables（Baserow）
- `openops-analytics`: OpenOps Analytics（Superset）
- `postgres`: 主数据库，同时初始化 `openops`、`tables`、`analytics`
- `redis`: 队列与缓存

LazyCat 路由层直接承担官方 `nginx` 网关职责，因此外部访问入口保持不变：

- 主站: `https://openops.<你的域名>/`
- Tables: `https://openops.<你的域名>/openops-tables`
- Analytics: `https://openops.<你的域名>/openops-analytics`

## 首次启动

首次安装后需要等待几分钟，系统会自动：

1. 初始化 PostgreSQL 主库、Tables 库和 Analytics 库
2. 启动 Redis、Tables、Analytics
3. 启动 OpenOps App 与 Engine

默认管理员账号会按 manifest 自动生成：

- 邮箱: `admin@<你的应用域名>`
- 密码: `<你的应用 ID>-admin`

建议首次登录后立即修改管理员密码，并替换默认 JWT / encryption secret。

## 关键环境变量

以下变量已经在 manifest 中提供默认值，通常开箱即可运行：

- `OPS_PUBLIC_URL`
- `OPS_ENGINE_URL`
- `OPS_POSTGRES_*`
- `OPS_OPENOPS_TABLES_*`
- `OPS_ANALYTICS_*`

如需对接云账号或第三方系统，可按上游文档补充：

- `OPS_SLACK_APP_SIGNING_SECRET`
- `OPS_ENABLE_HOST_SESSION`
- Azure CLI 会话目录: `/lzcapp/var/data/openops/azure`
- Google Cloud CLI 会话目录: `/lzcapp/var/data/openops/gcloud`

## 数据目录

- `/lzcapp/var/db/openops/postgres`: PostgreSQL 数据
- `/lzcapp/var/db/openops/init`: PostgreSQL 初始化脚本落点
- `/lzcapp/var/data/openops/tables`: Tables 数据
- `/lzcapp/var/data/openops/analytics`: Analytics 本地状态
- `/lzcapp/var/data/openops/redis`: Redis 数据
- `/lzcapp/var/data/openops/cache`: App 缓存
- `/lzcapp/var/data/openops/config`: App 配置
- `/lzcapp/var/data/openops/engine/codes`: Engine 运行时代码目录
- `/lzcapp/var/data/openops/azure`: Azure CLI 会话目录
- `/lzcapp/var/data/openops/gcloud`: Google Cloud CLI 会话目录

## 说明

- 本移植默认关闭遥测上报（`OPS_TELEMETRY_MODE=NONE`）
- 若上游 `public.ecr.aws/openops/*` 镜像发生限流，需要重新执行镜像复制后再正式构建
