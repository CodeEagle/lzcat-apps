# piclaw

本目录由 `scripts/bootstrap_migration.py` 生成，用于把上游 `rcarmo/piclaw` 初始化为懒猫微服迁移项目。

## 上游项目
- Upstream Repo: rcarmo/piclaw
- Homepage: https://github.com/rcarmo/piclaw
- License: MIT
- Author: rcarmo
- Version Strategy: `github_release` -> 当前初稿版本 `2.0.1`

## 当前迁移骨架
- Build Strategy: `upstream_dockerfile`
- Primary Subdomain: `piclaw`
- Image Targets: `pibox`
- Service Port: `8080`

### Services
- `pibox` -> `registry.lazycat.cloud/placeholder/piclaw:pibox`

## AIPod

当前未启用 AIPod / AI 服务。

## 环境变量

| 变量名 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- |
| TERM | No | xterm-256color | From compose service pibox |
| PUID | No | 1000 | From compose service pibox |
| PGID | No | 1000 | From compose service pibox |
| PICLAW_WEB_PORT | No | 8080 | From compose service pibox |
| PICLAW_AUTOSTART | No | 1 | From compose service pibox |

## 数据目录

| 宿主路径 | 容器路径 | 说明 |
| --- | --- | --- |
| /lzcapp/var/data/piclaw/pibox/config | /config | From compose service pibox |
| /lzcapp/var/data/piclaw/pibox/workspace | /workspace | From compose service pibox |

## 首次启动/验收提醒

- 自动扫描到 compose 文件：docker-compose.yml
- 主服务推断为 `pibox`，入口端口 `8080`。
- 未扫描到 env 示例文件
- 扫描到 README：README.md, README.md, README.md

## 下一步

1. 补完 `UPSTREAM_DEPLOYMENT_CHECKLIST.md`，把真实入口、环境变量、写路径和初始化动作全部核实清楚。
2. 按真实部署拓扑修正 `lzc-manifest.yml`，不要直接沿用占位镜像、端口或命令。
3. 如果是源码构建，补齐 `Dockerfile` / `Dockerfile.template`、`content/`、`overlay_paths` 等资产。
4. 初稿补全后执行 `./scripts/local_build.sh piclaw --check-only`，再进入实际构建与验收。
