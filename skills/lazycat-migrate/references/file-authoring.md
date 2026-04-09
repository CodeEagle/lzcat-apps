# 文件填写细则

用于 `[4/10]`、`[5/10]`、`[6/10]`。这里只写骨架与文件填写规则，不重复生命周期说明。

## 1. 先建目标仓库并注册到 monorepo
- 先切 GitHub 账号：`gh auth switch -u CodeEagle`
- 先确认 `GH_TOKEN` 已配置；未配置时，不创建新仓库，不继续 GitHub 自动化步骤
- 优先执行：

```bash
scripts/ensure-github-repo.sh \
  --upstream-repo owner/upstream-project \
  --repo-owner CodeEagle \
  --clone-dir ~/Develop/GitHub
```

- 未传 `--repo-name` 时，目标仓库名默认等于上游仓库名
- 除非用户明确要求其他命名，否则不要改仓库名

**目标仓库创建后，必须同步注册到 `CodeEagle/lzcat-apps` monorepo：**

1. 在 `lzcat-apps/registry/repos/` 创建 `<appname>.json`（全小写，无 owner 前缀）：

```json
{
  "repo": "CodeEagle/<repo-name>",
  "enabled": true,
  "upstream_repo": "<upstream-owner>/<upstream-name>",
  "check_strategy": "github_release",
  "build_strategy": "<strategy>",
  "publish_to_store": false,
  "official_image_registry": "",
  "precompiled_binary_url": "",
  "dockerfile_type": "custom",
  "dockerfile_path": "Dockerfile",
  "build_context": ".",
  "service_port": 0,
  "service_cmd": [],
  "image_targets": ["<main-service-name>"],
  "dependencies": []
}
```

2. 将 `<appname>.json` 追加到 `lzcat-apps/registry/repos/index.json` 的 `repos` 数组
3. 在 `lzcat-apps/apps/<appname>/`（全小写）创建与目标仓库同步的应用文件镜像
4. 提交到 `lzcat-apps` monorepo

`registry/repos/index.json` 是 `CodeEagle/lzcat-apps` monorepo 的构建配置入口；未追加则不会被 monorepo 的集成链路检查到。

**构建策略速查：**

| 场景 | `build_strategy` | 关键额外字段 |
|---|---|---|
| 官方 Docker Hub / GHCR 镜像直接复用 | `official_image` | `official_image_registry` |
| 上游有 Release 二进制 | `precompiled_binary` | `precompiled_binary_url` |
| 目标仓库自带 Dockerfile（直接构建） | `target_repo_dockerfile` | `dockerfile_path`, `build_context` |
| 上游源码 + 目标仓库 Dockerfile.template（含 `{{SERVICE_PORT}}` 等占位符） | `upstream_with_target_template` | `dockerfile_path: Dockerfile.template`, `overlay_paths` |
| 直接使用上游仓库的 Dockerfile 构建 | `upstream_dockerfile` | — |

`check_strategy`：通常用 `github_release`；无 release 只有 tag 用 `github_tag`；无版本语义用 `commit_sha`。

注意：`target_repo_dockerfile` 直接编译目标仓库里的 Dockerfile，不处理占位符；如果 Dockerfile 含 `{{...}}`，必须改用 `upstream_with_target_template`。

## 2. 建立骨架
- 优先复用 `lzcat-template/`
- 最低文件集：`README.md`、`lzc-manifest.yml`、`lzc-build.yml`、`icon.png`
- `icon.png` 文件大小不得超过 200KB，建议使用 512x512 像素的 PNG 格式图片
- 需要静态资源、默认配置、管理页时，再补 `content/`
- 需要自动跟踪上游版本时，再补 `.github/workflows/update-image.yml`

## 3. `lzc-manifest.yml` 填写顺序

写 manifest 前，先整理一份“上游部署清单”，至少包含：
- Dockerfile / compose / entrypoint / startup script 的真实启动入口
- 环境变量来源：README、DOCKER 文档、`.env.example`、默认配置文件
- 所有真实读写路径：数据、配置、缓存、上传、日志、临时目录
- 初始化与迁移动作：建库、建表、seed、管理员创建、首次下载模型或资源
- 外部依赖：数据库、Redis、对象存储、邮件、auth / OAuth / JWT / callback / secret
- 每个目录是否要预创建，以及应由哪个用户、以什么 owner / group / mode 创建

