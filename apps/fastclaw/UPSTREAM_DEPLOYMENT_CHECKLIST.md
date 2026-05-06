# fastclaw Upstream Deployment Checklist

## 已确认字段
- PROJECT_NAME: fastclaw
- PROJECT_SLUG: fastclaw
- UPSTREAM_REPO: fastclaw-ai/fastclaw
- UPSTREAM_URL: https://github.com/fastclaw-ai/fastclaw
- HOMEPAGE: https://github.com/fastclaw-ai/fastclaw
- LICENSE: MIT
- AUTHOR: fastclaw-ai
- VERSION: 0.20.0
- IMAGE: precompiled binary (fastclaw_linux_amd64)
- PORT: 18953
- CHECK_STRATEGY: github_release
- BUILD_STRATEGY: precompiled_binary

## 预填环境变量
- HOME=/root (容器内)
- FASTCLAW_CONFIG_DIR=/root/.fastclaw (可选)

## 预填数据路径
- /lzcapp/var/data/fastclaw -> /root/.fastclaw (配置、agents、skills、memory)

## 预填启动说明
- 自动推断为 release binary 路线。
- 当前只按通用单二进制服务处理，真实监听端口和启动参数仍需验收确认。
- 未扫描到 env 示例文件
- 扫描到 README：README.md, README.md, README.md

## 必扫清单
- [ ] Dockerfile / Containerfile / compose / helm / entrypoint / startup script 的真实启动入口
- [ ] README / 部署文档 / `.env.example` / sample config 中声明的环境变量
- [ ] 数据目录、配置目录、缓存目录、上传目录、日志目录、临时目录的真实读写路径
- [ ] 首次启动初始化命令、迁移命令、建库建表命令、管理员初始化命令
- [ ] 数据库、Redis、对象存储、auth / OAuth / JWT / callback / secret 等外部依赖配置
- [ ] 每个真实目录是否需要预创建、由谁创建、以什么 owner/group/mode 创建

## 当前服务拓扑初稿
- `fastclaw`
  image: `registry.lazycat.cloud/placeholder/fastclaw:bootstrap`

## 退出条件
- [ ] 入口、端口、环境变量、真实写路径、初始化命令、数据库/auth 配置全部确认完毕
- [ ] `lzc-manifest.yml` 中的镜像地址已替换为真实的 `registry.lazycat.cloud/...`
- [ ] 构建策略相关文件（Dockerfile / template / content / overlay）已补齐
- [ ] 可以进入预检、构建、下载 `.lpk`、安装验收阶段
