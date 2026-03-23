# SigNoz

SigNoz 是一个开源可观测性平台，用来集中查看 traces、metrics 和 logs。这个 LazyCat 移植版基于 SigNoz 官方 Docker 社区版最小拓扑，包含 Web UI、OTLP Collector、ClickHouse 和 ZooKeeper。

## 上游项目

- 项目地址: https://github.com/SigNoz/signoz
- 官方主页: https://signoz.io
- 文档入口: https://signoz.io/docs/install/docker/
- 最新确认版本: `v0.116.1`

## 应用说明

本应用保留了官方 Docker 最小社区版的核心服务：

- `signoz`: Web UI 和 API，内部端口 `8080`
- `otel-collector`: OTLP 数据接收与转发，内部端口 `4318`
- `signoz-telemetrystore-migrator`: ClickHouse schema 初始化
- `clickhouse`: 遥测数据存储
- `zookeeper`: ClickHouse 集群元数据
- `init-clickhouse`: 初始化自定义 `histogramQuantile` 脚本

## 访问方式

- Web UI: `https://signoz.<你的 LazyCat 域名>`
- OTLP HTTP ingest: `https://ingest.signoz.<你的 LazyCat 域名>/v1/traces`

当前迁移版默认面向 OTLP HTTP 接入。原生 OTLP gRPC `4317` 没有通过 LazyCat HTTP 路由公开。

## 默认环境变量

以下配置已内置为单机社区版默认值：

- `SIGNOZ_ALERTMANAGER_PROVIDER=signoz`
- `SIGNOZ_TELEMETRYSTORE_CLICKHOUSE_DSN=tcp://clickhouse:9000`
- `SIGNOZ_SQLSTORE_SQLITE_PATH=/var/lib/signoz/signoz.db`
- `SIGNOZ_TOKENIZER_JWT_SECRET=secret`

## 数据目录

- `/lzcapp/var/data/signoz/sqlite`: SigNoz SQLite 元数据
- `/lzcapp/var/db/signoz/clickhouse`: ClickHouse 数据与 user scripts
- `/lzcapp/var/db/signoz/zookeeper`: ZooKeeper 数据

## 首次启动

首次启动时应用会自动：

1. 下载 `histogramQuantile` 到 ClickHouse user scripts 目录
2. 启动 ZooKeeper 和 ClickHouse
3. 执行 telemetrystore migrations
4. 启动 SigNoz UI/API 与 OTLP collector

第一次可用通常需要几分钟，取决于 ClickHouse 初始化速度。

## 使用建议

- 推荐优先使用 OTLP HTTP exporter，endpoint 指向 `https://ingest.signoz.<你的 LazyCat 域名>`
- 如果你的接入端只能使用 OTLP gRPC，需要额外的端口暴露能力，这不在当前 LazyCat HTTP 路由方案内
- SigNoz 属于较重型 observability 栈，建议为 ClickHouse 预留充足内存和磁盘
