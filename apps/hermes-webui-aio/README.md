# hermes-webui

本目录由 `scripts/bootstrap_migration.py` 生成，用于把上游 `nesquena/hermes-webui` 初始化为懒猫微服迁移项目。

## 上游项目
- Upstream Repo: nesquena/hermes-webui
- Homepage: https://github.com/nesquena/hermes-webui
- License: MIT
- Author: nesquena
- Version Strategy: `github_release` -> 当前初稿版本 `0.38.6`

## 当前迁移骨架
- Build Strategy: `upstream_dockerfile`
- Primary Subdomain: `hermes-webui`
- Image Targets: `hermes-webui`
- Service Port: `8787`

### Services
- `hermes-webui` -> `registry.lazycat.cloud/placeholder/hermes-webui:hermes-webui`

## AIPod

当前未启用 AIPod / AI 服务。

## 环境变量

| 变量名 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- |
| HERMES_WEBUI_HOST | No | 0.0.0.0 | From compose service hermes-webui |
| HERMES_WEBUI_PORT | No | 8787 | From compose service hermes-webui |
| HERMES_WEBUI_STATE_DIR | No | /data | From compose service hermes-webui |

## 数据目录

| 宿主路径 | 容器路径 | 说明 |
| --- | --- | --- |
| /lzcapp/var/data/hermes-webui/hermes-webui | /data | From compose service hermes-webui |

## 首次启动/验收提醒

- 自动扫描到 compose 文件：docker-compose.yml
- 主服务推断为 `hermes-webui`，入口端口 `8787`。
- 扫描到 env 示例文件：.env.example
- 扫描到 README：README.md

## 下一步

1. 补完 `UPSTREAM_DEPLOYMENT_CHECKLIST.md`，把真实入口、环境变量、写路径和初始化动作全部核实清楚。
2. 按真实部署拓扑修正 `lzc-manifest.yml`，不要直接沿用占位镜像、端口或命令。
3. 如果是源码构建，补齐 `Dockerfile` / `Dockerfile.template`、`content/`、`overlay_paths` 等资产。
4. 初稿补全后执行 `./scripts/local_build.sh hermes-webui --check-only`，再进入实际构建与验收。
