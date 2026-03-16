# Paperclip - 懒猫微服迁移项目

本项目将上游 [paperclipai/paperclip](https://github.com/paperclipai/paperclip) 打包为可在懒猫微服中安装的应用。

## 应用说明

Paperclip 是一个面向多智能体团队协作的开源运营平台，提供任务编排、组织结构、预算治理、审计日志和 Web 控制台。

本迁移仓库采用上游官方 Dockerfile 源码构建镜像，运行时使用 `bootstrap-ui + paperclip + postgres` 三服务模式：

- Web 入口：`/`
- 容器内端口：`3100`
- 应用数据目录：`/paperclip`
- 数据库目录：`/var/lib/postgresql/data`
- 持久化挂载：
  - `/lzcapp/var/data -> /paperclip`
  - `/lzcapp/var/db/paperclip/postgres -> /var/lib/postgresql/data`

## 首次启动

首次安装后，认证相关变量默认按懒猫环境预置：

- `BETTER_AUTH_SECRET=paperclip-lazycat-auth-secret`
  默认提供一份可启动的认证签名密钥，避免 `authenticated` 模式因缺失密钥直接启动失败；如需更高安全性，可在后续版本改为用户自定义。
- `PAPERCLIP_PUBLIC_URL=https://${LAZYCAT_APP_DOMAIN}`
  默认绑定到懒猫分配给应用的实际访问地址，避免登录回调或邀请链接指向错误地址。

数据库连接由 manifest 内置：

- `DATABASE_URL=postgres://paperclip:paperclip@postgres:5432/paperclip`

默认环境变量：

- `PAPERCLIP_DEPLOYMENT_MODE=authenticated`
- `PAPERCLIP_DEPLOYMENT_EXPOSURE=private`
- `HOST=0.0.0.0`
- `PORT=3100`
- `SERVE_UI=true`
- `PAPERCLIP_HOME=/paperclip`

首次启动时，`paperclip` 服务会自动执行：

- 先显式准备上游默认实例目录：
  - `/paperclip/instances/default/logs`
  - `/paperclip/instances/default/data/storage`
  - `/paperclip/instances/default/data/backups`
  - `/paperclip/instances/default/data/run-logs`
  - `/paperclip/instances/default/data/plugins`
  - `/paperclip/instances/default/secrets`
  - `/paperclip/instances/default/workspaces`
  - `/paperclip/instances/default/plugins`
- 然后执行：
  - `pnpm paperclipai onboard --yes --data-dir "$PAPERCLIP_HOME"`
  - `pnpm paperclipai auth bootstrap-ceo --data-dir "$PAPERCLIP_HOME" --base-url "$PAPERCLIP_PUBLIC_URL"`

生成出的首个 CEO 邀请链接会被写入：

- `/paperclip/instances/default/bootstrap-invite.log`
- `/paperclip/instances/default/bootstrap-invite-url.txt`

`bootstrap-ui` 前置服务会在还没有首个 admin 时先展示自定义启动页，并把这个 URL 渲染成可点击按钮；当首个 admin 创建完成后，其余请求会直接透传到 Paperclip。

可选环境变量：

- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`

## 数据说明

根据上游 `doc/DOCKER.md` 和当前迁移拓扑，以下数据会被持久化：

- Paperclip 本地文件、附件、workspace 与实例目录：`/lzcapp/var/data`
- PostgreSQL 数据：`/lzcapp/var/db/paperclip/postgres`
- 其中会包含这些上游默认路径：
  - `/paperclip/instances/default/config.json`
  - `/paperclip/instances/default/logs`
  - `/paperclip/instances/default/data/storage`
  - `/paperclip/instances/default/data/backups`
  - `/paperclip/instances/default/data/run-logs`
  - `/paperclip/instances/default/data/plugins`
  - `/paperclip/instances/default/secrets/master.key`
  - `/paperclip/instances/default/workspaces`
  - `/paperclip/instances/default/plugins`

为避免懒猫挂载目录权限导致的首次启动失败，manifest 会在启动前一次性准备整棵上游默认实例目录，而不是只创建单个 `logs` 目录。

## 构建与发布

仓库内的 `.github/workflows/update-image.yml` 只作为目标 workflow 存在，由 `CodeEagle/lzcat-trigger` 统一触发；不再在目标仓库内自行定时触发。实际流程为：

1. 获取上游最新 semver 版本
2. 从上游源码 tag 构建 `ghcr.io/CodeEagle/paperclip:<source-commit-sha>`
3. 复制镜像到 `registry.lazycat.cloud/...`
4. 精确更新 `lzc-manifest.yml` 与 `.lazycat-build.json`
5. 生成 `.lpk` 并发布 GitHub Release

## 上游链接

- Upstream Repo: https://github.com/paperclipai/paperclip
- Homepage: https://paperclip.ing
- Docker 文档: https://github.com/paperclipai/paperclip/blob/master/doc/DOCKER.md
- License: MIT
