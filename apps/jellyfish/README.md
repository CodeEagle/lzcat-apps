# Jellyfish 懒猫微服迁移包

[Jellyfish](https://github.com/Forget-C/Jellyfish) 是一个面向 AI 短剧生产的前后端分离项目，覆盖项目管理、章节工作台、分镜管理、素材管理和模型配置等流程。本目录将其移植为 LazyCat 单容器应用：容器内同时运行 `Nginx + FastAPI`，前端静态页面和 `/api` 接口统一通过同一个域名对外提供。

## 上游项目

- 上游仓库: https://github.com/Forget-C/Jellyfish
- 上游主页: https://github.com/Forget-C/Jellyfish
- 上游许可证: Apache-2.0
- 当前适配版本:
  - `source_version`: `cd5d1c7`
  - `build_version`: `0.1.0`

## 迁移路线

- 上游形态: 前后端源码仓库，无官方 Dockerfile、无 compose
- LazyCat 形态: 单服务容器 `jellyfish`
- 容器内进程:
  - `uvicorn app.main:app` 监听 `127.0.0.1:8000`
  - `nginx` 对外监听 `8080`，根路径提供前端页面，并反代 `/api`、`/docs`、`/redoc`、`/openapi.json`

## 本次兼容改动

上游仓库直接运行时有两处会影响 LazyCat 可用性，本迁移包在镜像构建阶段做了最小修复：

1. 上游只实现了 S3 对象存储。迁移包增加“未配置 `S3_BUCKET_NAME` 时自动回退到本地文件系统”的逻辑，默认把素材写入 `/data/storage`，并通过 `/local-files/...` 对外暴露。
2. 上游 `README` 声称首次启动会自动建表，但代码里并未实际执行。迁移包在 FastAPI 生命周期里补上 `init_db()`，保证 SQLite 首次启动自动创建表。

## 访问方式

- 应用首页: `https://<你的应用域名>/`
- 健康检查: `https://<你的应用域名>/health`
- OpenAPI 文档: `https://<你的应用域名>/docs`
- OpenAPI JSON: `https://<你的应用域名>/openapi.json`

## 环境变量

### 默认可直接使用

| 变量名 | 默认值 | 说明 |
| --- | --- | --- |
| `PORT` | `8000` | 容器内 FastAPI 监听端口 |
| `DATABASE_URL` | `sqlite+aiosqlite:////data/jellyfish.db` | SQLite 数据库路径 |
| `LOCAL_STORAGE_DIR` | `/data/storage` | 本地素材存储目录 |
| `OPENAI_MODEL` | `gpt-4o-mini` | 默认文本模型名 |

### 按需配置

| 变量名 | 说明 |
| --- | --- |
| `OPENAI_API_KEY` | 启用文本抽取相关接口所需 |
| `OPENAI_BASE_URL` | 自定义 OpenAI 兼容接口地址 |
| `IMAGE_API_PROVIDER` / `IMAGE_API_KEY` / `IMAGE_API_BASE_URL` | 图片生成任务供应商配置 |
| `VIDEO_API_PROVIDER` / `VIDEO_API_KEY` / `VIDEO_API_BASE_URL` | 视频生成任务供应商配置 |
| `S3_ENDPOINT_URL` / `S3_REGION_NAME` / `S3_ACCESS_KEY_ID` / `S3_SECRET_ACCESS_KEY` / `S3_BUCKET_NAME` / `S3_BASE_PATH` / `S3_PUBLIC_BASE_URL` | 如果希望改回对象存储模式，可显式提供整套 S3 参数 |

未配置 `S3_BUCKET_NAME` 时，上传类接口使用本地存储，不依赖外部对象存储。

## 数据目录

| LazyCat 目录 | 容器内路径 | 用途 |
| --- | --- | --- |
| `/lzcapp/var/data/jellyfish` | `/data` | SQLite、上传素材、本地持久化数据 |

容器内实际读写路径：

- `/data/jellyfish.db`: SQLite 数据库
- `/data/storage`: 上传素材、本地对象存储回退目录

## 首次启动说明

- 首次启动时自动创建 SQLite 表结构
- 未配置任何模型 API Key 时，项目管理、素材管理等基础界面可访问，但依赖外部模型的抽取/生成接口会返回上游定义的错误
- 前端生产包已关闭 `VITE_USE_MOCK`，默认直连真实后端接口

## 自动构建

当前项目已经并入 `CodeEagle/lzcat-apps` monorepo，配置、应用文件和触发入口都在本仓库内：

- 应用目录：`apps/jellyfish/`
- 构建配置：`registry/repos/jellyfish.json`
- 配置索引：`registry/repos/index.json`

当前 app 目录不再保留独立 `.github` 工作流。镜像构建、包构建和触发逻辑统一由仓库外部的共享 workflow 负责；app 目录只保留应用定义、构建文件和补丁内容。

## 相关链接

- 上游项目 README: https://github.com/Forget-C/Jellyfish#readme
- 上游英文文档: https://github.com/Forget-C/Jellyfish/blob/main/docs/README.en.md
- LazyCat 开发文档: https://developer.lazycat.cloud/
