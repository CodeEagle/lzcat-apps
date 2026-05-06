# mercury-agent

懒猫微服移植版的 [cosmicstack-labs/mercury-agent](https://github.com/cosmicstack-labs/mercury-agent)。

Mercury 上游为 Node.js CLI agent，本镜像在单容器内提供：

- nginx 反代 (`:80`) — 唯一外部入口
- ttyd（Web 终端，监听 `127.0.0.1:7681`）
- 全局安装的 `mercury` CLI（npm `@cosmicstack/mercury-agent`）
- 默认入口=Web 终端：访问根路径直接进入 `mercury` CLI；CLI 退出后落到 `bash --login`
- nginx 在 ttyd 主页 HTML 注入悬浮球（floatball）资源；floatball **仅** 提供一个入口：`File Explorer`
- File Explorer 为纯静态前端 + nginx `autoindex_format json` 列目录、`alias` 直读文件，零 Python/Node 后端逻辑

## 上游

| 字段 | 值 |
| --- | --- |
| Upstream Repo | cosmicstack-labs/mercury-agent |
| Homepage | https://mercury.cosmicstack.org/ |
| License | MIT |
| Author | Cosmic Stack |
| Check Strategy | `github_release` |
| Build Strategy | `target_repo_dockerfile`（npm 安装，无需 clone 上游源） |
| Image Targets | `mercury-agent` |
| Service Port | `80` |

## 服务拓扑

| 服务 | 监听 | 说明 |
| --- | --- | --- |
| nginx | 80 | 唯一外部入口；反代 ttyd、注入 floatball、提供 explorer 静态页 + autoindex JSON |
| ttyd | 127.0.0.1:7681 | Web 终端；每会话 spawn `/app/run-mercury.sh`，启动交互式 mercury |
| mercury daemon | (后台) | supervisord 拉起 `mercury start --daemon`；24/7 运行 scheduler/heartbeat/Telegram 通道；首次安装后等到 `mercury.yaml` 出现才启动 |

## 数据目录

| 宿主路径 | 容器路径 | 说明 |
| --- | --- | --- |
| `/lzcapp/var/data/mercury-agent` | `/data` | `MERCURY_HOME`：mercury config / memory / .env / 全局 npm/pip 用户目录持久化 |
| `/lzcapp/var/data/mercury-agent/workspace` | `/root/workspace` | 工作区（终端默认 `cwd=/data`，`workspace` 仅做 explorer 浏览根） |

## 环境变量

`mercury` 自带 CLI setup wizard；首次启动后在终端里 `mercury` 即进入向导。也可以预先通过 LazyCat 应用环境变量配置：

| 变量 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- |
| `MERCURY_HOME` | No | `/data` | 持久化根；Second Brain 自动落 `${MERCURY_HOME}/memory`（上游硬编） |
| `DEFAULT_PROVIDER` | No | `deepseek` | `deepseek/openai/anthropic/grok/ollamaCloud/ollamaLocal` |
| `OPENAI_API_KEY` / `OPENAI_BASE_URL` / `OPENAI_MODEL` | No | - | OpenAI 兼容 |
| `ANTHROPIC_API_KEY` / `ANTHROPIC_MODEL` | No | - | Anthropic |
| `DEEPSEEK_API_KEY` / `DEEPSEEK_BASE_URL` / `DEEPSEEK_MODEL` | No | - | DeepSeek |
| `GROK_API_KEY` / `GROK_BASE_URL` / `GROK_MODEL` | No | - | xAI / Grok |
| `OLLAMA_CLOUD_*` / `OLLAMA_LOCAL_*` | No | - | Ollama |
| `TELEGRAM_BOT_TOKEN` | No | - | Telegram 通道 |
| `HEARTBEAT_INTERVAL_MINUTES` | No | `60` | 心跳频率 |
| `DAILY_TOKEN_BUDGET` | No | `50000` | 每日 token 预算 |
| `GITHUB_TOKEN` / `GITHUB_USERNAME` / `GITHUB_EMAIL` / `GITHUB_DEFAULT_OWNER` / `GITHUB_DEFAULT_REPO` | No | - | GitHub 工具 |
| `MERCURY_NAME` / `MERCURY_OWNER` | No | - | Agent identity |

未在 manifest 显式列出的上游环境变量可在 LazyCat 应用配置中自行追加。

## 访问入口

- 主页 = Web 终端，自动尝试启动 `mercury`；用户可在终端里完成 setup wizard 与日常对话
- 右下角 floatball ⚘ 点开 → `File Explorer`（浏览 `/data`、`/root/workspace`、`/etc/nginx`、`/etc/supervisor`）

## 构建与本地验证

```sh
./scripts/local_build.sh mercury-agent --check-only
./scripts/local_build.sh mercury-agent --force-build
./scripts/local_build.sh mercury-agent --install --with-docker
```

## 与 hermes 的差异

本应用借鉴 `apps/hermes/` 的 nginx + supervisord 单镜像思路，但做了大幅简化：

- 没有 hermes-webui / hermes-agent / setup-wizard 中间页
- 没有 UI switcher / Update Checker / Reset Config
- 不引入 Python / FastAPI；终端用 ttyd，文件浏览用 nginx autoindex JSON + 静态前端
- floatball 仅保留 File Explorer 一项菜单
- 终端默认启动 `mercury` 而非 `hermes`，退出后落到 `bash --login`
