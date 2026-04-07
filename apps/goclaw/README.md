# goclaw

本目录由 `scripts/bootstrap_migration.py` 生成，用于把上游 `nextlevelbuilder/goclaw` 初始化为懒猫微服迁移项目。

## 上游项目
- Upstream Repo: nextlevelbuilder/goclaw
- Homepage: https://goclaw.sh
- License: NOASSERTION
- Author: nextlevelbuilder
- Version Strategy: `github_release` -> 当前初稿版本 `2.67.4`

## 当前迁移骨架
- Build Strategy: `upstream_dockerfile`
- Primary Subdomain: `goclaw`
- Image Targets: `goclaw`
- Service Port: `18790`

### Services
- `goclaw` -> `registry.lazycat.cloud/placeholder/goclaw:goclaw`

## AIPod

当前未启用 AIPod / AI 服务。

## 环境变量

| 变量名 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- |
| GOCLAW_HOST | No | 0.0.0.0 | From compose service goclaw |
| GOCLAW_PORT | No | 18790 | From compose service goclaw |
| GOCLAW_CONFIG | No | /app/data/config.json | From compose service goclaw |
| GOCLAW_GATEWAY_TOKEN | No | - | From compose service goclaw |
| GOCLAW_ENCRYPTION_KEY | No | - | From compose service goclaw |
| GOCLAW_SKILLS_DIR | No | /app/data/skills | From compose service goclaw |
| GOCLAW_TRACE_VERBOSE | No | 0 | From compose service goclaw |
| POSTGRES_PASSWORD | No | - | From .env.example |
| VITE_BACKEND_PORT | No | 18790 | From .env.example |
| VITE_BACKEND_HOST | No | localhost | From .env.example |
| VITE_WS_URL | No | ws://localhost:18790/ws | From .env.example |

## 数据目录

| 宿主路径 | 容器路径 | 说明 |
| --- | --- | --- |
| /lzcapp/var/data/goclaw/goclaw/data | /app/data | From compose service goclaw |
| /lzcapp/var/data/goclaw/goclaw/workspace | /app/workspace | From compose service goclaw |

## 首次启动/验收提醒

- 自动扫描到 compose 文件：docker-compose.yml
- 主服务推断为 `goclaw`，入口端口 `18790`。
- 扫描到 env 示例文件：.env.example, .env.example
- 扫描到 README：README.md, README.ar.md, README.bn.md

## 下一步

1. 补完 `UPSTREAM_DEPLOYMENT_CHECKLIST.md`，把真实入口、环境变量、写路径和初始化动作全部核实清楚。
2. 按真实部署拓扑修正 `lzc-manifest.yml`，不要直接沿用占位镜像、端口或命令。
3. 如果是源码构建，补齐 `Dockerfile` / `Dockerfile.template`、`content/`、`overlay_paths` 等资产。
4. 初稿补全后执行 `./scripts/local_build.sh goclaw --check-only`，再进入实际构建与验收。
