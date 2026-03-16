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
        └── CodeEagle__*.json
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
2. 在 `registry/repos/` 下新建 `CodeEagle__<name>.json`
3. 在 `registry/repos/index.json` 中追加文件名
4. 提交后 `lzcat-trigger` 下次轮询自动加载
