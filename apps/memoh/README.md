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

### Services
- `postgres` -> `registry.lazycat.cloud/placeholder/memoh:postgres`
- `migrate` -> `registry.lazycat.cloud/placeholder/memoh:migrate`
- `server` -> `registry.lazycat.cloud/placeholder/memoh:server`
- `web` -> `registry.lazycat.cloud/placeholder/memoh:web`
- `sparse` -> `registry.lazycat.cloud/placeholder/memoh:sparse`
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
| /lzcapp/var/data/memoh/server/containerd | /var/lib/containerd | From compose service server |
| /lzcapp/var/data/memoh/server/cni | /var/lib/cni | From compose service server |
| /lzcapp/var/data/memoh/server/data | /opt/memoh/data | From compose service server |
| /lzcapp/var/data/memoh/qdrant/storage | /qdrant/storage | From compose service qdrant |

## 首次启动/验收提醒

- 自动扫描到 compose 文件：docker-compose.yml
- 主服务推断为 `web`，入口端口 `8082`。
- 依赖服务镜像已写入 dependencies，首次完整构建时会自动 copy-image。
- 未扫描到 env 示例文件
- 扫描到 README：README.md, README_CN.md, README.md

## 下一步

1. 补完 `UPSTREAM_DEPLOYMENT_CHECKLIST.md`，把真实入口、环境变量、写路径和初始化动作全部核实清楚。
2. 按真实部署拓扑修正 `lzc-manifest.yml`，不要直接沿用占位镜像、端口或命令。
3. 如果是源码构建，补齐 `Dockerfile` / `Dockerfile.template`、`content/`、`overlay_paths` 等资产。
4. 初稿补全后执行 `./scripts/local_build.sh memoh --check-only`，再进入实际构建与验收。
