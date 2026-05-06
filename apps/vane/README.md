# Vane - 懒猫微服自动构建项目

> [!NOTE]
> 本项目用于把上游 [ItzCrazyKns/Vane](https://github.com/ItzCrazyKns/Vane) 迁移到懒猫微服（LazyCat），并接入当前 `lzcat-apps` monorepo 的共享构建链路。

> [!IMPORTANT]
> 当前 monorepo 以 `scripts/run_build.py` / `scripts/local_build.sh` 作为正式构建入口，而不是旧版 skill 文档中的独立 helper 脚本。

## 上游项目简介

Vane 是一款隐私优先的 AI answering engine，提供 Web 搜索、引用来源、文件上传、图片/视频搜索以及多模型接入能力。官方完整镜像内置了 SearXNG，因此可以以单容器形式运行。

## 本次移植结论

- 移植路线：单容器，直接复用上游官方 Docker 镜像
- 上游最新稳定版本：`v1.12.1`
- 容器真实 Web 入口：`3000`
- 容器内置 SearXNG：`8080`
- 最小持久化目录：`/home/vane/data`
- 首次启动可能需要较长时间完成内置 SearXNG 和 Next.js 预热，所以健康检查窗口已经拉长

## 已确认的上游部署清单

- 真实启动入口：`entrypoint.sh`
  - 先以 `searxng` 用户启动内置 SearXNG（`0.0.0.0:8080`）
  - 再启动 Vane Next.js 服务（`node server.js`，监听 `3000`）
- 官方完整镜像：`itzcrazykns1337/vane:<tag>`
  - Docker Hub 当前可直接拉取的稳定入口是 `latest`
  - 本次 LazyCat 复制源使用 `docker.io/itzcrazykns1337/vane:latest`
- 官方 slim 镜像：`itzcrazykns1337/vane:slim-<tag>`
  - 需要外部 SearXNG，本次不采用
- 环境变量
  - `DATA_DIR`：决定 `config.json` 与 SQLite 数据库根目录
  - `SEARXNG_API_URL`：Vane 访问 SearXNG 的地址；完整镜像默认 `http://localhost:8080`
  - `NODE_ENV`：生产环境设为 `production`
- 真实写路径
  - `${DATA_DIR}/data/config.json`
  - `${DATA_DIR}/data/db.sqlite`
  - `${DATA_DIR}/data/uploads/*`
  - 官方 Docker 默认 `DATA_DIR=/home/vane`，因此统一持久化 `/home/vane/data`
- 首次启动初始化
  - 若 `config.json` 不存在，会自动生成默认配置
  - 若 SQLite 文件不存在，会在首次访问时创建
  - 文件上传目录 `data/uploads` 会由应用自动创建
- 外部依赖
  - 完整镜像不依赖外部数据库、Redis 或独立 SearXNG
  - 模型提供商 API Key 可在首次进入 Web UI 后配置，也可通过环境变量预注入

## 访问方式

安装后通过 LazyCat 分配的应用域名访问根路径 `/`。

推荐首次启动后的配置步骤：

1. 打开应用首页完成初始设置
2. 在设置页配置至少一个聊天模型 / embedding 模型提供商
3. 如需接入宿主机 Ollama，再把 `OLLAMA_BASE_URL` 指向可访问地址

## 端口与挂载

| 服务 | 容器端口 | 说明 |
|------|----------|------|
| `vane` | `3000` | Web UI 与 API 主入口 |
| `vane` | `8080` | 容器内置 SearXNG，仅容器内访问 |

| 宿主机路径 | 容器路径 | 用途 |
|------------|----------|------|
| `/lzcapp/var/data/vane` | `/home/vane/data` | 配置、SQLite 数据库、上传文件与索引数据 |

## 环境变量

manifest 中默认写入以下运行时变量：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DATA_DIR` | `/home/vane` | Vane 的配置与 SQLite 根目录 |
| `SEARXNG_API_URL` | `http://localhost:8080` | 指向容器内置 SearXNG |
| `NODE_ENV` | `production` | 生产模式 |
| `PORT` | `3000` | Next.js Web 主入口端口 |
| `HOSTNAME` | `0.0.0.0` | 强制 Next.js 监听所有网卡，避免只绑容器主机名 |

说明：

- 上游支持把模型提供商 Key 通过环境变量预注入，但这不是启动必需项。
- 如果不预填，应用仍可启动，用户可以在 Web 设置页完成配置。

## 当前已知阻塞

- 预检 / 构建 / 下载 / 安装验收统一使用 `scripts/full_migrate.py`，辅助工具见 `skills/lazycat-migrate/scripts/`。

## 上游链接

- Upstream Repo: [https://github.com/ItzCrazyKns/Vane](https://github.com/ItzCrazyKns/Vane)
- Homepage: [https://github.com/ItzCrazyKns/Vane](https://github.com/ItzCrazyKns/Vane)
- License: MIT
