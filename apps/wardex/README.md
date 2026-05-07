# Wardex

本目录由 `scripts/bootstrap_migration.py` 生成，用于把上游 `pinkysworld/Wardex` 初始化为懒猫微服迁移项目。

## 上游项目
- Upstream Repo: pinkysworld/Wardex
- Homepage: https://minh.systems/Wardex/site
- License: 
- Author: pinkysworld
- Version Strategy: `github_release` -> 当前初稿版本 `1.0.5`

## 当前迁移骨架
- Build Strategy: `upstream_dockerfile`
- Primary Subdomain: `wardex`
- Image Targets: `wardex`
- Service Port: `9077`

### Services
- `wardex` -> `registry.lazycat.cloud/placeholder/wardex:wardex`

## AIPod

当前未启用 AIPod / AI 服务。

## 环境变量

| 变量名 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- |
| SENTINEL_CORS_ORIGIN | No | http://localhost:8080 | From compose service wardex |
| WARDEX_PORT | No | 8080 | From .env.example |
| WARDEX_HOST | No | 127.0.0.1 | From .env.example |
| WARDEX_TOKEN | No | change-me-to-a-random-secret | From .env.example |
| WARDEX_AGENT_TOKEN | No | change-me-to-another-secret | From .env.example |
| RUST_LOG | No | info | From .env.example |

## 数据目录

| 宿主路径 | 容器路径 | 说明 |
| --- | --- | --- |
| /lzcapp/var/data/wardex | /app/var | From compose service wardex |

## 首次启动/验收提醒

- 自动扫描到 compose 文件：docker-compose.yml
- 主服务推断为 `wardex`，入口端口 `9077`。
- 扫描到 env 示例文件：.env.example
- 扫描到 README：README.md, README.md, README.md

## 下一步

1. 补完 `UPSTREAM_DEPLOYMENT_CHECKLIST.md`，把真实入口、环境变量、写路径和初始化动作全部核实清楚。
2. 按真实部署拓扑修正 `lzc-manifest.yml`，不要直接沿用占位镜像、端口或命令。
3. 如果是源码构建，补齐 `Dockerfile` / `Dockerfile.template`、`content/`、`overlay_paths` 等资产。
4. 初稿补全后执行 `./scripts/local_build.sh wardex --check-only`，再进入实际构建与验收。
