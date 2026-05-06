# codex-web Upstream Deployment Checklist

## 已确认字段

- PROJECT_NAME: Codex Web
- PROJECT_SLUG: codex-web
- UPSTREAM_REPO: 0xcaff/codex-web
- UPSTREAM_URL: https://github.com/0xcaff/codex-web
- HOMEPAGE: https://github.com/0xcaff/codex-web
- LICENSE: MIT
- AUTHOR: 0xcaff
- VERSION: 0.1.1
- SOURCE_VERSION: upstream commit SHA, current scan `3998af2cb3584610aa63d4f07c23ab4264077740`
- IMAGE: built by `apps/codex-web/Dockerfile`, then rendered through `.lazycat-images.json`
- PORT: 8214
- DATA_PATHS: `/data`, `/data/home/.codex`, `/data/cache`, `/data/config`, `/data/share`, `/data/tmp`, `/workspace`
- ENV_VARS: `HOME`, `CODEX_HOME`, `CODEX_CLI_PATH`, `XDG_CACHE_HOME`, `XDG_CONFIG_HOME`, `XDG_DATA_HOME`, `TMPDIR`, `NODE_ENV`
- STARTUP_NOTES: start Fastify bridge with `node /opt/codex-web/src/server/main.js --host 0.0.0.0 --port 8214`

## 上游部署清单

- Dockerfile / compose / helm: upstream does not ship a Dockerfile or compose file. The LazyCat package uses a custom Dockerfile that clones upstream and runs its npm build.
- Build entry:
  - `npm ci --no-audit --no-fund`
  - upstream `postinstall` runs `scripts/prepare`, `npm run build:browser`, and `npm run build:server`
  - `scripts/prepare` downloads the Codex Desktop app zip and extracts/patches the app asar used by the web runtime
- Runtime entry:
  - `src/server/main.ts`, compiled to `src/server/main.js`
  - default upstream listen address is `127.0.0.1:8214`
  - LazyCat runtime forces `--host 0.0.0.0 --port 8214`
- External command dependency:
  - upstream uses `codex` from `PATH` or `CODEX_CLI_PATH`
  - the LazyCat runtime installs `@openai/codex@0.126.0-alpha.15` and sets `CODEX_CLI_PATH=/usr/local/bin/codex`
- Environment variables declared by upstream docs:
  - `CODEX_CLI_PATH`
  - Advanced proxy mode: `CODEX_REMOTE_WS_URL`, `CODEX_REMOTE_WS_BUFFER_SIZE` when using `scripts/codex_remote_proxy`; not enabled in the default LazyCat package.
- Real writable paths:
  - `/data/home/.codex`: Codex CLI auth/session state, created by runtime command as root with mode `0700`
  - `/data/cache`: XDG cache, created by runtime command
  - `/data/config`: XDG config, created by runtime command
  - `/data/share`: XDG data, created by runtime command
  - `/data/tmp`: Fastify multipart upload temp root via `TMPDIR`, created by runtime command
  - `/workspace`: default workspace exposed to Codex sessions, created by runtime command
- Initialization:
  - No database migration, Redis, object storage, OAuth callback, JWT secret, or admin bootstrap command.
  - First real use requires `codex login --device-auth` inside the service container; auth persists in `/data/home/.codex`.
- Health check:
  - HTTP GET `http://127.0.0.1:8214/`
- Security:
  - Upstream explicitly treats UI access as equivalent to operating Codex as the service user. LazyCat routing should remain private or be protected externally.

## 退出条件

- [x] 入口、端口、环境变量、真实写路径、初始化命令、数据库/auth 配置已确认
- [x] 构建策略相关 Dockerfile 已补齐
- [ ] 构建后真实镜像地址已写入 `.lazycat-images.json`，打包阶段从该文件渲染临时 manifest
- [ ] 可以进入预检、构建、下载 `.lpk`、安装验收阶段
