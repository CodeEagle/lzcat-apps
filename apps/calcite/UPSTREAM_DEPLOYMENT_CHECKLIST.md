# calcite Upstream Deployment Checklist

## 已确认字段
- PROJECT_NAME: calcite
- PROJECT_SLUG: calcite
- UPSTREAM_REPO: apache/calcite
- UPSTREAM_URL: https://github.com/apache/calcite
- HOMEPAGE: https://calcite.apache.org/
- LICENSE: Apache-2.0
- AUTHOR: apache
- VERSION: 1.23.0
- IMAGE: ruby
- PORT: 4000
- AI_POD_SERVICE: 无
- AI_POD_SERVICE_NAME: 无
- AI_POD_SERVICE_PORT: 无
- CHECK_STRATEGY: github_release
- BUILD_STRATEGY: official_image

## 预填环境变量
- 待补充

## 预填数据路径
- `/root` <= `/lzcapp/var/data/calcite/dev/root` (From compose service dev)
- `/home/jekyll` <= `/lzcapp/var/data/calcite/build-site/jekyll` (From compose service build-site)
- `/usr/src/calcite` <= `/lzcapp/var/data/calcite/generate-javadoc/calcite` (From compose service generate-javadoc)
- `/root/.m2` <= `/lzcapp/var/data/calcite/generate-javadoc/m2` (From compose service generate-javadoc)

## 预填启动说明
- 自动扫描到 compose 文件：site/docker-compose.yml
- 主服务推断为 `dev`，入口端口 `4000`。
- 依赖服务镜像已写入 dependencies，首次完整构建时会自动 copy-image。
- 未扫描到 env 示例文件
- 扫描到 README：README, README.md, README.md
- 扫描到上游图标：.idea/icon.png

## 必扫清单
- [ ] Dockerfile / Containerfile / compose / helm / entrypoint / startup script 的真实启动入口
- [ ] README / 部署文档 / `.env.example` / sample config 中声明的环境变量
- [ ] 数据目录、配置目录、缓存目录、上传目录、日志目录、临时目录的真实读写路径
- [ ] 若启用 AIPod，确认 `ai-pod-service/docker-compose.yml` 中的真实镜像、服务端口、`-ai` Host 规则与 `traefik-shared-network` 配置
- [ ] 首次启动初始化命令、迁移命令、建库建表命令、管理员初始化命令
- [ ] 数据库、Redis、对象存储、auth / OAuth / JWT / callback / secret 等外部依赖配置
- [ ] 每个真实目录是否需要预创建、由谁创建、以什么 owner/group/mode 创建

## 当前服务拓扑初稿
- `build-site`
  image: `registry.lazycat.cloud/placeholder/calcite:build-site`
  binds: `/lzcapp/var/data/calcite/build-site/jekyll:/home/jekyll`
- `dev`
  image: `registry.lazycat.cloud/placeholder/calcite:dev`
  binds: `/lzcapp/var/data/calcite/dev/root:/root`
- `generate-javadoc`
  image: `registry.lazycat.cloud/placeholder/calcite:generate-javadoc`
  binds: `/lzcapp/var/data/calcite/generate-javadoc/calcite:/usr/src/calcite, /lzcapp/var/data/calcite/generate-javadoc/m2:/root/.m2`

## 退出条件
- [ ] 入口、端口、环境变量、真实写路径、初始化命令、数据库/auth 配置全部确认完毕
- [ ] 构建后真实镜像地址已写入 `.lazycat-images.json`，打包阶段从该文件渲染临时 manifest
- [ ] 构建策略相关文件（Dockerfile / template / content / overlay）已补齐
- [ ] 可以进入预检、构建、下载 `.lpk`、安装验收阶段
