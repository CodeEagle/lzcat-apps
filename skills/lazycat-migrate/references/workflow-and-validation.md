# 构建与验收闭环

用于 `[7/10]` 到 `[10/10]`。当骨架与文件已经成型，再读取这份 reference。

## 1. 预检
- 执行：由 `full_migrate.py` 内置预检逻辑自动完成
- 目标：在进 CI 之前消灭 manifest、build、README 的结构性问题
- 预检失败时，停留在 `[7/10]` 修复；不要直接进入构建

当前脚本已覆盖这些检查：
- `package`、`version`、`name`、`application`、`services` 是否存在
- `backend` 是否指向真实服务名和端口
- `version` 是否为纯 semver
- `lzc-build.yml` 是否引用 `./lzc-manifest.yml`
- 最终镜像是否已切到 `registry.lazycat.cloud/...`
- 是否还残留上游镜像源、模板占位符、`TODO:`
- 引用 `/lzcapp/pkg/content/...` 时是否声明了 `contentdir`

## 1.5 新仓库必须配置的 Secrets

在新 GitHub 仓库（如 `CodeEagle/lzcat-apps`）触发构建前，必须先配置以下 Secrets：

| Secret | 必要性 | 获取方式 |
|--------|--------|---------|
| `GH_TOKEN` | 必须 | `gh auth token`（本地 CodeEagle 账号） |
| `LZC_CLI_TOKEN` | 必须 | `~/.config/lzc-client-desktop/core.cfg` 中的 `LZC_MISC_AUTH_TOKEN` 字段 |
| `GHCR_TOKEN` | 镜像为私有时才需要 | GHCR PAT（public 镜像不需要） |
| `GHCR_USERNAME` | 镜像为私有时才需要 | GHCR 用户名（public 镜像不需要） |

```bash
# 设置必要 Secrets
gh auth switch -u CodeEagle
echo "$(gh auth token)" | gh secret set GH_TOKEN --repo CodeEagle/<repo>
LZC_TOKEN=$(python3 -c "import json; print(json.load(open('$HOME/.config/lzc-client-desktop/core.cfg'))['extra_headers']['LZC_MISC_AUTH_TOKEN'])")
echo "$LZC_TOKEN" | gh secret set LZC_CLI_TOKEN --repo CodeEagle/<repo>
```

## 2. 触发构建
- 执行：优先使用当前 monorepo 或目标仓库已经集成的正式构建入口
- 构建由 `full_migrate.py` 调用 `run_build.py` 执行，或通过 monorepo `local_build.sh` 单独触发
- 脚本或 workflow 会先确保 `gh auth switch -u CodeEagle`
- 目标：走通当前项目实际使用的正式构建、镜像复制、manifest 回写与后续产包链路
- 不要为了兼容旧流程额外引入外部触发器、独立 config repo 或临时辅助分支
- 构建失败时，先看 workflow 日志，再修复和重跑

## 3. `.lpk` 下载
- 执行：由 `full_migrate.py` 自动完成产物下载与校验
- release-first 项目优先直接按 release tag 下载
- 已知 release tag 时直接显式传入

下载后必须确认：
- 本地确实拿到了 `.lpk`
- 包不是旧版本、空文件或错误 release
- 直接解包核对内部 `manifest.yml`，确认 `version`、`image`、`backend` 没被 workflow 改坏
- 多服务项目要逐个核对 `services.*.image`，不要只看主服务；依赖服务镜像被误改时，安装也可能显示成功，但运行会在容器启动阶段失败
- 已记录下载路径，方便后续安装和回溯

## 4. 安装与运行验证
- 执行：由 `full_migrate.py` 自动完成，或独立使用 `skills/lazycat-migrate/scripts/install-and-verify.sh --package path/to/app.lpk --app-id <app_id>`

必须检查：
- `lzc-cli app install` 结果
- `app status`
- `app log`
- 如果 `app log` 返回 `not yet realized`，默认判定为“仍在安装/拉镜像阶段”，先轮询等待，不要立即判失败
- `lzc-docker-compose ps -a` 是否真的出现目标 project 与服务
- 入口 HTTP 是否可达
- 需要时直接做容器内接口调用，区分“路由正常”与“业务接口正常”
- 健康检查、环境变量、挂载目录、镜像来源是否符合预期

