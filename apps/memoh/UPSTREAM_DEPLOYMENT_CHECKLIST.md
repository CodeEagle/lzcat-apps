# Memoh Upstream Deployment Checklist

## 已确认字段
- PROJECT_NAME: Memoh
- PROJECT_SLUG: memoh
- UPSTREAM_REPO: memohai/Memoh
- UPSTREAM_URL: https://github.com/memohai/Memoh
- HOMEPAGE: https://docs.memoh.ai
- LICENSE: AGPL-3.0
- AUTHOR: memohai
- VERSION: 0.6.3
- IMAGE: memohai/web
- PORT: 8082
- AI_POD_SERVICE: 无
- AI_POD_SERVICE_NAME: 无
- AI_POD_SERVICE_PORT: 无
- CHECK_STRATEGY: github_release
- BUILD_STRATEGY: official_image

## 预填环境变量
- `POSTGRES_DB`: From compose service postgres (required=False)
- `POSTGRES_USER`: From compose service postgres (required=False)
- `POSTGRES_PASSWORD`: From compose service postgres (required=False)
- `BROWSER_CORES`: From compose service browser (required=False)

## 预填数据路径
- `/var/lib/postgresql` <= `/lzcapp/var/db/memoh/postgres` (From compose service postgres)
- `/var/lib/containerd` <= `/lzcapp/var/data/memoh/server/containerd` (From compose service server)
- `/var/lib/cni` <= `/lzcapp/var/data/memoh/server/cni` (From compose service server)
- `/opt/memoh/data` <= `/lzcapp/var/data/memoh/server/data` (From compose service server)
- `/qdrant/storage` <= `/lzcapp/var/data/memoh/qdrant/storage` (From compose service qdrant)

## 预填启动说明
- 自动扫描到 compose 文件：docker-compose.yml
- 主服务推断为 `web`，入口端口 `8082`。
- 依赖服务镜像已写入 dependencies，首次完整构建时会自动 copy-image。
- 未扫描到 env 示例文件
- 扫描到 README：README.md, README_CN.md, README.md

## 必扫清单
- [ ] Dockerfile / Containerfile / compose / helm / entrypoint / startup script 的真实启动入口
- [ ] README / 部署文档 / `.env.example` / sample config 中声明的环境变量
- [ ] 数据目录、配置目录、缓存目录、上传目录、日志目录、临时目录的真实读写路径
- [ ] 若启用 AIPod，确认 `ai-pod-service/docker-compose.yml` 中的真实镜像、服务端口、`-ai` Host 规则与 `traefik-shared-network` 配置
- [ ] 首次启动初始化命令、迁移命令、建库建表命令、管理员初始化命令
- [ ] 数据库、Redis、对象存储、auth / OAuth / JWT / callback / secret 等外部依赖配置
- [ ] 每个真实目录是否需要预创建、由谁创建、以什么 owner/group/mode 创建

## 当前服务拓扑初稿
- `postgres`
  image: `registry.lazycat.cloud/placeholder/memoh:postgres`
  binds: `/lzcapp/var/db/memoh/postgres:/var/lib/postgresql`
  environment: `POSTGRES_DB=memoh, POSTGRES_USER=memoh, POSTGRES_PASSWORD=memoh123`
- `migrate`
  image: `registry.lazycat.cloud/placeholder/memoh:migrate`
  depends_on: `postgres`
- `server`
  image: `registry.lazycat.cloud/placeholder/memoh:server`
  depends_on: `migrate`
  binds: `/lzcapp/var/data/memoh/server/containerd:/var/lib/containerd, /lzcapp/var/data/memoh/server/cni:/var/lib/cni, /lzcapp/var/data/memoh/server/data:/opt/memoh/data`
- `web`
  image: `registry.lazycat.cloud/placeholder/memoh:web`
  depends_on: `server`
- `sparse`
  image: `registry.lazycat.cloud/placeholder/memoh:sparse`
- `qdrant`
  image: `registry.lazycat.cloud/placeholder/memoh:qdrant`
  binds: `/lzcapp/var/data/memoh/qdrant/storage:/qdrant/storage`
- `browser`
  image: `registry.lazycat.cloud/placeholder/memoh:browser`
  depends_on: `server`
  environment: `BROWSER_CORES=chromium,firefox`

## 退出条件
- [ ] 入口、端口、环境变量、真实写路径、初始化命令、数据库/auth 配置全部确认完毕
- [ ] `lzc-manifest.yml` 中的镜像地址已替换为真实的 `registry.lazycat.cloud/...`
- [ ] 构建策略相关文件（Dockerfile / template / content / overlay）已补齐
- [ ] 可以进入预检、构建、下载 `.lpk`、安装验收阶段
