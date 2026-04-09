# GPU-First / AI 推理项目迁移判断

这份 reference 用于判断某个 AI / CV / OCR / 推理项目是否适合迁移到 LazyCat CPU / Docker 环境，以及在继续迁移前应该先确认哪些边界。若 CPU 路线不合适，也要继续判断是否更适合迁移成“微服前端 + 算力舱 AIPod GPU 服务”的双端形态，而不是过早下“完全不能迁移”的结论。

## 1. 何时读取

- 上游项目包含模型推理、OCR、CV、分割、RAG、视频处理或多模态理解
- 运行日志、依赖或源码里出现 `cuda`、`pin_memory`、`onnxruntime-gpu`、`triton`、`xformers`、`flash-attn`
- 用户要求“效果和官网一致”
- 迁移后出现“能跑，但效果差很多”

## 2. 先做可迁移性判断，不要先盲改

开始 patch 之前，先回答这 5 个问题：

1. 上游是否默认假设 GPU？
2. 上游官网效果是否依赖未开源前端、闭源服务或额外模型？
3. 关键质量链路是否依赖 refinement、upscale、RMBG、公式 OCR、multimodal OCR、外部 LLM？
4. 上游源码里是否大量硬编码 `cuda` 或只在 GPU 上测试？
5. 用户要的是“能用”还是“效果接近官网”？

如果前 4 项里有 3 项回答为“是”，默认先告知：这个项目很可能不适合 LazyCat CPU/Docker 迁移；但此时还应继续补问一件事：是否能改走 LazyCat AIPod / AI 应用路线。

继续追加 4 个问题：

1. 上游是否本来就是 API / WebUI / Gradio / FastAPI / vLLM / ComfyUI 之类的服务形态？
2. GPU 服务是否可以拆到独立 `docker-compose.yml` 中运行？
3. 微服侧是否只需要前端壳层、反向代理，或少量 API 编排，而不必把 GPU 推理本体塞进普通微服容器？
4. 是否可以接受“服务部署在算力舱，微服通过 API 或 LZC 路由访问”这一拓扑？

如果这 4 项里有 3 项回答为“是”，应优先评估 AIPod 路线。

## 3. 高风险信号

看到下面任一类信号时，要主动提示用户存在显著质量或稳定性风险：

- 默认设备写死为 `cuda`
- 到处使用 `pin_memory()`、`.cuda()`、`torch.autocast(device_type="cuda")`
- 依赖 `onnxruntime`、`spandrel`、`triton`、`decord`、`flash-attn` 等可选加速组件
- 日志出现：
  - `Torch not compiled with CUDA enabled`
  - `Cannot access accelerator device when none is available`
  - `not available, RMBG disabled`
  - `Upscale disabled`
- 接口层主动关闭 `with_refinement`
- 多模态 OCR / VLM 相关 env 为空
- 上游仓库没有公开官网那套前端或完整推理配置

## 4. 质量差异的常见来源

即使服务已经跑起来，效果仍可能明显差于官网。常见原因：

- CPU 替代 GPU：速度和质量稳定性都可能下降
- refinement 被关闭：边界、结构、连线、框选明显变差
- 预处理增强被关闭：如超分、去背景、公式 OCR
- 多模态模型未配置：复杂文字、语义块、图例理解变差
- 上游 demo 使用额外模型、额外参数或外部服务，但开源仓库未提供

## 5. 决策规则

### 可以继续迁移

满足这些条件时，可以继续：

- 用户接受“功能可用优先，不追求与官网一致”
- 核心链路主要是标准 Web 服务或轻量推理
- CPU 路径已有明确支持
- 日志里没有大面积 GPU 硬依赖

### 建议止损

满足任一条时，优先建议止损：

- 为了让 CPU 路径跑通，需要持续 patch 多个上游推理文件
- 已经能跑，但官网效果和迁移版差距仍然明显
- 上游能力高度依赖闭源前端、未公开模型、额外在线服务
- 用户明确要求“和官网一致”

止损时的建议口径：

- 说明该项目更适合原生 GPU 环境或官方部署方式
- 不建议继续在 LazyCat CPU/Docker 环境里做高成本魔改
- 如仍需接入 LazyCat，可退而求其次做“远程服务壳层”

### 建议改走 AIPod

满足这些条件时，优先从 CPU/Docker 路线切换到 AIPod：

- 上游默认依赖 GPU，但服务边界清晰，能独立部署
- 上游已有 Docker / compose / API 服务入口
- 微服侧主要承担前端、配置、账号、路由或结果展示
- 用户接受“GPU 服务在算力舱，微服通过 API 访问”的部署方式

改走 AIPod 时，默认检查这些点：

- `lzc-build.yml` 是否应增加 `ai-pod-service`
- `ai-pod-service/` 下是否能收敛出独立的 `docker-compose.yml`
- GPU 服务的数据目录、缓存目录是否改挂 `LZC_AGENT_DATA_DIR` / `LZC_AGENT_CACHE_DIR`
- 微服入口是直接调算力舱 API，还是通过 LZC 路由中转
- 是否需要为微服侧单独保留非 GPU 的 Web 服务或静态前端

## 6. 验收口径

对这类项目，必须把验收拆成两层：

- 运行验收：服务能启动、接口可调用、结果能返回
- 质量验收：结果与上游官网或用户预期是否接近

不要用“返回了文件”替代“质量通过”。

## 7. 推荐输出

当判断为高风险时，直接给出这类结论：

- 当前版本已达到“功能可跑”
- 尚未达到“效果接近官网”
- 差异主要来自 CPU 路径、关闭的增强链路、未配置的多模态能力
- 继续修复将进入高成本上游魔改，不建议默认继续

当判断“CPU 路线高风险，但 AIPod 可行”时，直接给出这类结论：

- 当前项目不适合继续强压到 LazyCat CPU/Docker 微服容器中
- 更合适的路线是：微服保留前端或壳层，GPU 推理服务迁到算力舱 AIPod
- 下一步应转做 `ai-pod-service` 拆分、算力舱 compose 编排、API/路由对接，而不是继续做 CPU 兼容补丁
