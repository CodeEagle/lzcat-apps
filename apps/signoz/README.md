# SigNoz

SigNoz 是一个基于 OpenTelemetry 的开源可观测性平台，提供 traces、metrics 和 logs 的统一查看入口。

## 上游信息

- Upstream Repo: `SigNoz/signoz`
- Homepage: `https://signoz.io`
- License: `Apache-2.0`
- Default Version: `0.116.1`

## 服务拓扑

- `signoz`: Web UI 和 query-service，入口端口 `8080`
- `clickhouse`: Telemetry 数据存储
- `zookeeper-1`: ClickHouse replication / cluster metadata
- `init-clickhouse`: 预下载 `histogramQuantile` 可执行文件
- `otel-collector`: 执行 migration 并暴露 OTLP 接收端

## 持久化目录

- `/lzcapp/var/db/signoz/clickhouse` -> `/var/lib/clickhouse`
- `/lzcapp/var/db/signoz/zookeeper` -> `/bitnami/zookeeper`
- `/lzcapp/var/data/signoz/sqlite` -> `/var/lib/signoz`

## 访问方式

- UI: `https://signoz.${LAZYCAT_BOX_DOMAIN}`

## 说明

- 该移植基于上游官方 `deploy/docker/docker-compose.yaml` 拆分。
- ClickHouse 配置和 collector 配置放在 `content/` 下，通过 `lzc-build.yml` 打包进 `.lpk`。
- collector 采用静态配置启动，不使用 OpAMP manager-config，避免首次启动阶段因 `orgId` 缺失阻塞。
