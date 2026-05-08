# Resumeai

本目录由 `scripts/bootstrap_migration.py` 生成，用于把上游 `Doomish77/ResumeAI` 初始化为懒猫微服迁移项目。

## 上游项目
- Upstream Repo: Doomish77/ResumeAI
- Homepage: https://github.com/Doomish77/ResumeAI
- License: MIT
- Author: Doomish77
- Version Strategy: `commit_sha` -> 当前初稿版本 `0.1.0`

## 当前迁移骨架
- Build Strategy: `upstream_with_target_template`
- Primary Subdomain: `resumeai`
- Image Targets: `web`
- Service Port: `8080`

### Services
- `mongo` -> `mongo:7`
- `web` -> `registry.lazycat.cloud/placeholder/resumeai:bootstrap`

## AIPod

当前未启用 AIPod / AI 服务。

## 环境变量

当前未预填环境变量，待补充。

## 数据目录

当前未声明持久化目录，待从上游部署清单补充。

## 首次启动/验收提醒

- analyze_source raised (未发现 compose、Dockerfile、可识别的前端应用或 release binary); apps/resumeai/Dockerfile.template already written by planner — using upstream_with_target_template route.
- image_targets derived from planner manifest: ['web'].
- sidecar dependencies derived from planner manifest: ['mongo']

## 下一步

1. 补完 `UPSTREAM_DEPLOYMENT_CHECKLIST.md`，把真实入口、环境变量、写路径和初始化动作全部核实清楚。
2. 按真实部署拓扑修正 `lzc-manifest.yml`，不要直接沿用占位镜像、端口或命令。
3. 如果是源码构建，补齐 `Dockerfile` / `Dockerfile.template`、`content/`、`overlay_paths` 等资产。
4. 初稿补全后执行 `./scripts/local_build.sh resumeai --check-only`，再进入实际构建与验收。
