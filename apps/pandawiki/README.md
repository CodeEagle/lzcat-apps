# PandaWiki

PandaWiki 是长亭开源的 AI 知识库系统，包含管理后台、Wiki 前台、API、consumer、Caddy、PostgreSQL、Redis、MinIO、NATS、Qdrant、Anydoc crawler 和 Raglite。

## 上游项目

- 项目地址: https://github.com/chaitin/PandaWiki
- 官方文档: https://pandawiki.docs.baizhi.cloud/
- 官方安装脚本: https://release.baizhi.cloud/panda-wiki/manager.sh
- 官方 compose: https://release.baizhi.cloud/panda-wiki/docker-compose.yml

## 当前移植路线

- 当前 LazyCat 版本压缩为 5 个服务：`panda-wiki-nginx`、`panda-wiki-api`、`postgres`、`redis`、`minio`。
- `panda-wiki-api` 使用当前目录下的 `Dockerfile` 从上游源码构建，并把源码里写死的 `169.254.15.*` 服务发现改成 LazyCat 服务名。
- `panda-wiki-api` 同时禁用了 MQ、RAG 和 Caddy 依赖，避免强依赖 `nats`、`qdrant`、`raglite`、`crawler` 等额外容器。
- 对外根入口走 `panda-wiki-nginx:8080`，但使用 `content/server.conf` 覆盖官方 HTTPS-only 配置，改为 LazyCat 兼容的 HTTP 管理后台入口。

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
| `/lzcapp/var/data/pandawiki/conf/api-v2` | API 配置与运行数据 |
| `/lzcapp/var/db/pandawiki/postgres-v2` | PostgreSQL 数据 |
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

- 当前版本已经完成管理后台安装验收。
- 公开 Wiki 发布页仍未在 LazyCat 外网入口下单独验收，后续如果需要开放知识库前台，还要继续补路由和场景验证。
