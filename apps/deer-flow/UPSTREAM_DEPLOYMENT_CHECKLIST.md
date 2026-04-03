# deer-flow Upstream Deployment Checklist

## 已确认字段
- PROJECT_NAME: deer-flow
- PROJECT_SLUG: deer-flow
- UPSTREAM_REPO: bytedance/deer-flow
- UPSTREAM_URL: https://github.com/bytedance/deer-flow
- HOMEPAGE: https://deerflow.tech
- LICENSE: MIT
- AUTHOR: bytedance
- VERSION: 0.1.0
- IMAGE: TODO
- PORT: 2026
- CHECK_STRATEGY: github_release
- BUILD_STRATEGY: upstream_dockerfile

## 预填环境变量
- `BETTER_AUTH_SECRET`: 前端会话密钥，默认按应用域名生成 (required=False)
- `OPENAI_API_KEY`: 默认模板模型使用的 API Key (required=False)
- `OPENROUTER_API_KEY`: 可选 OpenAI-compatible 网关 (required=False)
- `ANTHROPIC_API_KEY`: 可选 Claude 模型 (required=False)
- `GEMINI_API_KEY`: 可选 Gemini 模型 (required=False)
- `GOOGLE_API_KEY`: 可选 Google 模型 (required=False)
- `DEEPSEEK_API_KEY`: 可选 DeepSeek 模型 (required=False)
- `VOLCENGINE_API_KEY`: 可选火山引擎模型 (required=False)
- `TAVILY_API_KEY`: Web Search 工具 (required=False)
- `JINA_API_KEY`: Web Fetch 工具 (required=False)
- `INFOQUEST_API_KEY`: 可选 InfoQuest 工具 (required=False)
- `FIRECRAWL_API_KEY`: 可选抓取工具 (required=False)
- `GITHUB_TOKEN`: 可选 GitHub MCP / API 访问令牌 (required=False)
- `LANGCHAIN_TRACING_V2`: 默认关闭 LangSmith tracing (required=False)

## 预填数据路径
- `/app/backend/.deer-flow` <= `/lzcapp/var/data/deer-flow/runtime` (DeerFlow 线程、workspace、uploads、outputs 持久化目录)
- `/app/backend/.langgraph_api` <= `/lzcapp/var/data/deer-flow/langgraph-api` (LangGraph 运行时目录)

## 预填启动说明
- 自动扫描到 compose 文件：docker/docker-compose.yaml
- 首次安装和后续重配置均使用 `lzc-deploy-params.yml` 提供的官方部署参数页。
- 当前默认走 LocalSandboxProvider，避免依赖 Docker Socket 或 Kubernetes provisioner。
- 服务启动前会读取部署参数，并同步写回 `/lzcapp/var/data/deer-flow/config/model.env` 和 `/lzcapp/var/data/deer-flow/config/config.yaml`。

## 必扫清单
- [ ] Dockerfile / Containerfile / compose / helm / entrypoint / startup script 的真实启动入口
- [ ] README / 部署文档 / `.env.example` / sample config 中声明的环境变量
- [ ] 数据目录、配置目录、缓存目录、上传目录、日志目录、临时目录的真实读写路径
- [ ] 首次启动初始化命令、迁移命令、建库建表命令、管理员初始化命令
- [ ] 数据库、Redis、对象存储、auth / OAuth / JWT / callback / secret 等外部依赖配置
- [ ] 每个真实目录是否需要预创建、由谁创建、以什么 owner/group/mode 创建

## 当前服务拓扑初稿
- `nginx`
  image: `registry.lazycat.cloud/placeholder/deer-flow:nginx`
  binds: `/lzcapp/pkg/content/nginx.conf:/etc/nginx/nginx.conf`
  environment: `DEER_FLOW_MODEL_PROVIDER_PRESET=openai, DEER_FLOW_MODEL_NAME=default-chat, DEER_FLOW_MODEL_DISPLAY_NAME=Default Chat Model, DEER_FLOW_MODEL_ID=gpt-4.1-mini, DEER_FLOW_MODEL_BASE_URL=, DEER_FLOW_MODEL_API_KEY=, DEER_FLOW_MODEL_USE_RESPONSES_API=false, DEER_FLOW_MODEL_TEMPERATURE=0.7, TAVILY_API_KEY=, JINA_API_KEY=`
