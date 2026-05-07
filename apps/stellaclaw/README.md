# StellaClaw

本目录由 `scripts/bootstrap_migration.py` 生成，用于把上游 `JeremyGuo/StellaClaw` 初始化为懒猫微服迁移项目。

## 上游项目
- Upstream Repo: JeremyGuo/StellaClaw
- Homepage: https://github.com/JeremyGuo/StellaClaw
- License: 
- Author: JeremyGuo
- Version Strategy: `github_release` -> 当前初稿版本 `1.25.0`

## 当前迁移骨架
- Build Strategy: `upstream_with_target_template`
- Primary Subdomain: `stellaclaw`
- Image Targets: `stellaclaw-web`
- Service Port: `80`

### Services
- `stellaclaw-web` -> `registry.lazycat.cloud/placeholder/stellaclaw:bootstrap`

## AIPod

当前未启用 AIPod / AI 服务。

## 环境变量

当前未预填环境变量，待补充。

## 数据目录

当前未声明持久化目录，待从上游部署清单补充。

## 首次启动/验收提醒

- 检测到前端应用目录 `apps/stellacodeX/electron` 使用静态站构建，可按 nginx 托管产物封装。
- 构建目录：`apps/stellacodeX/electron`；安装根目录：`apps/stellacodeX/electron`。
- 自动推断构建命令：`npm run build`。
- 运行时按静态站处理，由 nginx 托管构建产物目录。
- 未扫描到 env 示例文件
- 扫描到 README：README.md, README_zh.md, README.md
- 扫描到上游图标：apps/stellacodeX/ios/StellaCodeX/StellaCodeX/Assets.xcassets/AppIcon.appiconset/Icon-App-256x256@1x.png

## 下一步

1. 补完 `UPSTREAM_DEPLOYMENT_CHECKLIST.md`，把真实入口、环境变量、写路径和初始化动作全部核实清楚。
2. 按真实部署拓扑修正 `lzc-manifest.yml`，不要直接沿用占位镜像、端口或命令。
3. 如果是源码构建，补齐 `Dockerfile` / `Dockerfile.template`、`content/`、`overlay_paths` 等资产。
4. 初稿补全后执行 `./scripts/local_build.sh stellaclaw --check-only`，再进入实际构建与验收。
