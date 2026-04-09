# 故障分流与回退规则

遇到问题时，先定位失败所在步骤，再决定查看内容、修复对象和是否回退。不要把预检、构建、产物、安装、启动、路由问题混在一起。

## 1. 失败分流矩阵

| 当前步骤 | 失败现象 | 优先查看 | 优先修复对象 | 是否回退 |
| --- | --- | --- | --- | --- |
| `[6/10]` | 预检失败 | `lzc-manifest.yml`、`lzc-build.yml`、README | 静态结构与字段缺失 | 不回退，留在 `[6/10]` |
| `[7/10]` | dispatch 失败或 run 未出现 | 目标 repo、workflow 名、dispatch inputs、Actions 权限 | workflow 输入与仓库配置 | 不回退，留在 `[7/10]` |
| `[7/10]` | workflow 运行失败 | Actions log、失败 job、镜像 tag、`copy-image`、构建步骤 | CI 配置、镜像流程、workflow 脚本 | 不回退，留在 `[7/10]` |
| `[8/10]` | 没有 `.lpk` 或下载失败 | artifacts、Release、run id、release tag | 产物上传逻辑、下载参数、版本口径 | 可回退到 `[7/10]` |
| `[9/10]` | 安装失败 | `lzc-cli app install` 输出、manifest 校验、镜像来源、包内容 | manifest、镜像地址、包构建结果 | 通常回退到 `[7/10]` |
| `[9/10]` | 启动失败 | `app status`、`app log`、环境变量、端口、挂载目录 | 启动命令、env、binds、healthcheck | 先留在 `[9/10]`，必要时回退 `[7/10]` |
| `[9/10]` | 入口不可访问 | `application.upstreams`、`backend`、`public_path`、HTTP 响应 | upstream、路由、端口、鉴权 | 先留在 `[9/10]`，必要时回退 `[7/10]` |

## 2. 回退规则
- 静态文件问题：停留在 `[4/10]`、`[5/10]`、`[6/10]`
- workflow 触发或构建问题：停留在 `[7/10]`
- `.lpk` 缺失或版本错误：回退到 `[7/10]`，然后重新执行 `[8/10]`
- 安装失败、启动失败、入口异常：
  - 只是状态确认或日志定位问题时，留在 `[9/10]`
  - 需要修改 manifest、workflow、镜像、版本并重新产包时，回退到 `[7/10]`
- 只有发现服务裁剪或架构判断错了，才允许回退到 `[2/10]`
- 非架构级错误，禁止回退到 `[1/10]`

