---
name: lazycat-migrate
description: 将 Docker 镜像、GitHub 开源项目或 docker-compose 服务移植到懒猫微服（LazyCat），并产出可运行的 `lzc-manifest.yml`、`lzc-build.yml`、README、图标与自动更新工作流。适用于用户提到 LazyCat、懒猫微服、应用商店上架、`lzc-manifest.yml`、`lzc-build.yml`、镜像迁移、容器移植、自动跟踪上游版本等场景。
---

# LazyCat App Migration

把现有容器应用移植到懒猫微服，并按固定 SOP 完成“上游研判 -> 注册/建骨架 -> 预检 -> 构建 -> 下载 `.lpk` -> 安装验收 -> 复盘回写”闭环。关键动作优先使用仓库内脚本；不要把决定成败的步骤只写成自然语言。

## 激活时机

- 用户要把 Docker 镜像、Compose 项目或 GitHub 项目移植到 LazyCat
- 用户要生成、修正或补全 `lzc-manifest.yml`、`lzc-build.yml`、README、workflow
- 用户要创建 LazyCat 移植仓库、接入当前仓库已集成的构建链路、构建 `.lpk`、安装验收
- 用户要修复“已发布 / 已上架 / 已交付审核”的 LazyCat 包

## 不可争议的默认规则

1. 所有 GitHub CLI 操作默认使用 `CodeEagle` 账号；先执行 `gh auth switch -u CodeEagle`，再执行任何 `gh` 命令。
2. 需要调用 GitHub API、触发 workflow 或下载 release 前，必须先确认可用的 `GH_TOKEN`；只有确实要创建独立仓库时，才把“建仓”作为必经步骤。
3. 默认以 `CodeEagle/lzcat-apps` monorepo 为单一事实来源推进；除非用户明确要求独立仓库，或当前正式构建链路明确依赖 `CodeEagle/<app>` 目标仓库，否则不要新建独立仓库。
4. 只有在确实需要独立仓库时，目标仓库默认使用上游仓库名并创建在 `CodeEagle` 下；除非用户明确指定别名或 owner，否则不要改名或换 owner。
5. 能脚本化的动作必须优先脚本化；只有脚本无法覆盖的内容才用手工编辑。
6. 移植不是”分析任务”；默认要持续推进到可验证产物，而不是停在建议层。
7. 同一步失败时，留在原步骤排查；不允许跳步掩盖问题。
8. 默认先用 `scripts/full_migrate.py <upstream>` 从 0 到 1 跑完整移植链路；只有脚本暴露问题后，才转入针对性排查和手工修复。
9. 修复过程中只要发现跨项目可复用的推断、生成、预检、构建、打包或验收改进，必须优先沉淀回 `scripts/full_migrate.py`（以及它直接调用的共享脚本），让下次可以直接运行 `full_migrate.py` 完成同类移植；不要只把通用修复写成一次性手工步骤。
10. 只有跨项目可复用的流程约束或判断口径，才允许回写到这个 skill；具体自动化能力优先回写到 `full_migrate.py`。
11. 所有移植应用统一管理在 `CodeEagle/lzcat-apps` monorepo；新建 app 时必须同步：在 `apps/<appname>/`（全小写）放置应用文件，在 `registry/repos/<appname>.json` 创建构建配置，并追加到 `registry/repos/index.json`。这一步本身就足以完成大多数新项目接入，不得顺手再创建一个未被链路使用的空仓库。
12. 安装启动成功不是最终验收；必须使用 Browser Use 打开真实 LazyCat 访问地址，按功能矩阵逐项点击、提交、刷新、查看控制台/网络错误，并把验收结论写入迁移状态或最终汇报。
13. 用户要求上架或提交懒猫商店时，必须在 Browser Use 验收通过后生成真实运行截图，再执行商店创建/提交流程；截图必须来自已安装的真实实例，不得使用未运行的设计稿或静态占位图。
14. 所有新移植必须在独立分支上推进，分支名建议 `migrate/<slug>` 或 `feat/<slug>`；只有商店上架完成（或用户明确同意提前合并）后才能合并回 `main`。`main` 不接受未上架的半成品移植。
15. 所有构建（Docker build、镜像推送、`.lpk` 打包、安装验证准备）必须通过 GitHub Workflow 完成，不允许在本地执行 `./scripts/local_build.sh` 或等价命令进行正式构建。开发期触发方式：`gh workflow run trigger-build.yml -f target_repo=<slug> -f force_build=true -r <branch>`。
16. 触发构建后必须实时监听运行结果（`gh run watch <run-id>` 或轮询 `gh run view`）；失败时获取日志、定位错误、提交修复 commit、再次触发，循环直至成功。不允许把失败 run 交给后续步骤承担，也不允许靠"本地能 build"绕开 workflow 失败。