没有这份清单时，不要开始猜 `services.*`、`binds`、`environment`。

### 元信息
- `package`：保持唯一且稳定，优先使用 `fun.selfstudio.app.migration.<slug>`
- `version`：必须是纯 semver `X.Y.Z`
- `name`、`description`、`license`、`homepage`、`author`：直接对应上游元信息

### Web 入口
- `application.subdomain`：通常使用 `PROJECT_SLUG`
- `application.upstreams[].backend`：直接写真实后端地址，例如 `http://web:3000/`
- 如果真实入口不在根路径，例如 `/mcp`、`/sse`、`/messages/`，就在 `backend` 中写完整路径，不要假设前缀会自动透传

### 服务定义
- `services.<service>.image`：填写最终可安装的 `registry.lazycat.cloud/...` 镜像地址
- `environment`：只保留真实需要的变量，区分必填项与可默认项
- `binds`：只保留真正需要持久化的目录
- `setup_script`：仅在首次初始化确实需要时添加
- 如果服务已定义 `command`，默认不要再定义 `setup_script`
- 先按“真实写路径”设计 `binds`，不要按路径名猜；上传目录、运行时生成目录、SQLite / KV / session / plugin / model cache 路径都要单独核实
- 对扫描到且会被访问的目录，默认先预创建；对会在启动时 `mkdir` / 写文件的目录，必须确认容器运行用户是否对目标路径有写权限；需要时在启动前显式补 `install -d`、`mkdir -p && chown` 或软链兼容，而不是等安装后再修
- 如果上游同时存在历史路径和当前路径，优先在启动链路里做兼容目录或软链，避免只挂一个新目录导致旧代码分支仍然写到无权限位置

### 本地化
- 同步维护 `locales.en` 与 `locales.zh`
- 中文描述保持功能直译，不堆营销词

## 4. README 最低要求
- 说明本仓库对应哪个上游项目
- 说明应用用途和入口访问方式
- 写清楚首次启动后的配置动作
- 写清楚必须配置的环境变量
- 写清楚数据保存目录
- 给出上游项目与文档链接

## 5. `lzc-build.yml` 最小形态

```yml
manifest: ./lzc-manifest.yml
pkgout: ./
icon: ./icon.png
```

如果 manifest 或运行逻辑引用 `/lzcapp/pkg/content/...`，必须增加：

```yml
contentdir: ./content
```

规则：
- `contentdir` 指向源码目录，由构建器打包成包内内容
- 不要把构建产物当源码提交
- 运行前必须存在的静态页、默认配置、管理页 HTML 都放在 `content/`

## 6. workflow 设计规则
- 默认使用当前 monorepo 或目标仓库已经集成的正式流程
- 构建触发入口优先复用当前仓库定义的 workflow / 脚本；不要为了兼容旧流程额外引入外部触发器、独立 config repo 或辅助分支
- 目标仓库 `update-image.yml` 默认只负责：解析上游版本 -> 构建并推送 `ghcr.io/${{ github.repository }}:<commit_sha>` 主镜像 -> 输出必要元数据；如果 monorepo 已经内建完整链路，就按 monorepo 现有约定落地
- 自建镜像 tag 只能使用 commit SHA（完整或短 SHA），禁止复用 `source_version`、`VERSION` 或其他版本号；版本号只保留给 manifest/version、release 名称和展示字段，否则容易命中旧缓存导致镜像未实际更新
- 不要默认把 `copy-image`、manifest 回写、`.lpk` 构建、商店发布、GitHub Release 上传都塞回目标仓库 workflow
- 只有用户明确要求目标仓库自闭环，或已确认当前项目就是目标仓库自管发布链，才把完整发布链写回目标仓库

目标仓库 workflow 至少兼容这些 `workflow_dispatch.inputs`：
- `force_build`
- `target_version`
- `publish_to_store`

## 7. 文件层面的禁止项
- 禁止把宿主映射端口写进 `backend`
- 禁止把 `ghcr.io` / `docker.io` / `quay.io` 直接写进最终 manifest
- 禁止使用服务名 `app`
- 禁止在同一服务里同时定义 `command` 与 `setup_script`
- 禁止引用 `/lzcapp/pkg/content/...` 却不声明 `contentdir`
- 禁止把缓存目录误记为持久化目录
- 禁止把上游环境变量不分辨地全量搬进 manifest 和 README
