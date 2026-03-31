# StorayBoat TTS Gateway

`StorayBoat TTS Gateway` 把 `Edge TTS` 和 `Kokoro` 收敛成一套统一 API。当前迁移版本额外提供了首页说明页，包含动态域名 quickstart、在线 demo、`speech_bundle` 试听下载，以及基于 SSE 的异步任务示例。

## 当前对齐范围

- 上游仓库：`CodeEagle/StorayBoatTTSGateway`
- 上游最新 tag：`v0.2.0`
- 本次已适配的未打 tag 提交：`434e621 feat: add async synthesis job streaming`
- 内置 sidecar：`ghcr.io/remsky/kokoro-fastapi-cpu:v0.2.4`

## 入口

- `/`：说明页与在线 demo
- `/docs`：FastAPI Swagger
- `/healthz`
- `/v1/providers`
- `/v1/voices?provider=edge`
- `/v1/voices?provider=kokoro`
- `/v1/catalog`
- `/v1/audio/jobs`
- `/v1/audio/jobs/{id}`
- `/v1/audio/jobs/{id}/events`
- `/v1/audio/jobs/{id}/bundle`
- `/v1/audio/speech_with_timestamps`
- `/v1/audio/speech_bundle`

## 迁移说明

- 主服务镜像由当前 app 目录内 `Dockerfile` 构建。
- `Dockerfile` 直接安装上游仓库，并叠加本地 `landing_app.py` 作为首页包装层。
- `kokoro-fastapi` 作为 sidecar 通过 `dependencies` 复制进 LazyCat 官方源。

## 配置项

- `KOKORO_FASTAPI_BASE_URL`
  默认 `http://kokoro-fastapi:8880`
- `KOKORO_FASTAPI_TIMEOUT`
  默认 `120`

## 版本策略

- 对外版本号保持与上游 tag 对齐：当前为 `0.2.0`
- 这轮 SSE 适配来自上游 tag 之后的提交，因此 `.lazycat-build.json` 额外记录了实际适配 commit

## 上游链接

- GitHub: https://github.com/CodeEagle/StorayBoatTTSGateway
