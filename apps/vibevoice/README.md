# VibeVoice

本目录由 `scripts/bootstrap_migration.py` 生成，用于把上游 `microsoft/VibeVoice` 初始化为懒猫微服迁移项目。

## 上游项目
- Upstream Repo: microsoft/VibeVoice
- Homepage: https://microsoft.github.io/VibeVoice/
- License: MIT
- Author: microsoft
- Version Strategy: `github_release` -> 当前初稿版本 `0.1.0`

## 当前迁移骨架
- Build Strategy: `official_image`
- Primary Subdomain: `vibevoice`
- Image Targets: `gateway`
- Service Port: `80`

### Services
- `gateway` -> `registry.lazycat.cloud/placeholder/gateway:bootstrap`

## AIPod

- AI Pod Service Dir: `./ai-pod-service`
- AI Service Name: `vibevoice`
- AI Service Port: `3000`
- AI Service Host: `https://vibevoice-ai.{{ .S.BoxDomain }}`
- 当前骨架已包含算力舱目录，但仍需把真实 GPU 服务镜像、命令、路由与前端代理补齐。

## 环境变量

当前未预填环境变量，待补充。

## 数据目录

当前未声明持久化目录，待从上游部署清单补充。

## 首次启动/验收提醒

- 检测到该仓库更像 GPU-first 的语音/推理研究项目。 依据：README / docs 明确要求 nvidia deep learning container, --gpus all, cuda environment, flash attention，且主要入口是 gradio demo, websocket demo, real-time websocket demo。 按当前 SOP，应优先评估 LazyCat AIPod / AI 应用路线，而不是继续强压到 CPU/Docker 微服容器。
- 已自动改走 AIPod 骨架：微服侧保留 gateway/content，GPU 推理服务迁到 ai-pod-service。
- 当前 AI 服务预估端口为 3000，预期域名为 https://vibevoice-ai.{{ .S.BoxDomain }} 。
- 若上游没有公开官方镜像，需后续手动补齐 ai-pod-service/docker-compose.yml 的真实镜像与启动命令。
- 未扫描到 env 示例文件
- 扫描到 README：README.md, README.md

## 下一步

1. 补完 `UPSTREAM_DEPLOYMENT_CHECKLIST.md`，把真实入口、环境变量、写路径和初始化动作全部核实清楚。
2. 按真实部署拓扑修正 `lzc-manifest.yml`，不要直接沿用占位镜像、端口或命令。
3. 如果是源码构建，补齐 `Dockerfile` / `Dockerfile.template`、`content/`、`overlay_paths` 等资产。
4. 补齐 `ai-pod-service/docker-compose.yml` 中的真实 GPU 服务镜像、启动命令、卷挂载与 `-ai` 路由标签。
5. 初稿补全后执行 `./scripts/local_build.sh vibevoice --check-only`，再进入实际构建与验收。