## 必收集信息

开始前必须确认或推断这些字段：

- `PROJECT_NAME`
- `PROJECT_SLUG`
- `UPSTREAM_REPO`
- `UPSTREAM_URL`
- `HOMEPAGE`
- `LICENSE`
- `AUTHOR`
- `VERSION`
- `IMAGE`
- `PORT`
- `DATA_PATHS`
- `ENV_VARS`
- `STARTUP_NOTES`

如果下面 5 项里缺失超过 2 项，停止推进并明确列出阻塞项：

- 是否存在可直接使用的官方镜像、可下载二进制或明确源码构建路径
- 是否能确认容器内真实监听端口
- 是否能区分数据目录、配置目录、缓存目录
- 是否知道首次启动、初始化或健康检查方式
- 是否能说明最小可运行路径：构建 -> 安装 `.lpk` -> 启动 -> 访问入口

开始写 `lzc-manifest.yml` 前，必须先产出一份“上游部署清单”，至少覆盖：

- Dockerfile / Containerfile / compose / helm / entrypoint / startup script 的真实启动入口
- DOCKER 文档、部署文档、`.env.example` / sample config 中声明的环境变量
- 数据目录、配置目录、缓存目录、上传目录、日志目录、临时目录的真实读写路径
- 首次启动初始化命令、迁移命令、建库建表命令、管理员初始化命令
- 数据库、Redis、对象存储、鉴权 / auth / secret / callback / JWT / OAuth 等外部依赖配置
- 对每个扫描到的真实目录，记录”是否应预创建、由谁创建、以什么 owner / group / mode 创建”
- 登录机制：应用是否需要登录？是否支持 OIDC/OAuth2？账号密码是固定默认值还是用户首次创建？是否存在改密流程？据此确定免密登录路线（OIDC / simple-inject-password / 三阶段 inject）

只有先拿到这份完整清单，才允许回头填写或修改 `lzc-manifest.yml`；禁止边猜边写 manifest。

## 固定脚本入口

### 主入口（monorepo `scripts/` 目录）

- `python3 scripts/full_migrate.py <upstream> [--repo-root <monorepo-path>] [--force] [--no-build] [--build-mode auto|build|install|reinstall|validate-only] [--resume] [--resume-from N] [--verify]`
  全量 10 步 SOP 自动化入口。每步产出写入 `apps/<slug>/.migration-state.json`。`--resume` 从最后完成步骤继续，`--resume-from N` 从第 N 步开始，`--verify` 从零复现验证，`--force` 忽略已有状态全量重跑。
- `python3 scripts/run_build.py <app-name> [--config-root ...] [--app-root ...] [--lzcat-apps-root ...] [--lpk-output ...] [--dry-run] [--force-build] [--skip-docker]`
  单次构建执行器（版本探测、Docker build、镜像推送、打包、发布）。
- `python3 scripts/bootstrap_migration.py --slug <name> --project-name "Name" --upstream-repo owner/repo --build-strategy official_image --service-port 8080`
  骨架生成器，也是 `full_migrate.py` 的内部依赖（`import bootstrap_migration as bm`）。
- `./scripts/local_build.sh <app-name> [--install] [--force-build] [--no-dry-run]`
  仅用于本地排错快速验证 Dockerfile 语法或 manifest 渲染；**不得用作正式构建链路**。正式构建一律走 `gh workflow run trigger-build.yml`。

### 辅助脚本（skill `scripts/` 目录，独立使用）

- `skills/lazycat-migrate/scripts/ensure-github-repo.sh --upstream-repo owner/name [--repo-owner CodeEagle]`
  仅在正式链路依赖独立仓库时使用。
- `skills/lazycat-migrate/scripts/install-and-verify.sh --package path/to/app.lpk --app-id <app_id>`
  独立安装验证，含 socat bridge 设备桥接处理。

### CI 辅助（monorepo `scripts/` 目录）

- `collect_targets.py` — GitHub Actions 矩阵生成
- `sync_trigger_build_options.py` — workflow 选项同步

规则：

- 新移植默认先执行 `scripts/full_migrate.py`；不要先手工创建骨架、手工填 manifest，再把脚本当作事后校验器。
- `ensure-github-repo.sh` 会先确保 `gh auth switch -u CodeEagle`
- 只有在确认当前正式链路需要独立仓库时，才调用 `ensure-github-repo.sh`
- 需要 GitHub 自动化时必须确认 `GH_TOKEN` 已配置；未配置时，不进入建仓、workflow 触发或 release 下载步骤
- 未传 `--repo-name` 时，仓库名默认等于上游仓库名
- `full_migrate.py` 失败时不要绕开脚本另起一套流程；应先定位失败阶段，完成修复后重跑同一入口。若修复具有通用性，先更新 `full_migrate.py` 再重跑验证。
- 所有脚本统一维护在 monorepo 内（`scripts/` 放 Python 主脚本，`skills/lazycat-migrate/scripts/` 放辅助 shell 工具），不再跨仓库引用。