- `frontend`
  image: `registry.lazycat.cloud/placeholder/deer-flow:frontend`
  environment: `BETTER_AUTH_SECRET=${LAZYCAT_APP_ID}-${LAZYCAT_BOX_DOMAIN}-better-auth, NODE_ENV=development, NEXT_TELEMETRY_DISABLED=1, DEER_FLOW_MODEL_PROVIDER_PRESET=openai, DEER_FLOW_MODEL_NAME=default-chat, DEER_FLOW_MODEL_DISPLAY_NAME=Default Chat Model, DEER_FLOW_MODEL_ID=gpt-4.1-mini, DEER_FLOW_MODEL_BASE_URL=, DEER_FLOW_MODEL_API_KEY=, DEER_FLOW_MODEL_USE_RESPONSES_API=false, DEER_FLOW_MODEL_TEMPERATURE=0.7, TAVILY_API_KEY=, JINA_API_KEY=`
- `gateway`
  image: `registry.lazycat.cloud/placeholder/deer-flow:gateway`
  binds: `/lzcapp/var/data/deer-flow/runtime:/app/backend/.deer-flow`
  environment: `CI=true, DEER_FLOW_HOME=/app/backend/.deer-flow, DEER_FLOW_CONFIG_PATH=/lzcapp/var/data/deer-flow/config/config.yaml, DEER_FLOW_EXTENSIONS_CONFIG_PATH=/lzcapp/var/data/deer-flow/config/extensions_config.json, OPENAI_API_KEY, OPENROUTER_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY, GOOGLE_API_KEY, DEEPSEEK_API_KEY, VOLCENGINE_API_KEY, TAVILY_API_KEY, JINA_API_KEY, INFOQUEST_API_KEY, FIRECRAWL_API_KEY, GITHUB_TOKEN, DEER_FLOW_MODEL_PROVIDER_PRESET=openai, DEER_FLOW_MODEL_NAME=default-chat, DEER_FLOW_MODEL_DISPLAY_NAME=Default Chat Model, DEER_FLOW_MODEL_ID=gpt-4.1-mini, DEER_FLOW_MODEL_BASE_URL=, DEER_FLOW_MODEL_API_KEY=, DEER_FLOW_MODEL_USE_RESPONSES_API=false, DEER_FLOW_MODEL_TEMPERATURE=0.7, TAVILY_API_KEY=, JINA_API_KEY=`
- `langgraph`
  image: `registry.lazycat.cloud/placeholder/deer-flow:langgraph`
  binds: `/lzcapp/var/data/deer-flow/runtime:/app/backend/.deer-flow, /lzcapp/var/data/deer-flow/langgraph-api:/app/backend/.langgraph_api`
  environment: `CI=true, DEER_FLOW_HOME=/app/backend/.deer-flow, DEER_FLOW_CONFIG_PATH=/lzcapp/var/data/deer-flow/config/config.yaml, DEER_FLOW_EXTENSIONS_CONFIG_PATH=/lzcapp/var/data/deer-flow/config/extensions_config.json, OPENAI_API_KEY, OPENROUTER_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY, GOOGLE_API_KEY, DEEPSEEK_API_KEY, VOLCENGINE_API_KEY, TAVILY_API_KEY, JINA_API_KEY, INFOQUEST_API_KEY, FIRECRAWL_API_KEY, GITHUB_TOKEN, DEER_FLOW_MODEL_PROVIDER_PRESET=openai, DEER_FLOW_MODEL_NAME=default-chat, DEER_FLOW_MODEL_DISPLAY_NAME=Default Chat Model, DEER_FLOW_MODEL_ID=gpt-4.1-mini, DEER_FLOW_MODEL_BASE_URL=, DEER_FLOW_MODEL_API_KEY=, DEER_FLOW_MODEL_USE_RESPONSES_API=false, DEER_FLOW_MODEL_TEMPERATURE=0.7, TAVILY_API_KEY=, JINA_API_KEY=, LANGCHAIN_TRACING_V2=false`

## 退出条件
- [ ] 入口、端口、环境变量、真实写路径、初始化命令、数据库/auth 配置全部确认完毕
- [ ] `lzc-manifest.yml` 中的镜像地址已替换为真实的 `registry.lazycat.cloud/...`
- [ ] 构建策略相关文件（Dockerfile / template / content / overlay）已补齐
- [ ] 可以进入预检、构建、下载 `.lpk`、安装验收阶段
