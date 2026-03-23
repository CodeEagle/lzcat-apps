# SigNoz Upstream Deployment Checklist

## Project Metadata

- PROJECT_NAME: SigNoz
- PROJECT_SLUG: signoz
- UPSTREAM_REPO: SigNoz/signoz
- UPSTREAM_URL: https://github.com/SigNoz/signoz
- HOMEPAGE: https://signoz.io
- LICENSE: MIT (community code outside `ee/` and `cmd/enterprise/`; upstream repo also carries enterprise-licensed paths)
- AUTHOR: SigNoz Inc.
- VERSION: 0.116.1

## Upstream Images And Versions

- `signoz/signoz:v0.116.1`
- `signoz/signoz-otel-collector:v0.144.2`
- `clickhouse/clickhouse-server:25.5.6`
- `signoz/zookeeper:3.7.1`

## Upstream Topology

- `signoz`
  - Purpose: Web UI and API
  - Entrypoint: image entrypoint `./signoz server`
  - Internal port: `8080`
  - Healthcheck: `wget --spider -q localhost:8080/api/v1/health`
  - Depends on: ClickHouse
- `otel-collector`
  - Purpose: OTLP ingest and telemetry pipeline
  - Entrypoint: `/bin/sh -c '/signoz-otel-collector migrate sync check && /signoz-otel-collector ...'`
  - Internal ports: `4317` (gRPC), `4318` (HTTP), `13133` (health), `1777` (pprof)
  - Depends on: ClickHouse, SigNoz OpAMP manager at `signoz:4320`
- `signoz-telemetrystore-migrator`
  - Purpose: bootstrap / sync / async ClickHouse migrations
  - Entrypoint: `/bin/sh -c '/signoz-otel-collector migrate bootstrap && ...'`
  - Depends on: ClickHouse
- `clickhouse`
  - Purpose: telemetry datastore
  - Internal ports: `8123`, `9000`, `9004`, `9005`, `9009`
  - Healthcheck: `wget --spider -q 0.0.0.0:8123/ping`
  - Depends on: `init-clickhouse`, `zookeeper-1`
- `init-clickhouse`
  - Purpose: download histogram executable into ClickHouse user scripts
  - Output path: `/var/lib/clickhouse/user_scripts/histogramQuantile`
- `zookeeper-1`
  - Purpose: ClickHouse cluster metadata
  - Internal ports: `2181`, `8080`, `9141`
  - Healthcheck: `curl -s -m 2 http://localhost:8080/commands/ruok | grep error | grep null`

## Environment Variables Confirmed Upstream

- SigNoz:
  - `SIGNOZ_ALERTMANAGER_PROVIDER=signoz`
  - `SIGNOZ_TELEMETRYSTORE_CLICKHOUSE_DSN=tcp://clickhouse:9000`
  - `SIGNOZ_SQLSTORE_SQLITE_PATH=/var/lib/signoz/signoz.db`
  - `SIGNOZ_TOKENIZER_JWT_SECRET=secret`
- Collector and migrator:
  - `SIGNOZ_OTEL_COLLECTOR_CLICKHOUSE_DSN=tcp://clickhouse:9000`
  - `SIGNOZ_OTEL_COLLECTOR_CLICKHOUSE_CLUSTER=cluster`
  - `SIGNOZ_OTEL_COLLECTOR_CLICKHOUSE_REPLICATION=true`
  - `SIGNOZ_OTEL_COLLECTOR_TIMEOUT=10m`
  - `OTEL_RESOURCE_ATTRIBUTES=host.name=signoz-host,os.type=linux`
  - `LOW_CARDINAL_EXCEPTION_GROUPING=false`
- ClickHouse:
  - `CLICKHOUSE_SKIP_USER_SETUP=1`
- ZooKeeper:
  - `ZOO_SERVER_ID=1`
  - `ALLOW_ANONYMOUS_LOGIN=yes`
  - `ZOO_AUTOPURGE_INTERVAL=1`
  - `ZOO_ENABLE_PROMETHEUS_METRICS=yes`
  - `ZOO_PROMETHEUS_METRICS_PORT_NUMBER=9141`

## Real Read/Write Paths

- `signoz`
  - `/var/lib/signoz`
  - writer: SigNoz server process
  - purpose: SQLite metadata database
- `otel-collector`
  - reads `/etc/otel-collector-config.yaml`
  - reads `/etc/manager-config.yaml`
  - no persistent write path confirmed from upstream compose
- `signoz-telemetrystore-migrator`
  - no dedicated persistent path confirmed
- `clickhouse`
  - `/var/lib/clickhouse`
  - `/var/lib/clickhouse/user_scripts`
  - `/var/log/clickhouse-server`
  - reads `/etc/clickhouse-server/users.xml`
  - reads `/etc/clickhouse-server/cluster.xml`
  - reads `/etc/clickhouse-server/custom-function.xml`
- `zookeeper-1`
  - `/bitnami/zookeeper`

## Config Files Required

- `deploy/docker/otel-collector-config.yaml`
- `deploy/common/signoz/otel-collector-opamp-config.yaml`
- `deploy/common/clickhouse/users.xml`
- `deploy/common/clickhouse/cluster.xml`
- `deploy/common/clickhouse/custom-function.xml`

## Initialization Order

1. `init-clickhouse` downloads `histogramQuantile` into shared ClickHouse scripts path.
2. `zookeeper-1` becomes reachable.
3. `clickhouse` starts with cluster and custom-function config.
4. `signoz-telemetrystore-migrator` runs bootstrap + schema migrations.
5. `signoz` serves UI and API on `8080`.
6. `otel-collector` starts after ClickHouse and uses OpAMP manager config pointing to `ws://signoz:4320/v1/opamp`.

## LazyCat Mapping Decisions

- Preserve the full community Docker topology instead of collapsing to one container.
- Persist:
  - `/lzcapp/var/data/signoz/sqlite -> /var/lib/signoz`
  - `/lzcapp/var/db/signoz/clickhouse -> /var/lib/clickhouse`
  - `/lzcapp/var/db/signoz/zookeeper -> /bitnami/zookeeper`
- Package upstream config files under `content/` and copy them into service paths at startup.
- Expose:
  - Web UI via root route to `signoz:8080`
  - OTLP HTTP ingress via secondary domain prefix `ingest` to `otel-collector:4318`

## Risks And Gaps

- Standard LazyCat HTTP routing can expose OTLP HTTP, but not native OTLP gRPC `4317`; this migration documents OTLP HTTP as the supported external ingest path.
- Upstream compose uses health-based `depends_on`; LazyCat manifest only preserves service ordering, so first boot may be slower and more sensitive to startup race conditions.
- Upstream explicitly sets `user: root` for `zookeeper-1`; current migration keeps the official image and persistent path, but actual runtime UID/GID behavior must be validated during install acceptance.
