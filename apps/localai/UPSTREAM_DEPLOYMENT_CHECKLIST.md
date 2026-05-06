# LocalAI Upstream Deployment Checklist

## 已确认字段
- PROJECT_NAME: LocalAI
- PROJECT_SLUG: localai
- UPSTREAM_REPO: mudler/LocalAI
- UPSTREAM_URL: https://github.com/mudler/LocalAI
- HOMEPAGE: https://localai.io
- LICENSE: MIT
- AUTHOR: mudler
- VERSION: 4.1.3
- IMAGE: docker.io/localai/localai
- PORT: 8080
- AI_POD_SERVICE: 无
- AI_POD_SERVICE_NAME: 无
- AI_POD_SERVICE_PORT: 无
- CHECK_STRATEGY: github_release
- BUILD_STRATEGY: official_image

## 预填环境变量
- `MODELS_PATH`: From compose service api (required=False)

## 预填数据路径
- `/models` <= `/lzcapp/var/data/localai/api/models` (From compose service api)
- `/tmp/generated/images/` <= `/lzcapp/var/data/localai/api/images` (From compose service api)
- `/data` <= `/lzcapp/var/data/localai/api` (From compose service api)
- `/backends` <= `/lzcapp/var/data/localai/api/backends` (From compose service api)
- `/configuration` <= `/lzcapp/var/data/localai/api/configuration` (From compose service api)

## 预填启动说明
- 自动扫描到 compose 文件：docker-compose.yaml
- 主服务推断为 `api`，入口端口 `8080`。
- 扫描到 env 示例文件：.env
- 扫描到 README：README.md, README.md, README.md
- 上游 compose 的 `command: phi-2` 是示例模型参数，默认安装不预置模型，避免首启导入失败；模型文件和配置由 `/models`、`/configuration` 持久化目录管理。

## 必扫清单
- [ ] Dockerfile / Containerfile / compose / helm / entrypoint / startup script 的真实启动入口
- [ ] README / 部署文档 / `.env.example` / sample config 中声明的环境变量
- [ ] 数据目录、配置目录、缓存目录、上传目录、日志目录、临时目录的真实读写路径
- [ ] 若启用 AIPod，确认 `ai-pod-service/docker-compose.yml` 中的真实镜像、服务端口、`-ai` Host 规则与 `traefik-shared-network` 配置
- [ ] 首次启动初始化命令、迁移命令、建库建表命令、管理员初始化命令
- [ ] 数据库、Redis、对象存储、auth / OAuth / JWT / callback / secret 等外部依赖配置
- [ ] 每个真实目录是否需要预创建、由谁创建、以什么 owner/group/mode 创建

## 当前服务拓扑初稿
- `api`
  image: `registry.lazycat.cloud/placeholder/localai:api`
  binds: `/lzcapp/var/data/localai/api/models:/models, /lzcapp/var/data/localai/api/images:/tmp/generated/images/, /lzcapp/var/data/localai/api:/data, /lzcapp/var/data/localai/api/backends:/backends, /lzcapp/var/data/localai/api/configuration:/configuration`
  environment: `MODELS_PATH=/models`

## 退出条件
- [ ] 入口、端口、环境变量、真实写路径、初始化命令、数据库/auth 配置全部确认完毕
- [ ] 构建后真实镜像地址已写入 `.lazycat-images.json`，打包阶段从该文件渲染临时 manifest
- [ ] 构建策略相关文件（Dockerfile / template / content / overlay）已补齐
- [ ] 可以进入预检、构建、下载 `.lpk`、安装验收阶段