### 4.1 Browser Use 功能完整性验收

安装启动后必须使用 Browser Use 做真实浏览器验收；`curl 200`、`app status = Installed`、首页能打开都不能单独算通过。

验收流程：

1. 打开 `lzc-cli project info --release` 输出的 `Target URL`。
2. 根据应用实际 UI/API 列出功能矩阵，至少覆盖：主导航/标签页、核心列表或看板、创建/编辑/删除或等价业务动作、设置保存、文件上传下载、API endpoint、登录/免密、移动或窄屏布局；不适用项写明原因。
3. 对每个功能点执行真实点击、输入、提交、刷新或接口调用；如果功能会产生外部副作用、删除数据、发送消息、提交表单或上传文件，先停下向用户确认。
4. 检查 Browser Use 的 console 与 network 记录：阻断性的 `error`、接口 4xx/5xx、资源加载失败、空白页、点击无响应、明显布局重叠都必须修复后重测。
5. 将验收摘要写入最终汇报，必要时保存到 `apps/<app>/.migration-state.json` 或 `apps/<app>/qa/browser-use-report.json`。

建议报告字段：

```json
{
  "target_url": "https://<app>.<box>.heiyu.space",
  "checked_at": "ISO-8601",
  "browser_use": {
    "passed": true,
    "console_errors": [],
    "network_failures": [],
    "functional_matrix": [
      {"name": "overview", "status": "pass", "evidence": "quota card rendered"}
    ]
  }
}
```

如果本机存在用户指定的 `bb-browser`，可用它作为 Browser Use 的执行前端；如果不存在，使用 Codex Browser Use 插件完成同等真实浏览器验收，并在汇报中说明。

### 4.2 商店截图生成

当用户要求上架或提交商店时，必须在 Browser Use 验收通过后生成商店截图。

截图要求：

- 截图来自真实安装实例，不能来自未运行的 mock、静态设计稿或旧版本页面。
- 默认保存到 `apps/<app>/store/screenshots/`，命名为 `01-overview.png`、`02-core-flow.png`、`03-settings.png` 等稳定顺序。
- 至少覆盖：首屏/概览、核心工作流、设置或管理页、移动/窄屏视图（如应用支持或商店需要）。
- 截图里不得暴露 token、授权码、邮箱、手机号、真实姓名、真实文件名、精确地址、密钥、付款信息等敏感数据；必要时先用测试账号/测试数据或打码后再生成。
- 截图应展示真实产品状态，避免只截登录页、空状态、错误页或纯说明页。

Browser Use 截图建议：

```js
await tab.goto(targetUrl);
await tab.playwright.waitForLoadState({ state: "networkidle", timeoutMs: 20000 }).catch(() => {});
await tab.playwright.screenshot({ path: "apps/<app>/store/screenshots/01-overview.png", fullPage: true });
```

如果 Browser Use 当前工具不支持直接写 `path`，先用工具返回的截图结果，再落盘到上述目录；最终汇报必须列出截图路径。

### 4.3 Playground 图文攻略草稿

用户要求发布攻略、教程或 Playground workshop 草稿时，攻略必须基于真实安装实例和功能验收结果，但正文不能写成测试记录或发布 checklist。

攻略应覆盖：

- 应用定位与适用人群：解释它解决什么问题，哪些用户值得安装。
- 开始前准备：列出账号、provider、示例数据、仓库、持久化目录或外部服务要求。
- 首次打开截图：只截真实产品界面，不截浏览器外框、系统桌面或启动错误页。
- 核心小任务：用可复现的最小任务跑通主流程，说明输入怎么写、何时点击、怎么判断进度。
- 执行中与结果截图：至少包含执行中状态、结果页、详情页或日志页之一；任务型 / agent 型应用必须补“执行中”和“完成结果”两类截图。
- 设置与进阶玩法：有 provider、runtime、员工、插件、Webhook、外部 API 时单独成节，写清适用场景、配置入口和小任务试跑建议。
- 使用心得：把排障经验改写成用户可执行建议，而不是贴日志或验收摘要。

公开攻略禁止出现：

