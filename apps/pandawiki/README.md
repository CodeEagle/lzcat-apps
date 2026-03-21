# PandaWiki

PandaWiki 是长亭开源的 AI 知识库系统，包含管理后台、Wiki 前台、API、consumer、Caddy、PostgreSQL、Redis、MinIO、NATS、Qdrant、Anydoc crawler 和 Raglite。

## 上游项目

- 项目地址: https://github.com/chaitin/PandaWiki
- 官方文档: https://pandawiki.docs.baizhi.cloud/
- 官方安装脚本: https://release.baizhi.cloud/panda-wiki/manager.sh
- 官方 compose: https://release.baizhi.cloud/panda-wiki/docker-compose.yml

## 当前移植路线

- `panda-wiki-api` 和 `panda-wiki-consumer` 使用当前目录下的 `Dockerfile` 从上游源码构建，并把源码里写死的 `169.254.15.*` 服务发现改成 LazyCat 服务名。
- `panda-wiki-nginx`、`panda-wiki-app`、`panda-wiki-caddy`、`postgres`、`redis`、`minio`、`nats`、`qdrant`、`crawler`、`raglite` 继续复用官方镜像。
- 默认对外入口先对齐官方管理后台，路由到 `panda-wiki-nginx:8080`。

## 关键环境变量

| 变量名 | 说明 |
| --- | --- |
| `POSTGRES_PASSWORD` | PostgreSQL 密码 |
| `NATS_PASSWORD` | NATS 密码 |
| `JWT_SECRET` | JWT 密钥 |
| `S3_SECRET_KEY` | MinIO 密钥 |
| `QDRANT_API_KEY` | Qdrant API Key |
| `REDIS_PASSWORD` | Redis 密码 |
| `ADMIN_PASSWORD` | 管理后台初始密码 |

## 数据目录

| 路径 | 说明 |
| --- | --- |
| `/lzcapp/var/data/pandawiki/caddy/config` | Caddy 配置 |
| `/lzcapp/var/data/pandawiki/caddy/data` | Caddy 数据 |
| `/lzcapp/var/data/pandawiki/caddy/run` | Caddy admin socket |
| `/lzcapp/var/data/pandawiki/nginx/ssl` | nginx / API 共享证书目录 |
| `/lzcapp/var/data/pandawiki/conf/api` | API 配置与运行数据 |
| `/lzcapp/var/db/pandawiki/postgres` | PostgreSQL 数据 |
| `/lzcapp/var/data/pandawiki/redis` | Redis 数据 |
| `/lzcapp/var/data/pandawiki/minio` | MinIO 数据 |
| `/lzcapp/var/data/pandawiki/nats` | NATS 数据 |
| `/lzcapp/var/data/pandawiki/qdrant` | Qdrant 数据 |
| `/lzcapp/var/data/pandawiki/raglite` | Raglite 数据 |

## 已确认的上游部署信息

- 官方最新 release: `v3.81.0`
- 官方管理后台端口: `2443`
- API 容器端口: `8000`
- Wiki 前台容器端口: `3010`
- Raglite 容器端口: `5050`
- 官方环境模板包含 `POSTGRES_PASSWORD`、`NATS_PASSWORD`、`JWT_SECRET`、`S3_SECRET_KEY`、`QDRANT_API_KEY`、`REDIS_PASSWORD`、`ADMIN_PASSWORD`

## 当前风险

- 该 manifest 目前优先保证官方管理后台链路可迁移，公开 Wiki 站点的 LazyCat 外网入口还没有完成安装验收。
- `panda-wiki-caddy` 在官方 compose 中使用 `host` 网络监听多 host/port，LazyCat 下需要在安装验收阶段继续确认公开 Wiki 的访问方式。
