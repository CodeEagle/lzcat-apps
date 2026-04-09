# 案例与文档索引

这份 reference 只在需要对照实现或查看平台规范时读取。

## 1. 仓库内优先参考

- `lzcat-template/README.md`
- `lzcat-template/lzc-manifest.yml`
- `chatgpt-on-wechat-lazycat/lzc-manifest.yml`
- `lzcat-higress/lzc-manifest.yml`
- `CodeEagle/lzcat-apps` monorepo 中的 `scripts/full_migrate.py`、`scripts/run_build.py`、`scripts/bootstrap_migration.py`
- `skills/lazycat-migrate/scripts/install-and-verify.sh`
- `skills/lazycat-migrate/scripts/ensure-github-repo.sh`

## 2. 历史移植先例

- 规则：每次移植成功后，都要把当前项目追加到这里，作为后续移植参考
- `https://github.com/CodeEagle/OpenFang`
- `https://github.com/CodeEagle/waoowaoo`
- `https://github.com/CodeEagle/Moltis`
- `https://github.com/CodeEagle/cutia`
- `https://github.com/CodeEagle/chatgpt-on-wechat-lazycat`
- `https://github.com/CodeEagle/cmms`
- `https://github.com/CodeEagle/paperclip`
- `https://github.com/CodeEagle/lzcat-apps/tree/main/apps/shadmin`
- `https://github.com/CodeEagle/lzcat-apps/tree/main/apps/pandawiki`
- `https://github.com/CodeEagle/lzcat-apps/tree/main/apps/superplane`
- `https://github.com/CodeEagle/lzcat-apps/tree/main/apps/omniroute`
- `https://github.com/CodeEagle/lzcat-apps/tree/main/apps/storayboat-tts-gateway`

查找建议：

- 多服务、数据库/缓存依赖、镜像替换问题：先看 `cutia`
- AI Web 应用、环境变量较多、配置初始化问题：先看 `chatgpt-on-wechat-lazycat`
- 无官方镜像、二进制构建、特殊启动方式问题：先看 `OpenFang`、`waoowaoo`、`Moltis`
- 多 upstream 路由、前后端分离、对象存储与数据库依赖同时存在的问题：先看 `cmms`
- 已发布包可打开首页但注册、登录或 `/api` 请求异常的问题：先看 `cmms`
- # 需要 `setup_script` 运行初始化命令（如 `onboard`、`bootstrap-ceo`）的应用：先看 `paperclip`
- ARM 开发机本地验 `amd64` 自建镜像、GHCR pull 权限与 monorepo buildx 支持问题：先看 `shadmin`
- 官方安装器隐藏真实 compose、需要从安装脚本反查完整依赖拓扑、并核对 release 包内最终 manifest 的多服务项目：先看 `pandawiki`
- 官方镜像可直接复用、但首启初始化脚本和 OIDC key 生成需要在 LazyCat `setup_script` 中补齐或修正的项目：先看 `superplane`

- Next.js 16 standalone、自建镜像、instrumentation hook 与 `app log` 可见性偏差的问题：先看 `omniroute`
- 轻量级 Python API 网关、无状态单服务、上游无 Dockerfile 且 `commit_sha` 驱动版本检查的问题：先看 `storayboat-tts-gateway`

## 3. 懒猫开发者站高频入口

- 首页 / 导航：`https://developer.lazycat.cloud/`
- 端口迁移 / 应用移植：`https://developer.lazycat.cloud/app-example-porting.html`
- `lzc-manifest.yml` 规范：`https://developer.lazycat.cloud/spec/manifest.html`
- `manifest.yml` 渲染：`https://developer.lazycat.cloud/advanced-manifest-render.html`
- 发布应用：`https://developer.lazycat.cloud/publish-app.html`
- 开发常见问题：`https://developer.lazycat.cloud/faq-dev.html`
- 高级路由：`https://developer.lazycat.cloud/advanced-route.html`
- 文件与持久化：`https://developer.lazycat.cloud/advanced-file.html`
- 公共 API：`https://developer.lazycat.cloud/advanced-public-api.html`
- 多实例：`https://developer.lazycat.cloud/advanced-multi-instance.html`
- 次级域名：`https://developer.lazycat.cloud/advanced-secondary-domains.html`
- Dockerd 支持：`https://developer.lazycat.cloud/dockerd-support.html`
- SSH 调试：`https://developer.lazycat.cloud/ssh.html`
- 开发环境 / `lzc-cli`：`https://developer.lazycat.cloud/en/lzc-cli.html`

查找建议：

- manifest 报错：先看 `spec/manifest.html` 与 `advanced-manifest-render.html`
- 上架 / 构建 / 镜像问题：先看 `publish-app.html` 与 `faq-dev.html`
- 路由、子域名、对外暴露异常：先看 `advanced-route.html` 与 `advanced-secondary-domains.html`
- 数据目录、挂载、文件读写问题：先看 `advanced-file.html`
- 调试环境问题：先看 `ssh.html`、`dockerd-support.html`、`en/lzc-cli.html`