补充规则：

- 如果当前 `CodeEagle/lzcat-apps` monorepo 或目标仓库已经集成了构建 / 触发 / 镜像状态回写链路，优先复用现有链路，不要额外创建 `lzcat-trigger`、`lzcat-registry` 一类辅助配置分支
- 如果 monorepo 已经能直接承载 app 目录、registry 配置、workflow 触发与镜像状态回写，就把 monorepo 视为唯一目标仓库；不要再额外创建 `CodeEagle/<app>` 镜像仓、配置仓或空壳仓库

## 可选转换器（docker2lzc）

`docker2lzc` 可作为 Compose 项目的“初稿生成器”，但不能替代本 skill 的 10 步 SOP。

- 适用范围：仅在上游是 `docker-compose.yml` 且需要快速起草 manifest/路由/挂载时使用
- 产物定位：把它生成的结果视为草稿，必须回归当前仓库标准文件与流程
- 禁止替代：不能跳过 `[7/10]` 预检、正式构建、`.lpk` 下载核对、安装验收
- 镜像约束：如果工具输出仍指向 `ghcr.io` / `docker.io` / `quay.io`，必须改为 `registry.lazycat.cloud/...` 后再进入构建
- 版本约束：工具生成版本若不满足纯 semver `X.Y.Z`，必须回改
- 打包约束：不要直接交付工具生成的 `.lpk`；最终交付包必须来自本仓库 workflow 与验收链路

如果用户反馈的是已发布应用故障，先额外读取 [references/repair-and-acceptance-sop.md](references/repair-and-acceptance-sop.md)，按“先复现 release 包，再覆盖验证修复包”的顺序处理。

## 固定 10 步 SOP

激活本 skill 后，默认按固定 10 步推进。过程汇报必须使用 `[当前步/10]`。

默认执行方式：先以 `scripts/full_migrate.py <upstream>` 跑通 10 步自动链路；脚本失败时，以失败阶段为当前步骤继续排查、修复并重跑。只有当脚本能力暂时缺口无法在本轮补齐时，才允许手工推进该步骤，但必须记录为什么不能回写到 `full_migrate.py`。

1. `[1/10]` 收集上游信息：先一次性扫清 Dockerfile、DOCKER 文档、环境变量、数据目录、初始化命令、数据库与 auth 配置，再确认入口服务、端口、镜像来源、挂载目录、健康检查与最小可运行路径。
2. `[2/10]` 选择移植路线：判断单容器、compose 拆分、带数据库依赖还是源码构建，并明确保留哪些服务。
3. `[3/10]` 注册目标 app 到 monorepo：先从 `origin/main` 切独立分支（建议 `migrate/<slug>`），后续所有改动只提交到该分支，待 `[S4]` 上架成功后再合并回 main。然后判断当前项目是否必须存在 `CodeEagle/<app>` 目标仓库；若不需要，则只在 `CodeEagle/lzcat-apps` 的 `registry/repos/<appname>.json` 创建构建配置并追加到 `registry/repos/index.json`。只有确认正式链路依赖独立仓库，才执行 `scripts/ensure-github-repo.sh --upstream-repo <owner/name> --repo-owner CodeEagle`。除非用户明确要求，否则不要额外创建独立配置仓、辅助 registry 分支或临时触发分支。
4. `[4/10]` 建立项目骨架：基于 `lzcat-template/` 在 monorepo 的 `lzcat-apps/apps/<appname>/`（全小写）创建目录，至少落 `README.md`、`lzc-manifest.yml`、`lzc-build.yml`、`icon.png`。只有当当前正式链路明确要求目标仓库也持有同一套文件时，才同步镜像到独立仓库。
5. `[5/10]` 编写 `lzc-manifest.yml`：一次性填完元信息、入口、服务、挂载、环境变量、本地化；服务镜像只保留占位或当前基线，不在后续 build 成功后把加速镜像回写进该文件。如果应用需要登录，必须同步配置免密登录（OIDC `oidc_redirect_path` + 环境变量 / `application.injects` + `builtin://simple-inject-password` / 三阶段 inject），并在需要时创建 `lzc-deploy-params.yml`。
6. `[6/10]` 补齐剩余文件：完成 README、`lzc-build.yml`、必要的 `content/` 和构建工作流；优先沿用当前 monorepo / 目标仓库已经集成的 workflow 结构，不要为了兼容旧链路额外复制一套过时流程。
7. `[7/10]` 运行预检：由 `full_migrate.py` 内置预检逻辑自动执行；不通过就继续修到通过。
8. `[8/10]` 触发并监听构建：通过 `gh workflow run trigger-build.yml -f target_repo=<slug> -f force_build=true -r <feature-branch>` 触发 GitHub Workflow 构建；用 `gh run watch <run-id>` 实时监听。失败时拉取日志（`gh run view <run-id> --log-failed`），定位错误，提交修复 commit 推送到同一分支，再次触发，循环到成功。**禁止以本地 `local_build.sh` 替代正式构建**。
9. `[9/10]` 下载并核对 `.lpk`：由 `full_migrate.py` 自动完成产物下载与校验。确认拿到的不是旧包、空包、错版本包。
10. `[10/10]` 安装验收并复盘：由 `full_migrate.py` 或独立执行 `scripts/install-and-verify.sh`；确认入口可达、状态健康，然后只把通用经验回写到 skill 或 reference。

