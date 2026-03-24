# lzcat-apps

懒猫微服（LazyCat）移植应用的 monorepo，集中管理所有移植 app 的配置文件与构建资产。

## 目录结构

```
lzcat-apps/
├── apps/                          # 各移植应用
│   ├── airflow/                   # Apache Airflow
│   ├── Airi/                      # AIRI AI Companion
│   ├── autoclip/                  # AutoClip
│   ├── chatgpt-on-wechat-lazycat/ # ChatGPT on WeChat
│   ├── CliRelay/                  # CliRelay
│   ├── cmms/                      # CMMS
│   ├── cutia/                     # Cutia
│   ├── ebook2audiobook/           # ebook2audiobook (待配置)
│   ├── Edit-Banana/               # Edit Banana
│   ├── GitNexus/                  # GitNexus
│   ├── Higress/                   # Higress
│   ├── markitdown/                # Markitdown
│   ├── OpenFang/                  # OpenFang
│   ├── paperclip/                 # Paperclip
│   ├── remodex-relay/             # Remodex Relay
│   ├── TaoYuan/                   # TaoYuan
│   └── waoowaoo/                  # Waoowaoo
└── registry/
    └── repos/                     # 各 app 的构建配置 JSON
        ├── index.json
        └── <app>.json
```

每个 `apps/<name>/` 目录包含：
- `lzc-manifest.yml` — 懒猫应用清单
- `lzc-build.yml` — 构建配置
- `icon.png` — 应用图标
- `Dockerfile` / `Dockerfile.template`（如需自定义构建）
- `README.md` — 应用说明

## 与 lzcat-trigger 的集成

`lzcat-trigger` 定时检查、构建、发布流程需做以下调整以支持 monorepo：

| 原来（多 repo） | 调整后（monorepo） |
|---|---|
| 从 `CodeEagle/lzcat-registry` 读取 JSON 配置 | 从本 repo 的 `registry/repos/` 读取 |
| checkout 各独立 repo 获取 Dockerfile / manifest | checkout 本 repo 的 `apps/<name>/` 子目录 |
| 回写 `lzc-manifest.yml` 到各独立 repo | 向本 repo 提交 PR / 直接 push `apps/<name>/lzc-manifest.yml` |
| `config_repo` 默认 `CodeEagle/lzcat-registry` | 改为 `CodeEagle/lzcat-apps`，`config_path` 前缀改为 `registry/repos/` |

## 新增 App

1. 在 `apps/` 下新建 `<name>/` 目录，放入 `lzc-manifest.yml`、`lzc-build.yml`、`icon.png`
2. 在 `registry/repos/` 下新建 `<name>.json`
3. 在 `registry/repos/index.json` 中追加文件名
4. 提交后 `lzcat-trigger` 下次轮询自动加载

## 一键迁移 SOP

真正面向“只给一个上游地址就开始跑”的入口是：

```bash
./scripts/full-migrate.sh <upstream-address>
```

支持的输入：

- GitHub 仓库 URL，例如 `https://github.com/owner/repo`
- GitHub 简写，例如 `owner/repo`
- `docker-compose.yml` / `compose.yaml` URL
- Docker / GHCR 镜像地址
- 本地上游仓库目录

脚本会按当前 `lazycat-migrate` 的 10 步 SOP 自动推进：

- 自动识别来源类型并抓取上游材料
- 自动推断迁移路线（`official_image` / `upstream_dockerfile` / `upstream_with_target_template` / `precompiled_binary`）
- 自动注册到 `apps/<slug>/` 和 `registry/repos/<slug>.json`
- 自动生成 `lzc-manifest.yml`、`lzc-build.yml`、`README.md`、`UPSTREAM_DEPLOYMENT_CHECKLIST.md`
- 自动运行预检
- 如果本机具备容器引擎和 token，就继续尝试本地构建/安装；缺条件时会停在对应步骤并明确报阻塞

容器引擎优先顺序：

- 优先使用 `docker`
- 如果没有 `docker` 但有 `podman`，脚本会自动做兼容桥接

## 骨架脚本

现在可以直接用 `scripts/bootstrap_migration.py` 生成新 app 的初稿骨架，而不是手工复制旧项目目录。

最小单服务示例：

```bash
./scripts/bootstrap_migration.py \
  --slug demo-app \
  --project-name "Demo App" \
  --upstream-repo owner/demo-app \
  --build-strategy official_image \
  --official-image-registry ghcr.io/owner/demo-app \
  --service-port 8080
```

复杂多服务项目建议先写 JSON spec，再一次性生成：

```bash
./scripts/bootstrap_migration.py \
  --spec docs/migration-spec.example.json
```

脚本会自动完成这些动作：

- 创建 `apps/<slug>/README.md`、`lzc-manifest.yml`、`lzc-build.yml`、`UPSTREAM_DEPLOYMENT_CHECKLIST.md`、`icon.png`
- 按构建策略生成 `Dockerfile` / `Dockerfile.template` 占位文件（如果该策略需要）
- 写入 `registry/repos/<slug>.json`
- 追加 `registry/repos/index.json`
- 在需要时创建 `content/` 和 `overlay_paths`

注意：

- 这是“迁移骨架一键化”，不是“完整移植全自动化”。真实入口、环境变量、数据目录、初始化命令和依赖拓扑，仍然要回到 `UPSTREAM_DEPLOYMENT_CHECKLIST.md` 补齐后再进构建/验收。
- 对复杂项目，优先用 spec 明确 `application`、`services`、`image_targets`、`dependencies`，不要只靠单服务参数硬猜。
