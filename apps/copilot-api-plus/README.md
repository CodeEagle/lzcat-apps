# copilot-api-plus

本目录由 `scripts/bootstrap_migration.py` 生成，用于把上游 `CodeEagle/copilot-api-plus` 初始化为懒猫微服迁移项目。

## 上游项目
- Upstream Repo: CodeEagle/copilot-api-plus
- Homepage: https://github.com/CodeEagle/copilot-api-plus
- License: MIT
- Author: CodeEagle
- Version Strategy: `commit_sha` -> 当前初稿版本 `1.2.24`

## 当前迁移骨架
- Build Strategy: `upstream_dockerfile`
- Primary Subdomain: `copilot-api-plus`
- Image Targets: `copilot-api-plus`
- Service Port: `4141`

### Services
- `copilot-api-plus` -> `registry.lazycat.cloud/placeholder/copilot-api-plus:bootstrap`

## AIPod

当前未启用 AIPod / AI 服务。

## 环境变量

当前未预填环境变量，待补充。

## 数据目录

| 宿主路径 | 容器路径 | 说明 |
| --- | --- | --- |
| /lzcapp/var/data/copilot-api-plus | /root/.local/share/copilot-api-plus | From source code pattern in paths.ts |

## 首次启动/验收提醒

- 自动扫描到 Dockerfile：Dockerfile
- 当前路线按源码构建处理，后续需确认真实入口、初始化命令和写路径。
- 扫描到 env 示例文件：.env.example
- 扫描到 README：README.en.md, README.md

## 下一步

1. 补完 `UPSTREAM_DEPLOYMENT_CHECKLIST.md`，把真实入口、环境变量、写路径和初始化动作全部核实清楚。
2. 按真实部署拓扑修正 `lzc-manifest.yml`，不要直接沿用占位镜像、端口或命令。
3. 如果是源码构建，补齐 `Dockerfile` / `Dockerfile.template`、`content/`、`overlay_paths` 等资产。
4. 初稿补全后执行 `./scripts/local_build.sh copilot-api-plus --check-only`，再进入实际构建与验收。