## 上架扩展阶段

只有 `[10/10]` 通过后，才允许进入懒猫商店上架阶段。用户没有明确要求上架时，不默认提交商店。

1. `[S1]` 准备商店资料：核对 `icon.png`、`name`、`description`、`locales`、README、使用说明、隐私/许可证/上游链接；应用名称、描述和使用须知需要支持多语言。
2. `[S2]` Browser Use 功能验收与截图：用 Browser Use 打开已安装实例，覆盖主要导航、表单、列表、设置、导入/导出、API 或后台任务等核心路径；同时保存商店截图到 `apps/<app>/store/screenshots/`，文件名使用 `01-<scene>.png` 这类稳定顺序。
3. `[S3]` 预发布/内测：需要内测时执行 `lzc-cli appstore pre-publish dist/<app>.lpk [-G <group-id>] -c "<changelog>"`，并记录返回结果。
4. `[S4]` 创建/提交商店审核：优先执行 `lzc-cli appstore publish dist/<app>.lpk --clang <locale> -c "<changelog>"`；首次提交按 CLI / 开发者中心当前行为创建或更新商店记录。若 CLI 能力不足，再使用懒猫开发者中心页面创建/补全应用资料。提交审核属于对第三方的公开/半公开提交，必须在点击最终提交或执行 `publish` 前向用户确认。

## 每一步的退出条件

- `[1/10]` 结束前，关键信息缺口不超过 2 项，且必须已有一份覆盖入口、环境变量、真实写路径、初始化命令、数据库与 auth 配置的“上游部署清单”
- `[3/10]` 结束前，monorepo 注册必须完成；若当前正式链路依赖独立仓库，则该仓库也必须存在
- `[4/10]` 结束前，基础骨架必须存在
- `[7/10]` 失败不得进入 `[8/10]`
- `[8/10]` 失败不得进入 `[9/10]`
- `[9/10]` 没拿到 `.lpk` 不得进入 `[10/10]`
- 只有 `[10/10]` 完成且 workflow 成功、`.lpk` 安装成功、应用启动成功、入口可访问，才算移植完成
- 若用户要求“上架”“提交商店”“生成商店截图”，还必须完成上架扩展阶段；否则不能把任务汇报为已上架完成

## 标准输出模板

默认使用下面的汇报结构，不允许改成松散叙述：

```md
[当前步/10] 步骤名称

- 当前结论：一句话说明本步结果
- 当前产出：列出本步新增或确认的文件、配置、run id、包路径、日志结论
- 镜像缓存：写明本步镜像是否命中缓存（`my-images`），以及复用或新复制的结果
- 调用脚本：写明本步实际调用的脚本；如果没有，明确写“无”
- 阻塞/风险：没有就写“无”；有就写具体阻塞点
- 下一步：明确写下一个步骤编号和动作
```

失败时仍用同一模板，但必须明确失败类别属于：预检、构建、产物、安装、启动、路由中的哪一种。

每步执行完毕后，结构化数据自动写入 `apps/<slug>/.migration-state.json`。汇报格式不变，但 state 文件包含完整可机读数据，支持断点续跑（`--resume`）、问题追踪（`problems` 生命周期：open → resolved → backported）和从零复现验证（`--verify`）。

## 关键硬约束

