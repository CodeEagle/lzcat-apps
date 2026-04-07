# goclaw Upstream Deployment Checklist

## 已确认字段
- PROJECT_NAME: goclaw
- PROJECT_SLUG: goclaw
- UPSTREAM_REPO: nextlevelbuilder/goclaw
- UPSTREAM_URL: https://github.com/nextlevelbuilder/goclaw
- HOMEPAGE: https://goclaw.sh
- LICENSE: NOASSERTION
- AUTHOR: nextlevelbuilder
- VERSION: 2.67.4
- IMAGE: TODO
- PORT: 18790
- AI_POD_SERVICE: 无
- AI_POD_SERVICE_NAME: 无
- AI_POD_SERVICE_PORT: 无
- CHECK_STRATEGY: github_release
- BUILD_STRATEGY: upstream_dockerfile

## 预填环境变量
- `GOCLAW_HOST`: From compose service goclaw (required=False)
- `GOCLAW_PORT`: From compose service goclaw (required=False)
- `GOCLAW_CONFIG`: From compose service goclaw (required=False)
- `GOCLAW_GATEWAY_TOKEN`: From compose service goclaw (required=False)
- `GOCLAW_ENCRYPTION_KEY`: From compose service goclaw (required=False)
- `GOCLAW_SKILLS_DIR`: From compose service goclaw (required=False)
- `GOCLAW_TRACE_VERBOSE`: From compose service goclaw (required=False)
- `POSTGRES_PASSWORD`: From .env.example (required=False)
- `VITE_BACKEND_PORT`: From .env.example (required=False)
- `VITE_BACKEND_HOST`: From .env.example (required=False)
- `VITE_WS_URL`: From .env.example (required=False)

## 预填数据路径
- `/app/data` <= `/lzcapp/var/data/goclaw/goclaw/data` (From compose service goclaw)
- `/app/workspace` <= `/lzcapp/var/data/goclaw/goclaw/workspace` (From compose service goclaw)

## 预填启动说明
- 自动扫描到 compose 文件：docker-compose.yml
- 主服务推断为 `goclaw`，入口端口 `18790`。
- 扫描到 env 示例文件：.env.example, .env.example
- 扫描到 README：README.md, README.ar.md, README.bn.md

## 必扫清单
- [ ] Dockerfile / Containerfile / compose / helm / entrypoint / startup script 的真实启动入口
- [ ] README / 部署文档 / `.env.example` / sample config 中声明的环境变量
- [ ] 数据目录、配置目录、缓存目录、上传目录、日志目录、临时目录的真实读写路径
- [ ] 若启用 AIPod，确认 `ai-pod-service/docker-compose.yml` 中的真实镜像、服务端口、`-ai` Host 规则与 `traefik-shared-network` 配置
- [ ] 首次启动初始化命令、迁移命令、建库建表命令、管理员初始化命令
- [ ] 数据库、Redis、对象存储、auth / OAuth / JWT / callback / secret 等外部依赖配置
- [ ] 每个真实目录是否需要预创建、由谁创建、以什么 owner/group/mode 创建

## 当前服务拓扑初稿
- `goclaw`
  image: `registry.lazycat.cloud/placeholder/goclaw:goclaw`
  binds: `/lzcapp/var/data/goclaw/goclaw/data:/app/data, /lzcapp/var/data/goclaw/goclaw/workspace:/app/workspace`
  environment: `GOCLAW_HOST=0.0.0.0, GOCLAW_PORT=18790, GOCLAW_CONFIG=/app/data/config.json, GOCLAW_GATEWAY_TOKEN=, GOCLAW_ENCRYPTION_KEY=, GOCLAW_SKILLS_DIR=/app/data/skills, GOCLAW_TRACE_VERBOSE=0`

## 退出条件
- [ ] 入口、端口、环境变量、真实写路径、初始化命令、数据库/auth 配置全部确认完毕
- [ ] 构建后真实镜像地址已写入 `.lazycat-images.json`，打包阶段从该文件渲染临时 manifest
- [ ] 构建策略相关文件（Dockerfile / template / content / overlay）已补齐
- [ ] 可以进入预检、构建、下载 `.lpk`、安装验收阶段
