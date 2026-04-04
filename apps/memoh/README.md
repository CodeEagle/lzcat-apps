# Memoh

本目录由 `scripts/bootstrap_migration.py` 生成，用于把上游 `memohai/Memoh` 初始化为懒猫微服迁移项目。

## 上游项目
- Upstream Repo: memohai/Memoh
- Homepage: https://docs.memoh.ai
- License: AGPL-3.0
- Author: memohai
- Version Strategy: `github_release` -> 当前初稿版本 `0.6.3`

## 当前迁移骨架
- Build Strategy: `official_image`
- Primary Subdomain: `memoh`
- Image Targets: `web`
- Service Port: `8082`
- Default topology retained from upstream: `postgres + migrate + server + web + qdrant + browser`

### Services
- `postgres` -> `registry.lazycat.cloud/placeholder/memoh:postgres`
- `migrate` -> `registry.lazycat.cloud/placeholder/memoh:migrate`
- `server` -> `registry.lazycat.cloud/placeholder/memoh:server`
- `web` -> `registry.lazycat.cloud/placeholder/memoh:web`
- `qdrant` -> `registry.lazycat.cloud/placeholder/memoh:qdrant`
- `browser` -> `registry.lazycat.cloud/placeholder/memoh:browser`

## AIPod

当前未启用 AIPod / AI 服务。

## 环境变量

| 变量名 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- |
| POSTGRES_DB | No | memoh | From compose service postgres |
| POSTGRES_USER | No | memoh | From compose service postgres |
| POSTGRES_PASSWORD | No | memoh123 | From compose service postgres |
| BROWSER_CORES | No | chromium,firefox | From compose service browser |

## 数据目录

| 宿主路径 | 容器路径 | 说明 |
| --- | --- | --- |
| /lzcapp/var/db/memoh/postgres | /var/lib/postgresql | From compose service postgres |
| /lzcapp/var/data/memoh/config | generated config.toml | Shared generated runtime config |
| /lzcapp/var/data/memoh/server/containerd | /var/lib/containerd | From compose service server |
| /lzcapp/var/data/memoh/server/cni | /var/lib/cni | From compose service server |
| /lzcapp/var/data/memoh/server/data | /opt/memoh/data | From compose service server |
| /lzcapp/var/data/memoh/qdrant/storage | /qdrant/storage | From compose service qdrant |

## 首次启动/验收提醒

- 自动扫描到 compose 文件：docker-compose.yml
- 主服务推断为 `web`，入口端口 `8082`。
- 官方部署文档要求先生成 `config.toml`；当前懒猫稿会在首启时自动生成并持久化到 `/lzcapp/var/data/memoh/config/config.toml`。
- 默认保留官方推荐的 `qdrant + browser` 组合，未默认启用 `sparse` profile。
- 默认登录信息将生成为 `admin / ${LAZYCAT_APP_ID}-admin`。
- `server` 依赖 nested `containerd`、CNI、iptables 和 cgroup；是否能在 LazyCat 中稳定运行仍需实际安装验收确认。

## 下一步

1. 触发正式构建，把 `placeholder` 镜像替换成真实 `registry.lazycat.cloud/...` 地址。
2. 用 release 包实际验收 `migrate -> server -> web` 链路，重点确认 nested `containerd` 和 CNI 是否可用。
3. 如果 `server` 因权限或内核能力受限无法启动，再评估 `Memoh` 是否适合作为 LazyCat 目标，或是否需要更深的运行时适配。
