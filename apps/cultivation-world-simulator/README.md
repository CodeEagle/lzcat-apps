# cultivation-world-simulator

本目录由 `scripts/bootstrap_migration.py` 生成，用于把上游 `4thfever/cultivation-world-simulator` 初始化为懒猫微服迁移项目。

## 上游项目
- Upstream Repo: 4thfever/cultivation-world-simulator
- Homepage: https://github.com/4thfever/cultivation-world-simulator
- License: NOASSERTION
- Author: 4thfever
- Version Strategy: `github_release` -> 当前初稿版本 `2.4.0`

## 当前迁移骨架
- Build Strategy: `upstream_dockerfile`
- Primary Subdomain: `cultivation-world-simulator`
- Image Targets: `frontend`
- Service Port: `80`

### Services
- `backend` -> `registry.lazycat.cloud/placeholder/cultivation-world-simulator:backend`
- `frontend` -> `registry.lazycat.cloud/placeholder/cultivation-world-simulator:frontend`

## AIPod

当前未启用 AIPod / AI 服务。

## 环境变量

| 变量名 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- |
| PYTHONUNBUFFERED | No | 1 | From compose service backend |
| CWS_DATA_DIR | No | /data | From compose service backend |
| CWS_DISABLE_AUTO_SHUTDOWN | No | 1 | From compose service backend |

## 数据目录

| 宿主路径 | 容器路径 | 说明 |
| --- | --- | --- |
| /lzcapp/var/data/cultivation-world-simulator/backend | /data | From compose service backend |

## 首次启动/验收提醒

- 自动扫描到 compose 文件：docker-compose.yml
- 主服务推断为 `frontend`，入口端口 `80`。
- 未扫描到 env 示例文件
- 扫描到 README：README.md, README.md, README_MIGRATION.md

## 下一步

1. 补完 `UPSTREAM_DEPLOYMENT_CHECKLIST.md`，把真实入口、环境变量、写路径和初始化动作全部核实清楚。
2. 按真实部署拓扑修正 `lzc-manifest.yml`，不要直接沿用占位镜像、端口或命令。
3. 如果是源码构建，补齐 `Dockerfile` / `Dockerfile.template`、`content/`、`overlay_paths` 等资产。
4. 初稿补全后执行 `./scripts/local_build.sh cultivation-world-simulator --check-only`，再进入实际构建与验收。
