# TTS-Story - 懒猫微服自动构建项目

> [!NOTE]
> 本项目是 [TTS-Story](https://github.com/Xerophayze/TTS-Story) 的懒猫微服（LazyCat）迁移版本，已并入 `lzcat-apps` monorepo，由仓库级共享 workflow 统一完成镜像构建、镜像复制、manifest 回写与 `.lpk` 打包。

> [!IMPORTANT]
> 首次启动会下载所选 TTS 引擎需要的模型文件。为了优先保证 LazyCat CPU 设备上的稳定性，本迁移默认把引擎切到 `Pocket TTS Preset`，其余重型本地引擎保持可选。

## 项目简介

TTS-Story 是一个多引擎 Web TTS 工作台，支持把故事、书籍或分章节文本转换成多角色配音音频。上游提供本地模型、Replicate 云推理、Gemini 文本预处理、语音样本管理、任务队列和音频库等功能。

本次 LazyCat 迁移保留单容器形态，不引入外部数据库，所有状态统一持久化到 `/data`。

## 访问方式

- 安装完成后，通过懒猫分配域名访问：`https://<your-domain>/`
- 健康检查接口：`/api/health`

## 默认运行策略

- 默认 TTS 引擎：`pocket_tts_preset`
- 默认语音：`alba`
- 默认并行块数：`1`
- `pocket_tts_preset` 首次配置会自动写入默认预设语音，避免未分配 speaker 时直接拦截生成
- 本地 GPU 优先的引擎仍然保留，但在 CPU 设备上可能很慢，或在首次使用时触发较大的模型下载

## 数据目录

LazyCat 持久化目录映射：

- `/lzcapp/var/data/tts-story` -> `/data`

运行时会把以下路径持久化到 `/data` 下：

- `config.json`
- `data/jobs/`
- `data/voice_prompts/`
- `data/prep/`
- `data/custom_voices.json`
- `data/chatterbox_voices.json`
- `data/external_voice_archives.json`
- `static/audio/`
- `models/qwen3/`
- Hugging Face / Torch 缓存目录

## 环境变量

大多数配置通过 Web UI 写入 `config.json`。仅建议在需要预置密钥时使用以下环境变量：

- `GEMINI_API_KEY`
- `REPLICATE_API_KEY`
- `CHATTERBOX_TURBO_REPLICATE_API_TOKEN`

如果这些变量存在，入口脚本会在 `config.json` 的对应字段为空时自动写入一次。

## 首次启动说明

首次启动时，入口脚本会自动：

1. 预创建持久化目录和模型缓存目录
2. 初始化 `config.json`
3. 将默认引擎切到稳定优先的 `pocket_tts_preset`
4. 初始化作业数据库
5. 启动 Flask 服务并监听 `5000` 端口

## 已知限制

- `Chatterbox Turbo`、`VoxCPM`、`Qwen3-TTS`、`IndexTTS` 等本地大模型模式在 CPU-only 设备上可能非常慢
- 首次切换到某些模型时仍可能下载 Hugging Face 权重，耗时和磁盘占用都较大；如果切回 `kitten_tts`，其默认模型已做构建期预取
- `pyopenjtalk` 未打进当前容器，因此日语相关特性可能不可用

## 上游链接

- Upstream repository: <https://github.com/Xerophayze/TTS-Story>
- License: Apache-2.0
