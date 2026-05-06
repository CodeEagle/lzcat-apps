# VibeVoice Upstream Deployment Checklist

## 已确认字段
- PROJECT_NAME: VibeVoice
- PROJECT_SLUG: vibevoice
- UPSTREAM_REPO: microsoft/VibeVoice
- UPSTREAM_URL: https://github.com/microsoft/VibeVoice
- HOMEPAGE: https://microsoft.github.io/VibeVoice/
- LICENSE: MIT
- AUTHOR: microsoft
- VERSION: 0.1.0
- IMAGE: registry.lazycat.cloud/catdogai/caddy-aipod:65e058ce
- PORT: 80
- AI_POD_SERVICE: ./ai-pod-service
- AI_POD_SERVICE_NAME: vibevoice
- AI_POD_SERVICE_PORT: 3000
- CHECK_STRATEGY: github_release
- BUILD_STRATEGY: official_image

## 预填环境变量
- 待补充

## 预填数据路径
- 待补充

## 预填启动说明
- 检测到该仓库更像 GPU-first 的语音/推理研究项目。 依据：README / docs 明确要求 nvidia deep learning container, --gpus all, cuda environment, flash attention，且主要入口是 gradio demo, websocket demo, real-time websocket demo。 按当前 SOP，应优先评估 LazyCat AIPod / AI 应用路线，而不是继续强压到 CPU/Docker 微服容器。
- 已自动改走 AIPod 骨架：微服侧保留 gateway/content，GPU 推理服务迁到 ai-pod-service。
- 当前 AI 服务预估端口为 3000，预期域名为 https://vibevoice-ai.{{ .S.BoxDomain }} 。
- 若上游没有公开官方镜像，需后续手动补齐 ai-pod-service/docker-compose.yml 的真实镜像与启动命令。
- 未扫描到 env 示例文件
- 扫描到 README：README.md, README.md

## 必扫清单
- [ ] Dockerfile / Containerfile / compose / helm / entrypoint / startup script 的真实启动入口
- [ ] README / 部署文档 / `.env.example` / sample config 中声明的环境变量
- [ ] 数据目录、配置目录、缓存目录、上传目录、日志目录、临时目录的真实读写路径
- [ ] 若启用 AIPod，确认 `ai-pod-service/docker-compose.yml` 中的真实镜像、服务端口、`-ai` Host 规则与 `traefik-shared-network` 配置
- [ ] 首次启动初始化命令、迁移命令、建库建表命令、管理员初始化命令
- [ ] 数据库、Redis、对象存储、auth / OAuth / JWT / callback / secret 等外部依赖配置
- [ ] 每个真实目录是否需要预创建、由谁创建、以什么 owner/group/mode 创建

## 当前服务拓扑初稿
- `gateway`
  image: `registry.lazycat.cloud/placeholder/gateway:bootstrap`

## 退出条件
- [ ] 入口、端口、环境变量、真实写路径、初始化命令、数据库/auth 配置全部确认完毕
- [ ] `lzc-manifest.yml` 中的镜像地址已替换为真实的 `registry.lazycat.cloud/...`
- [ ] 构建策略相关文件（Dockerfile / template / content / overlay）已补齐
- [ ] 可以进入预检、构建、下载 `.lpk`、安装验收阶段
