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