- 用户要求“直接移植”时，默认连续完成“归纳信息 -> monorepo 注册/必要时建仓 -> 骨架 -> manifest/build/README/workflow -> 预检 -> 构建 -> 下载 -> 安装验收”，而不是只做分析。
- 用户要求“直接移植”时，默认第一动作是运行 `scripts/full_migrate.py <upstream>`；不要先从手工 SOP 开始。脚本失败后要修脚本、修生成结果或修上游适配，再重跑到同类问题可自动处理。
- `lzc-manifest.yml` 的 `version` 必须是纯 semver `X.Y.Z`；上游预发布版本拆成 `source_version` 与 `build_version`，不要原样塞进 `version`。
- `application.upstreams[].backend` 必须指向真实服务名和容器内端口，不能写宿主映射端口。
- 打包前，`services.*.image` 必须全部从独立镜像状态 JSON（当前约定为 `apps/<app>/.lazycat-images.json`）渲染成 `registry.lazycat.cloud/...`；最终打包 manifest 里不能保留 `ghcr.io`、`docker.io`、`quay.io`。
- 所有服务镜像都必须先通过 `lzc-cli appstore copy-image` 获取 LazyCat 加速地址后写入独立镜像状态 JSON，再由打包阶段生成临时 manifest；这条对主镜像和依赖镜像同样强制，禁止只处理主镜像，也禁止 build 成功后把加速镜像回写进仓库内的 `lzc-manifest.yml`。
- 执行 `copy-image` 前必须先检查镜像缓存（如 `lzc-cli appstore my-images` 或等价缓存查询）；命中同 tag 时优先复用缓存地址，未命中再复制。
- 供 `lzc-cli appstore copy-image` 拉取的源镜像必须可被 LazyCat 侧直接拉取；如果源镜像放在 `ghcr.io` 等私有 registry，必须先确认 package 是 `public`，不能假设 workflow 内的 `docker login` 会传递给 LazyCat 侧复制链路。
- 新建的 GHCR package 默认按 GitHub 规则往往是 `private`；只要构建链路后续要交给 LazyCat `copy-image` 回源拉取，就必须在 workflow 内加入“匿名 pull 预检”并在失败时直接中断，不能等到 `copy-image` 阶段才暴露问题。
- 开发期只要是为了验证修复而重跑构建，默认使用 `force build`；不要依赖版本探测、缓存命中或“上游版本未变化”来赌新补丁会自动进入产物。
- `lzc-manifest.yml` 是结构化配置；构建链路不得把构建得到的镜像地址直接提交回该文件。需要为打包渲染单个服务镜像时，只能精确改临时 manifest 的目标字段，例如仅修改 `services.<service>.image`，禁止用宽泛 `sed` / 正则全局替换 `image:` 行。
- 默认主流程以当前仓库已经集成的构建链路为准；如果 monorepo 或目标仓库已内建完整流程，就直接沿用，不要再人为拆回旧的外部触发器模式。
- 如果 monorepo 已经提供 app 目录、registry 配置、构建入口和产物分发能力，禁止因为 SOP 里写了“建仓”就额外创建 `CodeEagle/<app>`；必须先证明那个仓库是当前正式链路的必需品。
- 触发构建时优先使用当前仓库定义的正式入口；不要为了兼容旧习惯，额外引入 `lzcat-trigger`、独立 config repo 或临时辅助分支。
- 自建主镜像的 tag 只能使用 commit SHA（完整或短 SHA），禁止使用 `VERSION`、`source_version` 或其他版本号作为 tag；否则 registry 侧可能命中旧缓存，导致镜像内容未更新但 tag 看起来已变化。
- 如果目标仓库自带构建 workflow 但权限或凭据异常，优先修当前仓库的正式链路本身；不要默认绕到额外的外部触发器或新建配置分支。
- 新建项目时，先确认 `GH_TOKEN` 已配置，再创建仓库、配置 workflow 或调用 GitHub API。
- 如果某个服务已经定义 `command`，不要再叠加 `setup_script`，除非已确认安装器支持。
- 不要使用保留或高风险服务名，例如 `app`。
- `icon.png` 不得超过 200KB；建议使用 512x512 像素的 PNG 图片。
- 如果运行逻辑引用 `/lzcapp/pkg/content/...`，`lzc-build.yml` 必须声明 `contentdir: ./content`。
- 任何具备通用性的临时 shell，最终都应沉淀到 `scripts/` 或 reference。
- 安装验收时，`lzc-cli app status = Installed` 不是通过标准；必须继续核对 `lzc-docker-compose ps -a`、真实入口响应，以及需要时容器内接口调用。
- Browser Use 验收是 `[10/10]` 的默认组成部分：必须打开真实 `https://<subdomain>.<box>.heiyu.space` 或等价 LazyCat URL，逐项验证主要功能，检查 console error、network failure、页面空白/遮挡/跳转异常；仅有 Tailwind CDN 之类非阻断 warning 时可记录为非阻断风险。
- Browser Use 验收不得只看首页。必须先根据应用类型列出功能矩阵：导航/标签页、增删改查、登录/免密、文件上传下载、后台任务、API endpoint、设置保存、移动端或窄屏布局；不适用项写明原因。
- 生成商店截图时，必须使用真实安装实例和 Browser Use 截图；截图应覆盖首屏价值、核心工作流、设置/管理页、移动或窄屏适配（如适用），并避免暴露 token、邮箱、手机号、真实用户数据等敏感信息。
- 商店提交前必须确认 `.lpk` 内最终 `manifest.yml` 镜像均为 `registry.lazycat.cloud/...`，并已按懒猫官方上架指南补齐 logo、名称、描述、截图、安装加载、免密登录等审核重点。
- 对任何会写文件的应用，必须在 `[1/10]` 明确列出“谁在什么用户下写哪些目录”，并在 `[5/10]` 把这些真实写路径全部映射到可写挂载或显式兼容层；不能把目录权限问题留到安装后再碰运气。
- 扫描到的真实目录，只要启动链路、初始化逻辑或应用运行时会访问，就默认在启动前或初始化阶段先创建；不要把“目录不存在”留给应用自己首次失败后再补。
- 如果上游镜像默认以非 root 用户运行，禁止只靠 `mkdir -p` 侥幸修权限；必须同步确认目录 owner / group / chmod、挂载目标路径、初始化创建时机，以及是否需要在启动命令前补 `install -d`、`chown`、软链或路径迁移。
- 对 GPU-first / ML 推理项目，必须在 `[1/10]` 先判断“CPU Docker 运行是否会显著降级”，再判断“是否更适合走 LazyCat AIPod / AI 应用路线”。若存在大量硬编码 `cuda`、`pin_memory`、可选加速依赖或质量高度依赖 refinement / multimodal / upscaler，不要直接把结论写成“完全不适合 LazyCat”；应先评估是否改为“微服前端 + `ai-pod-service` 算力舱服务 + API/路由中转”的部署方式。只有在 CPU 路线不可接受、AIPod 路线也缺少可行入口或运维边界不清时，才下“不适合继续迁移”的结论。
- 对需要严格遵循上游拓扑的项目，优先复用官方 healthcheck、服务拆分和入口定义；不要用看起来能跑的简化版替代上游运行方式。
- 对一打开就要求登录的应用，必须在 `[1/10]` 判断登录机制，并在 `[5/10]` 配置免密登录支持（[上架审核要求](https://developer.lazycat.cloud/store-submission-guide.html#_8-免密登录支持)）。三种实现路线按优先级：
  1. **OIDC 标准登录流**（优先）：上游支持 OIDC/OAuth2 时，在 `lzc-manifest.yml` 设置 `application.oidc_redirect_path`，并通过部署时环境变量 `${LAZYCAT_AUTH_OIDC_CLIENT_ID}` 等注入凭据（详见 [对接 OIDC](https://developer.lazycat.cloud/advanced-oidc.html)）。
  2. **部署参数 + `builtin://simple-inject-password`**（简单场景）：账号固定或由部署参数提供时，在 `lzc-deploy-params.yml` 定义 `login_user`（type: string）和 `login_password`（type: secret, default: `$random(len=20)`），在 manifest 的 `application.injects` 中用 `builtin://simple-inject-password` 在登录页自动填充。
  3. **三阶段 inject 联动**（高级场景）：首次由用户创建账号且后续可能改密时，用 request 阶段捕获候选凭据到 `ctx.flow`、response 阶段确认成功后提交到 `ctx.persist`、browser 阶段从 `ctx.persist` 自动填充（详见 [免密登录](https://developer.lazycat.cloud/advanced-inject-passwordless-login.html)）。
  - 判断依据：上游是否有 OIDC 支持 → 账号是否可固定/可随机生成 → 是否需要学习用户后续改密。
  - 禁止跳过：不能把"需要手动输入账号密码"留给用户；安装验收时必须确认首次打开无需手工登录。

## 本轮新增经验

- Airflow 这类基础设施项目，入口和健康检查必须优先以官方 compose / 文档为准；错误的 worker hostname 展开、后台 job 探针或缺失初始化步骤，会让 Web UI 表面可起但应用整体仍判失败。
- OpenFang 这类编译型项目，若上游 release binary 依赖的 `glibc` 高于 LazyCat 运行时，优先改为在与运行时同代的基础镜像里源码构建，不要继续追二进制兼容。
- Edit-Banana 这类 GPU-first AI 项目，先确认“功能可跑”和“质量可接受”是两件事。即使 CPU 兼容补丁能把服务跑起来，也可能因关闭 refinement、RMBG、upscale、multimodal OCR 而与官网质量明显不一致。
- GPU-first 项目若在 CPU / Docker 路线下质量或性能明显不可接受，不应止步于“放弃 LazyCat”；要继续判断是否改走算力舱 AIPod。根据 LazyCat 开发者文档，AI 应用可在 `lzc-build.yml` 中声明 `ai-pod-service`，把 GPU 服务部署到算力舱，微服侧再通过 API 或 LZC 路由中转访问；算力舱中的 docker 默认使用 `nvidia-runtime`，适合承载这类 GPU 服务。
- 对 release-first 项目，下载 `.lpk` 后要直接解包检查内部 `manifest.yml`；仓库内 `lzc-manifest.yml` 正确，不代表 release 包里的最终 manifest 没被 workflow 改坏。
- 对多服务项目，release 包解包检查时必须逐个核对 `services.*.image`，尤其要确认依赖服务镜像没有被主应用镜像覆盖。
- 安装验收中如果 `app log` 返回 `not yet realized`，默认表示仍在安装/拉镜像阶段，不应立即判失败；应先轮询 `app status` 与 `app log`，超时或出现明确错误再进入故障分流。
- 对仓库自建镜像，若 workflow 用版本号反复推送同一个 tag，LazyCat 侧可能继续复用旧层缓存；因此自建镜像 tag 必须绑定 commit SHA，版本号只用于 manifest/version、release 元数据或展示，不用于镜像 tag。
- 如果在 ARM 开发机上本地验收 `linux/amd64` 自建镜像，优先让构建链支持 `docker buildx build --load --platform linux/amd64`，并在 Dockerfile 中区分 `BUILDPLATFORM` 与 `TARGETPLATFORM`；不要把所有 `FROM` 都硬编码成 `linux/amd64`，否则容易遇到跨 stage 平台不匹配、legacy builder 失败或 qemu 编译崩溃。
- 对 GHCR 这类可私有化的镜像仓库，workflow 本机能 `push` 不代表 LazyCat 后续能 `copy-image`；只要构建链路依赖 LazyCat 去回源拉取，就必须把对应 package 设为 `public`，否则会在复制阶段报 `UNAUTHORIZED`。
- 对 GHCR 新包，不能依赖“之前公开过一次同名包”的记忆来判断后续所有包都可匿名拉取；只要是会被 LazyCat 回源的 tag，都应该在 workflow 里先做一次匿名拉取预检，失败就立即报 package visibility/pull access 问题。
- 开发期修 bug 时，如果目标是验证“刚改的补丁是否进入新镜像 / 新 `.lpk`”，默认用 `force build` 重跑整条链路；否则很容易因为版本未变、镜像 tag 复用或缓存命中而误判修复已生效。
- 遇到“创建目录没权限”，默认不要先加大权限或改成 root 兜底；先回溯上游真实写路径、容器运行用户、挂载目标和初始化时机，再决定是补挂载、预创建目录、修 owner，还是用软链兼容历史路径。
- 扫描清单里确认会被访问但当前镜像或挂载目标中不存在的目录，默认都要预创建；目录创建属于 manifest / 启动链路设计的一部分，不算运行后临时补救。
- 对需要运行初始化命令（如 `onboard`、`bootstrap-ceo` 等）的应用，必须在 `setup_script` 中完成初始化和首次启动命令，而不是依赖 `bootstrap-ui` 或其他依赖服务来运行主服务的初始化逻辑；如果 `setup_script` 只创建目录而不运行初始化，会导致应用首次安装后无法自动完成引导流程。
- 如果 monorepo 已经内建构建与分发链路，skill 必须以 monorepo 为单一事实来源推进；不要再额外创建 `lzcat-registry` / `lzcat-trigger` 风格的辅助分支去“适配”旧流程。
- 如果 workflow 构建成功并完成 `copy-image`，只允许把服务名到加速镜像地址的映射写回 `.lazycat-images.json` 这类独立状态文件；仓库里的 `lzc-manifest.yml` 应保持人工维护的拓扑配置，打包时再用 JSON 渲染临时 manifest，避免自动构建频繁制造 manifest 冲突。
- 移植过程中遇到的通用缺口（例如上游识别、端口推断、compose 服务筛选、依赖镜像处理、目录预创建、版本规范化、preflight 规则、打包前 manifest 渲染）优先修进 `scripts/full_migrate.py`；最终目标是同类上游只需要直接运行 `full_migrate.py` 即可完成移植。
- 如果 SOP 的历史步骤与当前仓库现实相冲突，优先服从当前仓库的正式链路；不能为了“补齐步骤”创建一个实际上无人使用的独立仓库。
- 如果新 app 的 `registry/repos/<appname>.json` 没有同步追加到 `registry/repos/index.json`，workflow 的 target 收集阶段会直接报 `Config not found for app`；因此注册 app 时，`repos/<appname>.json` 与 `index.json` 必须视为同一步的原子更新。
- 如果 `setup_script` 运行在 `/bin/sh`，默认不要写 `set -o pipefail` 或依赖 bash-only 语义；安装验收里一旦出现平台错误页，要先检查 setup script 是否在最前几行就被 shell 选项绊倒。
- 对首启初始化脚本里的“目录为空则生成文件”逻辑，禁止写成仅依赖 pipeline 退出码的 `find ... | head ...` 判空；必须使用能真实检测输出内容的写法，例如 `find ... -print -quit | grep -q .` 或等价方案，否则目录为空时也可能误判为“已有文件”。
- 对带 owner setup / 首次管理员初始化的项目，不要仅凭 `OWNER_SETUP_ENABLED=yes`、`BLOCK_SIGNUP=yes` 之类环境变量就断言“入口一定会跳 `/setup`”或“存在默认账号”；安装验收时必须结合持久化数据状态一起判断，例如检查 `/auth/config`、数据库里是否已存在 account / organization，再决定是首次初始化、普通登录，还是密码重置场景。
- LazyCat 设备的 debug.bridge SSH 入口默认不是普通 shell；排障时不要直接假设 `ssh box@... ls/cat/docker ...` 可用。应优先使用 `lzc-docker`、`resume`、`status`、`devshell` 等 bridge 子命令；若需要进入容器交互排障，默认使用带 TTY 的方式（如 `ssh -tt ... 'devshell <pkgId> --uid <uid> sh'` 或 `lzc-docker exec -it ...`）。

## 按需加载的 reference

- 文件填写与骨架规则：见 [references/file-authoring.md](references/file-authoring.md)
- Compose 初稿生成与回归规范：见 [references/docker2lzc-integration.md](references/docker2lzc-integration.md)
- 构建、下载、安装与验收闭环：见 [references/workflow-and-validation.md](references/workflow-and-validation.md)
- 失败分流与常见报错：见 [references/failure-playbook.md](references/failure-playbook.md)
- GPU-first / AI 推理项目适配边界：见 [references/gpu-first-apps.md](references/gpu-first-apps.md)
- LazyCat 算力舱 / AI 应用总入口：见 [https://developer.lazycat.cloud/aipod/](https://developer.lazycat.cloud/aipod/)
- LazyCat AI 应用规范（`ai-pod-service`）：见 [https://developer.lazycat.cloud/aipod/package/spec.html](https://developer.lazycat.cloud/aipod/package/spec.html)
- LazyCat LZC 路由中转 AI 服务：见 [https://developer.lazycat.cloud/aipod/issues/lzc-app-forward-to-ai-service.html](https://developer.lazycat.cloud/aipod/issues/lzc-app-forward-to-ai-service.html)
- 已发布应用的修复 / 复现 / 覆盖验收 SOP：见 [references/repair-and-acceptance-sop.md](references/repair-and-acceptance-sop.md)
- 历史案例与开发者站链接：见 [references/examples-and-docs.md](references/examples-and-docs.md)

## 交付标准

完成一次移植时，至少保证：

- 目录结构基于模板
- monorepo 中的 app 目录与 registry 注册已完成；若当前正式链路依赖独立仓库，则该仓库也已创建且名称符合“上游仓库名”
- `lzc-manifest.yml` 字段完整、端口正确，构建后的真实镜像地址由独立镜像状态 JSON 管理并在打包阶段正确渲染
- `lzc-build.yml` 可直接构建
- README 说明访问方式、环境变量、数据目录和上游链接
- 数据目录已正确持久化
- 若有自动发布需求，workflow 与仓库既有模式一致
- workflow 成功、`.lpk` 安装成功、应用启动成功
- Browser Use 功能矩阵验收通过，且关键页面无阻断 console error / network failure
- 如用户要求上架，已生成 `apps/<app>/store/screenshots/` 截图、准备 changelog，并完成 `lzc-cli appstore pre-publish` 或 `publish` / 开发者中心创建提交
- 本轮通用自动化改进已回写到 `scripts/full_migrate.py` 或其共享脚本；只有流程性约束才回写到 skill 或 reference
- 当前完成移植的项目已追加到 [references/examples-and-docs.md](references/examples-and-docs.md) 的“历史移植先例”
- 移植工作分支已合并回 `main`（合并仅在商店上架完成后执行；上架前分支独立维护，不污染 main）

## 复盘回写规则

- 只有满足“跨项目可复用、能提升后续移植成功率、与单个上游实现无强绑定”的流程结论，才回写到 skill。
- 可自动化的通用修复不要只写进 skill；优先改 `scripts/full_migrate.py`，使后续同类应用可以直接运行脚本完成迁移。
- 只对单个项目、单个版本或单条业务链成立的问题，归类为项目个案，不直接写进 skill 主体。
- 复盘优先提炼检查方法、分流思路、验收口径和流程约束，不照搬单次故障现象。
- 只要本轮移植完成，就把当前项目追加到 [references/examples-and-docs.md](references/examples-and-docs.md) 的“历史移植先例”。
