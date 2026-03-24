# Shadowbroker

本目录由 `scripts/bootstrap_migration.py` 生成，用于把上游 `BigBodyCobain/Shadowbroker` 初始化为懒猫微服迁移项目。

## 上游项目
- Upstream Repo: BigBodyCobain/Shadowbroker
- Homepage: https://github.com/BigBodyCobain/Shadowbroker
- License: AGPL-3.0
- Author: BigBodyCobain
- Version Strategy: `github_release` -> 当前初稿版本 `0.9.5`

## 当前迁移骨架
- Build Strategy: `upstream_dockerfile`
- Primary Subdomain: `shadowbroker`
- Image Targets: `frontend`
- Service Port: `3000`

### Services
- `backend` -> `registry.lazycat.cloud/placeholder/shadowbroker:backend`
- `frontend` -> `registry.lazycat.cloud/placeholder/shadowbroker:frontend`

## 环境变量

| 变量名 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- |
| AIS_API_KEY | Yes | - | From compose service backend |
| OPENSKY_CLIENT_ID | Yes | - | From compose service backend |
| OPENSKY_CLIENT_SECRET | Yes | - | From compose service backend |
| LTA_ACCOUNT_KEY | Yes | - | From compose service backend |
| CORS_ORIGINS | No | - | From compose service backend |
| BACKEND_URL | No | http://backend:8000 | From compose service frontend |

## 数据目录

| 宿主路径 | 容器路径 | 说明 |
| --- | --- | --- |
| /lzcapp/var/data/shadowbroker/backend/data | /app/data | From compose service backend |

## 首次启动/验收提醒

- 自动扫描到 compose 文件：docker-compose.yml
- 主服务推断为 `frontend`，入口端口 `3000`。
- 扫描到 env 示例文件：.env.example, .env.example
- 扫描到 README：README.md, README.md, README.md

## 下一步

1. 补完 `UPSTREAM_DEPLOYMENT_CHECKLIST.md`，把真实入口、环境变量、写路径和初始化动作全部核实清楚。
2. 按真实部署拓扑修正 `lzc-manifest.yml`，不要直接沿用占位镜像、端口或命令。
3. 如果是源码构建，补齐 `Dockerfile` / `Dockerfile.template`、`content/`、`overlay_paths` 等资产。
4. 初稿补全后执行 `./scripts/local_build.sh shadowbroker --check-only`，再进入实际构建与验收。
