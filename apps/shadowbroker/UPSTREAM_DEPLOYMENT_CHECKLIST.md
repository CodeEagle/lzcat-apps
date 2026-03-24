# Shadowbroker Upstream Deployment Checklist

## 已确认字段
- PROJECT_NAME: Shadowbroker
- PROJECT_SLUG: shadowbroker
- UPSTREAM_REPO: BigBodyCobain/Shadowbroker
- UPSTREAM_URL: https://github.com/BigBodyCobain/Shadowbroker
- HOMEPAGE: https://github.com/BigBodyCobain/Shadowbroker
- LICENSE: AGPL-3.0
- AUTHOR: BigBodyCobain
- VERSION: 0.9.5
- IMAGE: TODO
- PORT: 3000
- CHECK_STRATEGY: github_release
- BUILD_STRATEGY: upstream_dockerfile

## 预填环境变量
- `AIS_API_KEY`: From compose service backend (required=True)
- `OPENSKY_CLIENT_ID`: From compose service backend (required=True)
- `OPENSKY_CLIENT_SECRET`: From compose service backend (required=True)
- `LTA_ACCOUNT_KEY`: From compose service backend (required=True)
- `CORS_ORIGINS`: From compose service backend (required=False)
- `BACKEND_URL`: From compose service frontend (required=False)

## 预填数据路径
- `/app/data` <= `/lzcapp/var/data/shadowbroker/backend/data` (From compose service backend)

## 预填启动说明
- 自动扫描到 compose 文件：docker-compose.yml
- 主服务推断为 `frontend`，入口端口 `3000`。
- 扫描到 env 示例文件：.env.example, .env.example
- 扫描到 README：README.md, README.md, README.md

## 必扫清单
- [ ] Dockerfile / Containerfile / compose / helm / entrypoint / startup script 的真实启动入口
- [ ] README / 部署文档 / `.env.example` / sample config 中声明的环境变量
- [ ] 数据目录、配置目录、缓存目录、上传目录、日志目录、临时目录的真实读写路径
- [ ] 首次启动初始化命令、迁移命令、建库建表命令、管理员初始化命令
- [ ] 数据库、Redis、对象存储、auth / OAuth / JWT / callback / secret 等外部依赖配置
- [ ] 每个真实目录是否需要预创建、由谁创建、以什么 owner/group/mode 创建

## 当前服务拓扑初稿
- `backend`
  image: `registry.lazycat.cloud/placeholder/shadowbroker:backend`
  binds: `/lzcapp/var/data/shadowbroker/backend/data:/app/data`
  environment: `AIS_API_KEY, OPENSKY_CLIENT_ID, OPENSKY_CLIENT_SECRET, LTA_ACCOUNT_KEY, CORS_ORIGINS`
- `frontend`
  image: `registry.lazycat.cloud/placeholder/shadowbroker:frontend`
  depends_on: `backend`
  environment: `BACKEND_URL=http://backend:8000`

## 退出条件
- [ ] 入口、端口、环境变量、真实写路径、初始化命令、数据库/auth 配置全部确认完毕
- [ ] `lzc-manifest.yml` 中的镜像地址已替换为真实的 `registry.lazycat.cloud/...`
- [ ] 构建策略相关文件（Dockerfile / template / content / overlay）已补齐
- [ ] 可以进入预检、构建、下载 `.lpk`、安装验收阶段
