# LocalAI

本目录由 `scripts/bootstrap_migration.py` 生成，用于把上游 `mudler/LocalAI` 初始化为懒猫微服迁移项目。

## 上游项目
- Upstream Repo: mudler/LocalAI
- Homepage: https://localai.io
- License: MIT
- Author: mudler
- Version Strategy: `github_release` -> 当前初稿版本 `4.1.3`

## 当前迁移骨架
- Build Strategy: `upstream_dockerfile`
- Primary Subdomain: `localai`
- Image Targets: `api`
- Service Port: `8080`

### Services
- `api` -> `registry.lazycat.cloud/placeholder/localai:api`

## AIPod

当前未启用 AIPod / AI 服务。

## 环境变量

| 变量名 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- |
| MODELS_PATH | No | /models | From compose service api |

## 数据目录

| 宿主路径 | 容器路径 | 说明 |
| --- | --- | --- |
| /lzcapp/var/data/localai/api/models | /models | From compose service api |
| /lzcapp/var/data/localai/api/images | /tmp/generated/images/ | From compose service api |
| /lzcapp/var/data/localai/api | /data | From compose service api |
| /lzcapp/var/data/localai/api/backends | /backends | From compose service api |
| /lzcapp/var/data/localai/api/configuration | /configuration | From compose service api |

## 首次启动/验收提醒

- 自动扫描到 compose 文件：docker-compose.yaml
- 主服务推断为 `api`，入口端口 `8080`。
- 扫描到 env 示例文件：.env
- 扫描到 README：README.md, README.md, README.md

## 下一步

1. 补完 `UPSTREAM_DEPLOYMENT_CHECKLIST.md`，把真实入口、环境变量、写路径和初始化动作全部核实清楚。
2. 按真实部署拓扑修正 `lzc-manifest.yml`，不要直接沿用占位镜像、端口或命令。
3. 如果是源码构建，补齐 `Dockerfile` / `Dockerfile.template`、`content/`、`overlay_paths` 等资产。
4. 初稿补全后执行 `./scripts/local_build.sh localai --check-only`，再进入实际构建与验收。