- `本次功能测试记录`、`验收记录`、`Browser Use 验收证据` 这类内部小节标题
- `截图/发布攻略时要注意什么`、提交审核提醒、安全确认流程等面向操作者的提示
- API key、GitHub token、OAuth token、私有仓库 URL、真实客户任务、回调 URL、日志密钥或真实账号信息

素材路径建议：

- `apps/<app>/copywriting/assets/`：攻略正文图片，文件名按阅读顺序命名，例如 `tutorial-01-first-run.png`。
- `apps/<app>/store/screenshots/`：商店截图，文件名按商店展示顺序命名，例如 `01-overview.png`。
- `apps/<app>/copywriting/tutorial.md`：完整使用攻略。
- `apps/<app>/copywriting/playground.md`：可直接贴到 LazyCat Playground workshop 的版本。

`scripts/copywriter.py` 生成的是初稿，发布前必须人工把真实截图、demo 执行过程、结果页和心得补齐；如果生成稿含有测试记录、发布提醒或安全边界提示，必须移到内部 checklist，不得留在公开正文。

当用户要求“写攻略”“补截图”“存到草稿箱”时，按这个顺序处理，避免把执行过程或未验证结果混进文章：

1. 先完成真实实例验收，再写文章。截图必须来自可打开的应用实例、控制台或真实配置页面；没有实例时只能保留截图占位说明，不能伪造产品截图。
2. 文章源文件放在 `apps/<app>/copywriting/`，常用文件为 `store-copy.md`、`tutorial.md`、`playground.md`。截图源文件放在 `apps/<app>/copywriting/assets/`，文件名使用 `tutorial-01-login.png`、`tutorial-02-runtime.png` 这类稳定顺序。
3. 如果教程包含 Agent、Runtime、CLI 或 demo，必须区分“链路已验证”和“业务任务已完成”。例如 Runtime online、Issue 已分配、run completed 可以写成已验证；DNS、repo checkout、token、权限等阻塞必须写成阻塞，不要把 blocked run 改写成成功案例。
4. 使用测试账号、测试 workspace 和测试数据。文章、截图、日志里不得暴露 token、验证码、回调 URL 中的 JWT、邮箱、手机号、真实姓名、真实仓库私密路径、密钥或付款信息。
5. 上传到 Playground/Workshop 前，先审一遍 Markdown：删除用户给 Codex 的指令、Codex 对指令的回复、调试口吻、内部 TODO、临时占位和“我正在处理”这类过程文本。可以用 `rg -n "指令|用户要求|我会|我先|保存草稿|token|JWT|callback|验证码" apps/<app>/copywriting` 做辅助检查，但最终仍要人工通读标题、正文、图片说明和 FAQ。
6. 上传截图后，确认文章里的图片引用已经替换为平台返回的真实 URL，或确认平台编辑器已接收本地上传文件。不要只上传封面而漏掉正文截图。
7. 补齐标题、分类和封面。标题应能独立说明文章对象和收益；分类选择与教程用途匹配。封面可以用品牌图或生成图，但正文产品截图仍必须来自真实实例。
8. 在浏览器编辑器里如果滚动不到顶部或底部，先用 Browser Use 的 DOM locator、`Home`、`End`、滚轮和截图确认按钮位置；不要因为页面滚动异常就盲点保存或发布。
9. 点击“存草稿”会把标题、正文、分类、封面和上传图片写入第三方平台；点击“发布”会进入公开发布链路。两者都应在动作前向用户确认，且“发布”必须单独确认。

草稿提交前检查：

- 标题已填写，且不是占位标题。
- 正文不包含用户指令、助手回复、调试日志、密钥、验证码或未打码 token。
- 图片数量与文章中截图说明一致，图片能在编辑器中正常显示。
- 分类和封面已设置。
- 文章真实说明了 demo 的成功范围和未解决阻塞。
- 浏览器页面停在最终保存/发布动作前，已获得用户确认。

### 4.4 懒猫商店创建与提交

