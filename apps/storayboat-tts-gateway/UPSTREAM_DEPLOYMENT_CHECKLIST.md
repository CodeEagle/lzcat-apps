# StorayBoat TTS Gateway 上游部署清单

## 1. 上游来源

- 仓库：`CodeEagle/StorayBoatTTSGateway`
- 主页：<https://github.com/CodeEagle/StorayBoatTTSGateway>
- 当前最新 tag：`v0.2.1`
- 当前已适配提交：`c29afa280d29459585a6ae586b1eb7624a1b479f`

## 2. 上游运行拓扑

### 主服务

- 文件：`Dockerfile`
- 基础镜像：`python:3.12-slim`
- 安装方式：`pip install .`
- 监听端口：`5051`
- 启动命令：

```bash
python -m uvicorn storayboat_tts_gateway.app:app --host 0.0.0.0 --port 5051
```

### 依赖服务

- 文件：`docker-compose.yml`
- 服务名：`kokoro-fastapi`
- 镜像：`ghcr.io/remsky/kokoro-fastapi-cpu:v0.2.4`
- 监听端口：`8880`

## 3. 环境变量

来自 `.env.example` 与 `docker-compose.yml`：

- `STORAYBOAT_PORT=5051`
- `KOKORO_FASTAPI_PORT=8880`
- `KOKORO_FASTAPI_IMAGE=ghcr.io/remsky/kokoro-fastapi-cpu:v0.2.4`
- `KOKORO_FASTAPI_BASE_URL=http://kokoro-fastapi:8880`
- `KOKORO_FASTAPI_TIMEOUT=120`

## 4. API 能力

### 同步接口

- `GET /healthz`
- `GET /v1/providers`
- `GET /v1/voices?provider={provider}`
- `GET /v1/catalog`
- `POST /v1/audio/speech_with_timestamps`
- `POST /v1/{provider}/audio/speech_with_timestamps`
- `POST /v1/audio/speech`
- `POST /v1/audio/speech_bundle`

### 异步 + SSE

- `POST /v1/audio/jobs`
- `GET /v1/audio/jobs/{id}`
- `GET /v1/audio/jobs/{id}/events`
- `GET /v1/audio/jobs/{id}/bundle`

## 5. 数据目录

- 主服务为无状态 API 网关
- 当前未声明必须持久化的数据目录
- `kokoro-fastapi` sidecar 也按无状态服务处理

## 6. LazyCat 迁移落点

- 主路由：`/ -> http://storayboat-tts-gateway:5051/`
- 主镜像：当前仓库内 `Dockerfile` 构建
- sidecar 镜像：通过 `dependencies` 做 `copy-image`
- 首页包装层：`landing_app.py`

## 7. 本轮特别说明

- 当前版本已直接对齐上游 `v0.2.1`
- `landing_app.py` 只增加首页和 demo，不改写上游 API 语义
