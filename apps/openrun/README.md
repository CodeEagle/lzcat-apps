# openrun

本目录由 `scripts/bootstrap_migration.py` 生成，用于把上游 `openrundev/openrun` 初始化为懒猫微服迁移项目。

## 上游项目
- Upstream Repo: openrundev/openrun
- Homepage: https://openrun.dev
- License: Apache-2.0
- Author: openrundev
- Version Strategy: `github_release` -> 当前初稿版本 `0.17.0`

## 当前迁移骨架
- Build Strategy: `upstream_with_target_template`
- Primary Subdomain: `openrun`
- Image Targets: `openrun`
- Service Port: `25222`

### Services
- `openrun` -> `registry.lazycat.cloud/placeholder/openrun:bootstrap`

## AIPod

当前未启用 AIPod / AI 服务。

## 环境变量

当前未预填环境变量，待补充。

## 数据目录

当前未声明持久化目录，待从上游部署清单补充。

## 首次启动/验收提醒

- 自动扫描到 Dockerfile：Dockerfile
- 当前路线按源码构建处理，后续需确认真实入口、初始化命令和写路径。
- 未扫描到 env 示例文件
- 扫描到 README：README.md, README.md, README.md
- 扫描到上游图标：docs/static/apple-touch-icon.png

## 下一步

1. 补完 `UPSTREAM_DEPLOYMENT_CHECKLIST.md`，把真实入口、环境变量、写路径和初始化动作全部核实清楚。
2. 按真实部署拓扑修正 `lzc-manifest.yml`，不要直接沿用占位镜像、端口或命令。
3. 如果是源码构建，补齐 `Dockerfile` / `Dockerfile.template`、`content/`、`overlay_paths` 等资产。
4. 初稿补全后执行 `./scripts/local_build.sh openrun --check-only`，再进入实际构建与验收。
