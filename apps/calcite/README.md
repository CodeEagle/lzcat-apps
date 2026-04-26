# calcite

本目录由 `scripts/bootstrap_migration.py` 生成，用于把上游 `apache/calcite` 初始化为懒猫微服迁移项目。

## 上游项目
- Upstream Repo: apache/calcite
- Homepage: https://calcite.apache.org/
- License: Apache-2.0
- Author: apache
- Version Strategy: `github_release` -> 当前初稿版本 `1.23.0`

## 当前迁移骨架
- Build Strategy: `official_image`
- Primary Subdomain: `calcite`
- Image Targets: `build-site, dev`
- Service Port: `4000`

### Services
- `build-site` -> `registry.lazycat.cloud/placeholder/calcite:build-site`
- `dev` -> `registry.lazycat.cloud/placeholder/calcite:dev`
- `generate-javadoc` -> `registry.lazycat.cloud/placeholder/calcite:generate-javadoc`

## AIPod

当前未启用 AIPod / AI 服务。

## 环境变量

当前未预填环境变量，待补充。

## 数据目录

| 宿主路径 | 容器路径 | 说明 |
| --- | --- | --- |
| /lzcapp/var/data/calcite/dev/root | /root | From compose service dev |
| /lzcapp/var/data/calcite/build-site/jekyll | /home/jekyll | From compose service build-site |
| /lzcapp/var/data/calcite/generate-javadoc/calcite | /usr/src/calcite | From compose service generate-javadoc |
| /lzcapp/var/data/calcite/generate-javadoc/m2 | /root/.m2 | From compose service generate-javadoc |

## 首次启动/验收提醒

- 自动扫描到 compose 文件：site/docker-compose.yml
- 主服务推断为 `dev`，入口端口 `4000`。
- 依赖服务镜像已写入 dependencies，首次完整构建时会自动 copy-image。
- 未扫描到 env 示例文件
- 扫描到 README：README, README.md, README.md
- 扫描到上游图标：.idea/icon.png

## 下一步

1. 补完 `UPSTREAM_DEPLOYMENT_CHECKLIST.md`，把真实入口、环境变量、写路径和初始化动作全部核实清楚。
2. 按真实部署拓扑修正 `lzc-manifest.yml`，不要直接沿用占位镜像、端口或命令。
3. 如果是源码构建，补齐 `Dockerfile` / `Dockerfile.template`、`content/`、`overlay_paths` 等资产。
4. 初稿补全后执行 `./scripts/local_build.sh calcite --check-only`，再进入实际构建与验收。
