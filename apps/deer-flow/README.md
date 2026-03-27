# deer-flow

本目录由 `scripts/bootstrap_migration.py` 生成，用于把上游 `bytedance/deer-flow` 初始化为懒猫微服迁移项目。

## 上游项目
- Upstream Repo: bytedance/deer-flow
- Homepage: https://deerflow.tech
- License: MIT
- Author: bytedance
- Version Strategy: `github_release` -> 当前初稿版本 `0.1.0`

## 当前迁移骨架
- Build Strategy: `upstream_dockerfile`
- Primary Subdomain: `deer-flow`
- Image Targets: `frontend, gateway, langgraph`
- Service Port: `2026`

### Services
- `config-ui` -> `registry.lazycat.cloud/placeholder/deer-flow:frontend`
- `nginx` -> `registry.lazycat.cloud/placeholder/deer-flow:nginx`
- `frontend` -> `registry.lazycat.cloud/placeholder/deer-flow:frontend`
- `gateway` -> `registry.lazycat.cloud/placeholder/deer-flow:gateway`
- `langgraph` -> `registry.lazycat.cloud/placeholder/deer-flow:langgraph`

## 环境变量

| 变量名 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- |
| BETTER_AUTH_SECRET | No | ${LAZYCAT_APP_ID}-${LAZYCAT_BOX_DOMAIN}-better-auth | 前端会话密钥，默认按应用域名生成 |
| OPENAI_API_KEY | No | - | 默认模板模型使用的 API Key |
| OPENROUTER_API_KEY | No | - | 可选 OpenAI-compatible 网关 |
| ANTHROPIC_API_KEY | No | - | 可选 Claude 模型 |
| GEMINI_API_KEY | No | - | 可选 Gemini 模型 |
| GOOGLE_API_KEY | No | - | 可选 Google 模型 |
| DEEPSEEK_API_KEY | No | - | 可选 DeepSeek 模型 |
| VOLCENGINE_API_KEY | No | - | 可选火山引擎模型 |
| TAVILY_API_KEY | No | - | Web Search 工具 |
| JINA_API_KEY | No | - | Web Fetch 工具 |
| INFOQUEST_API_KEY | No | - | 可选 InfoQuest 工具 |
| FIRECRAWL_API_KEY | No | - | 可选抓取工具 |
| GITHUB_TOKEN | No | - | 可选 GitHub MCP / API 访问令牌 |
| LANGCHAIN_TRACING_V2 | No | false | 默认关闭 LangSmith tracing |

## 数据目录

| 宿主路径 | 容器路径 | 说明 |
| --- | --- | --- |
| /lzcapp/var/data/deer-flow/runtime | /app/backend/.deer-flow | DeerFlow 线程、workspace、uploads、outputs 持久化目录 |
| /lzcapp/var/data/deer-flow/langgraph-api | /app/backend/.langgraph_api | LangGraph 运行时目录 |

## 首次启动/验收提醒

- 自动扫描到 compose 文件：docker/docker-compose.yaml
- 首次访问会进入应用内配置页，用户通过下拉选项选择模型提供方和默认模型后再启动 DeerFlow。
- 配置完成后可随时访问 `/settings/config` 重新修改。
- 当前默认走 LocalSandboxProvider，避免依赖 Docker Socket 或 Kubernetes provisioner。
- 服务启动前会根据应用内表单状态自动渲染 `/lzcapp/var/data/deer-flow/config/config.yaml`。
- 当前内置的是 OpenAI / OpenRouter 下拉选项；如果后续要支持更多 provider，可继续扩展 schema 和渲染脚本。

## 下一步

1. 补完 `UPSTREAM_DEPLOYMENT_CHECKLIST.md`，把真实入口、环境变量、写路径和初始化动作全部核实清楚。
2. 按真实部署拓扑修正 `lzc-manifest.yml`，不要直接沿用占位镜像、端口或命令。
3. 如果是源码构建，补齐 `Dockerfile` / `Dockerfile.template`、`content/`、`overlay_paths` 等资产。
4. 初稿补全后执行 `./scripts/local_build.sh deer-flow --check-only`，再进入实际构建与验收。
