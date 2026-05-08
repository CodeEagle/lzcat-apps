# Resumeai Upstream Deployment Checklist

## 已确认字段
- PROJECT_NAME: Resumeai
- PROJECT_SLUG: resumeai
- UPSTREAM_REPO: Doomish77/ResumeAI
- UPSTREAM_URL: https://github.com/Doomish77/ResumeAI
- HOMEPAGE: https://github.com/Doomish77/ResumeAI
- LICENSE: MIT
- AUTHOR: Doomish77
- VERSION: 0.1.0
- IMAGE: TODO
- PORT: 8080
- AI_POD_SERVICE: 无
- AI_POD_SERVICE_NAME: 无
- AI_POD_SERVICE_PORT: 无
- CHECK_STRATEGY: commit_sha
- BUILD_STRATEGY: upstream_with_target_template

## 预填环境变量
- 待补充

## 预填数据路径
- 待补充

## 预填启动说明
- analyze_source raised (未发现 compose、Dockerfile、可识别的前端应用或 release binary); apps/resumeai/Dockerfile.template already written by planner — using upstream_with_target_template route.
- image_targets derived from planner manifest: ['web'].
- sidecar dependencies derived from planner manifest: ['mongo']

## 必扫清单
- [ ] Dockerfile / Containerfile / compose / helm / entrypoint / startup script 的真实启动入口
- [ ] README / 部署文档 / `.env.example` / sample config 中声明的环境变量
- [ ] 数据目录、配置目录、缓存目录、上传目录、日志目录、临时目录的真实读写路径
- [ ] 若启用 AIPod，确认 `ai-pod-service/docker-compose.yml` 中的真实镜像、服务端口、`-ai` Host 规则与 `traefik-shared-network` 配置
- [ ] 首次启动初始化命令、迁移命令、建库建表命令、管理员初始化命令
- [ ] 数据库、Redis、对象存储、auth / OAuth / JWT / callback / secret 等外部依赖配置
- [ ] 每个真实目录是否需要预创建、由谁创建、以什么 owner/group/mode 创建

## 当前服务拓扑初稿
- `mongo`
  image: `mongo:7`
- `web`
  image: `registry.lazycat.cloud/placeholder/resumeai:bootstrap`

## 退出条件
- [ ] 入口、端口、环境变量、真实写路径、初始化命令、数据库/auth 配置全部确认完毕
- [ ] 构建后真实镜像地址已写入 `.lazycat-images.json`，打包阶段从该文件渲染临时 manifest
- [ ] 构建策略相关文件（Dockerfile / template / content / overlay）已补齐
- [ ] 可以进入预检、构建、下载 `.lpk`、安装验收阶段
