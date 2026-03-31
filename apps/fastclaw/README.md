# fastclaw

本目录由 `scripts/bootstrap_migration.py` 生成，用于把上游 `fastclaw-ai/fastclaw` 初始化为懒猫微服迁移项目。

## 上游项目
- Upstream Repo: fastclaw-ai/fastclaw
- Homepage: https://github.com/fastclaw-ai/fastclaw
- License: MIT
- Author: fastclaw-ai
- Version Strategy: `github_release` -> 当前初稿版本 `0.20.0`

## 当前迁移骨架
- Build Strategy: `precompiled_binary`
- Primary Subdomain: `fastclaw`
- Image Targets: `fastclaw`
- Service Port: `8080`

### Services
- `fastclaw` -> `registry.lazycat.cloud/placeholder/fastclaw:bootstrap`

## 环境变量

当前未预填环境变量，待补充。

## 数据目录

当前未声明持久化目录，待从上游部署清单补充。

## 首次启动/验收提醒

- 自动推断为 release binary 路线。
- 当前只按通用单二进制服务处理，真实监听端口和启动参数仍需验收确认。
- 未扫描到 env 示例文件
- 扫描到 README：README.md, README.md, README.md

## 下一步

1. 补完 `UPSTREAM_DEPLOYMENT_CHECKLIST.md`，把真实入口、环境变量、写路径和初始化动作全部核实清楚。
2. 按真实部署拓扑修正 `lzc-manifest.yml`，不要直接沿用占位镜像、端口或命令。
3. 如果是源码构建，补齐 `Dockerfile` / `Dockerfile.template`、`content/`、`overlay_paths` 等资产。
4. 初稿补全后执行 `./scripts/local_build.sh fastclaw --check-only`，再进入实际构建与验收。
