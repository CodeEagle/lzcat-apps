# StellaClaw Upstream Deployment Checklist

## 已确认字段
- PROJECT_NAME: StellaClaw
- PROJECT_SLUG: stellaclaw
- UPSTREAM_REPO: JeremyGuo/StellaClaw
- UPSTREAM_URL: https://github.com/JeremyGuo/StellaClaw
- HOMEPAGE: https://github.com/JeremyGuo/StellaClaw
- LICENSE: 
- AUTHOR: JeremyGuo
- VERSION: 1.25.0
- IMAGE: TODO
- PORT: 80
- AI_POD_SERVICE: 无
- AI_POD_SERVICE_NAME: 无
- AI_POD_SERVICE_PORT: 无
- CHECK_STRATEGY: github_release
- BUILD_STRATEGY: upstream_with_target_template

## 预填环境变量
- 待补充

## 预填数据路径
- 待补充

## 预填启动说明
- 检测到前端应用目录 `apps/stellacodeX/electron` 使用静态站构建，可按 nginx 托管产物封装。
- 构建目录：`apps/stellacodeX/electron`；安装根目录：`apps/stellacodeX/electron`。
- 自动推断构建命令：`npm run build`。
- 运行时按静态站处理，由 nginx 托管构建产物目录。
- 未扫描到 env 示例文件
- 扫描到 README：README.md, README_zh.md, README.md
- 扫描到上游图标：apps/stellacodeX/ios/StellaCodeX/StellaCodeX/Assets.xcassets/AppIcon.appiconset/Icon-App-256x256@1x.png

## 必扫清单
- [ ] Dockerfile / Containerfile / compose / helm / entrypoint / startup script 的真实启动入口
- [ ] README / 部署文档 / `.env.example` / sample config 中声明的环境变量
- [ ] 数据目录、配置目录、缓存目录、上传目录、日志目录、临时目录的真实读写路径
- [ ] 若启用 AIPod，确认 `ai-pod-service/docker-compose.yml` 中的真实镜像、服务端口、`-ai` Host 规则与 `traefik-shared-network` 配置
- [ ] 首次启动初始化命令、迁移命令、建库建表命令、管理员初始化命令
- [ ] 数据库、Redis、对象存储、auth / OAuth / JWT / callback / secret 等外部依赖配置
- [ ] 每个真实目录是否需要预创建、由谁创建、以什么 owner/group/mode 创建

## 当前服务拓扑初稿
- `stellaclaw-web`
  image: `registry.lazycat.cloud/placeholder/stellaclaw:bootstrap`

## 退出条件
- [ ] 入口、端口、环境变量、真实写路径、初始化命令、数据库/auth 配置全部确认完毕
- [ ] 构建后真实镜像地址已写入 `.lazycat-images.json`，打包阶段从该文件渲染临时 manifest
- [ ] 构建策略相关文件（Dockerfile / template / content / overlay）已补齐
- [ ] 可以进入预检、构建、下载 `.lpk`、安装验收阶段