商店提交入口以当前 `lzc-cli` 为准；提交规则以官方文档为准：[发布自己的第一个应用](https://developer.lazycat.cloud/publish-app.html)、[应用上架审核指南](https://developer.lazycat.cloud/store-submission-guide.html)。

```bash
lzc-cli appstore login
lzc-cli appstore pre-publish dist/<app>.lpk -c "Initial LazyCat package"
lzc-cli appstore publish dist/<app>.lpk --clang zh-CN -c "Initial LazyCat package"
```

操作口径：

- `pre-publish` 用于内测；需要指定测试组时加 `-G <group-id>`。
- `publish` 用于提交商店审核；首次提交按 CLI / 开发者中心当前行为创建或更新商店侧应用记录。
- 多语言 changelog 使用 `--clangs <locale>:<file>`，例如 `--clangs zh-CN:CHANGELOG.zh-CN.md --clangs en:CHANGELOG.en.md`。
- 当前 `lzc-cli appstore publish --help` 只暴露包路径与 changelog 参数；如果 CLI 无法补齐截图、分类、详细说明等商店资料，改用懒猫开发者中心页面创建/补全；页面操作必须仍以 Browser Use 验收产物为依据。
- 执行 `publish` 或在网页点击最终提交前，必须向用户确认，因为这会把应用包、元数据和截图提交给懒猫商店审核。

提交前检查：

- `.lpk` 是最新构建产物，sha256 已记录。
- `lzc-cli project info --release` 显示当前版本已部署且运行健康。
- Browser Use 功能矩阵通过。
- `apps/<app>/store/screenshots/` 截图齐全。
- `manifest.yml` 的 logo、名称、描述、locales、免密登录、数据持久化、镜像地址符合官方上架审核指南。

建议轮询口径：
- 连续轮询 `app status` + `app log`，直到进入可观测容器状态或超过超时阈值再进入失败分流
- 仅当长时间无进展、出现明确错误日志或超时，才按安装/启动故障处理

## 5. 构建前的硬检查
- `services.*.image` 必须全部切到 `registry.lazycat.cloud/...`
- 主镜像与依赖镜像都要检查
- 主镜像和依赖镜像都必须先做缓存查询（例如 `lzc-cli appstore my-images`）；命中同 tag 时优先复用缓存地址
- 缓存未命中时，再执行 `lzc-cli appstore copy-image` 并使用返回的加速地址；不允许任何服务直接保留上游 registry 地址
- 如果源镜像位于 `ghcr.io`，在执行 `copy-image` 前必须先做“匿名 pull 预检”；预检失败时，直接按 package visibility/pull access 问题中断，不要继续把错误留给 LazyCat 侧 `copy-image`
- 对 GHCR 新建 package，默认按 private 对待，直到匿名 pull 预检明确通过为止；不要把 workflow 本机 `docker push` 成功误判为 LazyCat 也能回源拉取
- 如果 workflow 需要回写 `lzc-manifest.yml`，只能精确更新目标服务字段；禁止用宽泛正则全局替换所有包含项目名的 `image:` 行
- 如果 workflow 先产出 `ghcr.io/<owner>/<repo>:<tag>`，也必须先复制到 LazyCat registry，再回写 manifest
- 对仓库自建主镜像，`<tag>` 只能是 commit SHA；禁止用版本号反复覆盖同一 tag，否则可能因缓存命中导致 LazyCat 侧拿到旧镜像
- `lzc-manifest.yml` 的 `version` 必须是纯 `X.Y.Z`
- 健康检查命令必须与镜像内真实存在的工具一致
- 带认证中间件的应用，要确认健康检查不会被缺失 secret 直接拦死

## 6. 常见验收重点
- workflow 失败点：镜像复制、manifest 回写、`lzc-cli project build`、发布步骤
- 如果只是修 semver 或重发 release，先查缓存并复用已复制到 LazyCat 的镜像，不要重复做无意义的 `copy-image`
- 安装阶段优先看 manifest 字段、包内容、镜像地址
- 启动阶段优先看端口、环境变量、挂载目录、初始化逻辑、运行日志

## 7. 何时使用整体验证
- 骨架完整，且要从预检一路跑到安装验收时，优先用 `full_migrate.py` 一条龙跑完
- 只排查单段问题时，拆开用当前项目实际在用的构建入口（`run_build.py` / `local_build.sh`）或 `install-and-verify.sh`
