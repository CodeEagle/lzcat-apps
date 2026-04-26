# dvc

本目录由 `scripts/bootstrap_migration.py` 生成，用于把上游 `treeverse/dvc` 初始化为懒猫微服迁移项目。

## 上游项目
- Upstream Repo: treeverse/dvc
- Homepage: https://dvc.org
- License: Apache-2.0
- Author: treeverse
- Version Strategy: `github_release` -> 当前初稿版本 `3.67.1`

## 当前迁移骨架
- Build Strategy: `official_image`
- Primary Subdomain: `dvc`
- Image Targets: `git-server`
- Service Port: `2222`

### Services
- `git-server` -> `registry.lazycat.cloud/placeholder/dvc:git-server`

## AIPod

当前未启用 AIPod / AI 服务。

## 环境变量

| 变量名 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- |
| USER_NAME | No | user | From compose service git-server |
| PUBLIC_KEY_FILE | No | /tmp/key | From compose service git-server |

## 数据目录

| 宿主路径 | 容器路径 | 说明 |
| --- | --- | --- |
| /lzcapp/var/data/dvc/git-server/key | /tmp/key | From compose service git-server |
| /lzcapp/var/data/dvc/git-server/custom-cont-init-d | /custom-cont-init.d | From compose service git-server |

## 首次启动/验收提醒

- 自动扫描到 compose 文件：tests/docker-compose.yml
- 主服务推断为 `git-server`，入口端口 `2222`。
- 未扫描到 env 示例文件
- 扫描到 README：README.rst, README.rst

## 下一步

1. 补完 `UPSTREAM_DEPLOYMENT_CHECKLIST.md`，把真实入口、环境变量、写路径和初始化动作全部核实清楚。
2. 按真实部署拓扑修正 `lzc-manifest.yml`，不要直接沿用占位镜像、端口或命令。
3. 如果是源码构建，补齐 `Dockerfile` / `Dockerfile.template`、`content/`、`overlay_paths` 等资产。
4. 初稿补全后执行 `./scripts/local_build.sh dvc --check-only`，再进入实际构建与验收。