## 3. 高频报错处理
- `manifest unknown`：优先检查目标仓库 workflow 是否真的产出了 `ghcr.io/<owner>/<repo>:<tag>`，以及上游 tag 和目标 ghcr tag 是否一致
- `copy-image` 报 `UNAUTHORIZED`，且日志里是回源拉取 `ghcr.io/<owner>/<repo>:<tag>` 失败：优先检查对应 GHCR package 是否为 `public`；不要误判为 workflow 内 `docker login` 失效。LazyCat 侧复制链路不会继承 GitHub runner 上的登录态，私有 GHCR 包即使刚成功 `push`，后续 `copy-image` 仍会失败
- `version` 不符合 semver：检查是不是把 `v0.9.0-alpha.2` 之类的上游版本直接写进 manifest 了
- release 包安装后 `Installed` 但 `lzc-docker-compose ps -a` 没有项目：先解包 `.lpk` 检查内部 `manifest.yml` 的 `version`、`image` 和 `backend`，不要只看仓库工作区文件
- 多服务应用里某个依赖容器安装后直接 `Exited 127` / `command not found`：先怀疑 release 包里的 `manifest.yml` 是否把该依赖服务的 `image` 错写成了主应用镜像；优先解包 `.lpk` 核对 `services.*.image`
- `cannot define both init and entrypoint/command`：把初始化逻辑并入单一 `command`，不要和 `setup_script` 并存
- `app log` 返回 `not yet realized`：先视为安装阶段进行中（通常在拉镜像或创建容器），先轮询 `app status` 与 `app log`；只有超时或出现明确错误再进入故障分流
- `app log` 持续返回 `not yet realized`，但 `lzc-docker-compose -p <project> ps -a` 已显示主服务与 sidecar `healthy`，且入口已稳定返回 `200`：优先按运行态验收通过处理，并记录为 `lzc-cli` 可见性问题；不要只因 `app log` 单点异常就回退重构建
- `exec format error`：优先怀疑镜像架构与目标 box 不匹配，而不是先怀疑脚本换行
- ARM 本地环境里 `docker build --platform linux/amd64` 报 stage 平台不匹配、`runtime/cgo` / `compile` 段错误、或 legacy builder 无法完成交叉构建：优先切到 `docker buildx build --load`，并让 Dockerfile 区分 `BUILDPLATFORM` / `TARGETPLATFORM`；不要把所有 stage 都硬编码成 `linux/amd64`
- PostgreSQL 容器启动前退出：优先核对挂载路径是否适配当前主版本，尤其注意 `/var/lib/postgresql` 与 `/var/lib/postgresql/data` 的差异
- 入口长期超时或系统“启动异常”页：优先检查健康检查是否误用镜像内不存在的命令，或 `/health` 是否被缺失 secret 拦住
- Web UI 能打开但应用仍被系统判异常：优先回看后台服务 healthcheck、初始化用户/secret、以及官方推荐的服务拓扑，不要只看前台入口
- 路由或静态页报找不到 `/lzcapp/pkg/content/...`：先检查 `lzc-build.yml` 是否声明了 `contentdir`
- **Workflow 内联 Dockerfile 覆盖自定义依赖**：如果项目 Dockerfile 添加了运行时依赖，但 workflow 使用内联 Dockerfile 创建，会覆盖自定义内容。解决方案：让 workflow 使用 `cp ${{ github.workspace }}/Dockerfile .` 复制项目文件
- **旧 helper / 外部触发器 与当前 monorepo 流程不兼容**：先回到当前仓库已集成的正式入口，确认是不是 reference 或脚本还停留在旧链路；不要为了“跑通”再额外建辅助分支去适配旧流程
- **目标仓库构建 workflow 秒失败**：如果日志是缺 `github-token` / `GH_TOKEN` 或 dispatch 权限异常，优先修目标仓库或 monorepo 里当前正式链路的 secrets / 权限配置，不要默认绕到外部触发器
- **GHCR push 成功但 `copy-image` 仍报 `UNAUTHORIZED`**：优先检查对应 GHCR 包是否允许外部 pull；LazyCat 复制器拉取镜像时不会自动继承你在 workflow 里的 push 权限。先确认包可见性、仓库关联关系，以及是否需要显式开放 pull
- **GPU-first 模型在 CPU Docker 下频繁报 `cuda` / `pin_memory` / accelerator 错误**：先评估项目是否适合 LazyCat CPU 路线；如果还要继续，优先 patch 主推理路径，再决定是否值得继续追平质量
- **workflow 用宽泛 `sed` 替换 manifest 镜像字段**：这是多服务项目高风险事故源。不要写 `s|image: .*repo.*|...|g` 这类全局替换；改用精确字段更新，只允许修改目标服务块里的 `image`

## 4. 增量更新场景（非全新迁移）

当项目已有完整骨架，只需添加新功能（如新增依赖）时：
- 不需要完整 10 步流程，但仍需验证构建闭环
- 重点检查 workflow 是否会覆盖自定义文件（如内联 Dockerfile 覆盖项目 Dockerfile）
- 修复方案：修改 workflow 使用项目文件而非内联模板

## 5. 失败时的输出模板

```md
[当前步/10] 步骤名称
- 当前结论：明确写失败类型和直接现象
- 当前产出：写明已拿到的日志、run id、报错信息、包路径、状态输出
- 调用脚本：写明本步执行过的脚本
- 阻塞/风险：写明当前阻塞点属于预检 / 构建 / 产物 / 安装 / 启动 / 路由中的哪一类
- 下一步：写明是留在当前步骤修复，还是按规则回退到哪一步
```
