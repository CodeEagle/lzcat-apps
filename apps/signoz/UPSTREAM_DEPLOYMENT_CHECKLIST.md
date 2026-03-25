# SigNoz Upstream Deployment Checklist

## 已确认字段

- PROJECT_NAME: SigNoz
- PROJECT_SLUG: signoz
- UPSTREAM_REPO: SigNoz/signoz
- UPSTREAM_URL: https://github.com/SigNoz/signoz
- HOMEPAGE: https://signoz.io
- LICENSE: Apache-2.0
- AUTHOR: SigNoz
- VERSION: 0.116.1
- IMAGE: signoz/signoz:v0.116.1
- PORT: 8080

## 真实启动入口

- 官方 compose: `deploy/docker/docker-compose.yaml`
- 主服务: `signoz`
- collector: `signoz-otel-collector`
- 初始化链:
  - `init-clickhouse` 下载 `histogramQuantile`
  - `otel-collector migrate bootstrap`
  - `otel-collector migrate sync up`
  - `otel-collector migrate async up`
  - `otel-collector migrate sync check`

## 真实写路径

- ClickHouse data: `/var/lib/clickhouse`
- ClickHouse user scripts: `/var/lib/clickhouse/user_scripts`
- ZooKeeper data: `/bitnami/zookeeper`
- SigNoz sqlite: `/var/lib/signoz`
- Collector runtime temp: `/var/tmp`

## 配置文件

- ClickHouse cluster config: `deploy/common/clickhouse/cluster.xml`
- ClickHouse users config: `deploy/common/clickhouse/users.xml`
- ClickHouse custom function: `deploy/common/clickhouse/custom-function.xml`
- Collector config: `deploy/docker/otel-collector-config.yaml`
- OpAMP config: `deploy/common/signoz/otel-collector-opamp-config.yaml`

## 外部依赖

- ClickHouse
- ZooKeeper
- SQLite

## LazyCat 适配结论

- 保留官方多服务拓扑，不压成单容器。
- ClickHouse 需要额外注入 `cluster.xml`、`users.xml`、`custom-function.xml` 和单机 `macros.xml`。
- collector 不能直接沿用上游 `/etc` 写入路径，配置改复制到 `/var/tmp`。
- collector 不使用 OpAMP manager-config，避免 `cannot create agent without orgId` 启动阻塞。
- 显式设置 `SIGNOZ_PROMETHEUS_ACTIVE__QUERY__TRACKER_PATH`，避免默认空路径触发 active query tracker 目录报错。
