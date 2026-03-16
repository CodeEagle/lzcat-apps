# AutoClip - 懒猫微服迁移项目

> [!NOTE]
> 本项目是 [zhouxiaoka/autoclip](https://github.com/zhouxiaoka/autoclip) 的懒猫微服迁移骨架，目标是在 LazyCat 中提供可访问的前端页面、FastAPI 后端、Celery Worker 与 Redis。

> [!IMPORTANT]
> 上游仓库当前没有稳定 release/tag；本迁移首版采用源码内声明的 `1.0.0` 作为应用版本，并在工作流里用提交 SHA 作为镜像标签来源。

## 上游项目

- 上游仓库: [zhouxiaoka/autoclip](https://github.com/zhouxiaoka/autoclip)
- Homepage: [https://github.com/zhouxiaoka/autoclip](https://github.com/zhouxiaoka/autoclip)
- License: MIT
- 作者: zhouxiaoka

## 应用简介

AutoClip 是一个 AI 视频智能切片系统，支持视频下载、片段分析、自动切片、合集管理和异步任务处理。上游项目使用 React + Vite 前端、FastAPI 后端、Celery Worker、Redis 与 SQLite。

## 本次迁移的保留服务

- `web`: 自定义构建镜像，内部同时运行 `nginx + FastAPI`，对外提供单一 Web 入口
- `worker`: 复用同一镜像，执行 Celery 异步任务
- `redis`: 任务队列与缓存

本次没有保留：

- `celery-beat`: 上游定时任务服务，非最小可运行路径必需
- `flower`: 调试/监控用途，可选，不纳入首版迁移

## 访问方式

- 应用入口: `https://autoclip.${LAZYCAT_APP_DOMAIN}`
- 前端页面: `/`
- FastAPI 文档: `/docs`
- 健康检查: `/api/v1/health/`

## 环境变量

| 变量 | 必填 | 说明 |
| --- | --- | --- |
| `API_DASHSCOPE_API_KEY` | 是 | 通义千问 API Key，AI 处理能力依赖该变量 |
| `API_MODEL_NAME` | 否 | 默认 `qwen-plus` |
| `API_MAX_TOKENS` | 否 | 默认 `4096` |
| `API_TIMEOUT` | 否 | 默认 `30` 秒 |
| `CELERY_CONCURRENCY` | 否 | Worker 并发数，默认 `2` |

## 数据目录

| 懒猫路径 | 容器内路径 | 用途 |
| --- | --- | --- |
| `/lzcapp/var/data/autoclip` | `/app/data` | SQLite、项目数据、设置文件、上传文件、输出文件、临时文件 |
| `/lzcapp/var/log/autoclip` | `/app/logs` | 应用日志 |
| `/lzcapp/var/data/autoclip/redis` | `/data` | Redis 持久化数据 |

上游代码同时存在 `/app/data/*`、`/app/uploads`、`/app/output` 三套路径约定。本迁移在启动脚本里统一把 `/app/uploads` 和 `/app/output` 重定向回 `/app/data/uploads`、`/app/data/output`，避免本地导入、在线拉取资源和生成结果在重启后丢失。

## 首次启动说明

1. 配置 `API_DASHSCOPE_API_KEY`
2. 首次启动时容器会自动初始化 SQLite 数据库
3. `web` 服务会在内部启动 FastAPI (`8000`) 与 nginx (`3000`)
4. 首次保存 AI 配置后会写入 `/app/data/settings.json`
5. 访问应用首页后即可使用 Web UI

## 迁移说明

- 上游 Dockerfile 只默认启动 FastAPI，虽然暴露了 `3000` 端口，但没有真正提供前端服务
- 本迁移通过自定义 `Dockerfile.template`、`nginx` 配置和启动脚本，将构建好的前端静态资源与 API 汇聚到同一个 Web 入口
- 工作流默认只负责构建并推送 `ghcr.io/<owner>/autoclip:<commit-sha>` 主镜像，以兼容 `lzcat-trigger`

## 待验证项

- `registry.lazycat.cloud/...` 镜像地址需要在触发正式构建并完成 `copy-image` 后回写
- Redis 懒猫镜像标签需要在真实构建/安装阶段替换为已复制到 LazyCat Registry 的地址
- 本地或目标仓库完成首轮 Actions 构建后，需继续执行 `.lpk` 下载、安装与入口验收
