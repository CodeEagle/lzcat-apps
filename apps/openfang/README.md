# OpenFang - 懒猫微服自动构建项目

> [!NOTE]
> 本项目是 [OpenFang](https://github.com/RightNow-AI/openfang) 的懒猫微服（LazyCat）自动构建项目，用于自动跟踪上游镜像更新并发布到懒猫应用商店。

**OpenFang - The Agent Operating System**

## 关于本项目

本项目会自动监测 [RightNow-AI/openfang](https://github.com/RightNow-AI/openfang) 的容器镜像更新，当有新版本发布时：
1. 自动复制镜像到懒猫官方镜像源
2. 更新 `lzc-manifest.yml` 配置
3. 构建并发布到懒猫应用商店

## OpenFang 简介

OpenFang 是一个开源的 Agent 操作系统，用 Rust 从零构建，而非 Python 框架或聊天机器人包装器。

整个系统编译为单一的 ~32MB 二进制文件，安装即用，你的 Agent 即刻上线。

## 配置说明

> [!IMPORTANT]
> **首次使用需要配置 LLM API Key**
>
> OpenFang 需要至少一个 LLM Provider 的 API Key 才能正常运行。
>
> 在懒猫微服中，进入应用设置，添加以下环境变量之一：
> - `ANTHROPIC_API_KEY` - Anthropic API Key（默认）
> - `OPENAI_API_KEY` - OpenAI API Key
>
> 或在 `lzc-manifest.yml` 的 `services.openfang.environment` 中添加：
> ```yaml
> environment:
>   - ANTHROPIC_API_KEY=your-api-key-here
> ```

## 功能特性

### Autonomous Hands
预构建的自主能力包，独立运行，按计划执行：
- **Clip** - YouTube 视频剪辑，自动生成短视频
- **Lead** - 每日发现潜在客户，评分并交付
- **Collector** - OSINT 级情报收集与监控
- **Predictor** - 超级预测引擎，追踪预测准确性
- **Researcher** - 深度自主研究，生成引用报告
- **Twitter** - 自动化 Twitter/X 账号管理
- **Browser** - Web 自动化，支持审批门控

> [!TIP]
> **Hands 依赖已内置**
>
> 镜像已预装所有 Hands 所需的运行时依赖，开箱即用：
> - **Clip Hand**: `ffmpeg`, `yt-dlp` (视频处理与下载)
> - **Browser Hand**: `python3`, `selenium`, `chromium` (Headless 浏览器自动化)

### 安全特性
- 16 层安全防护
- WASM 双计量沙箱
- Merkle 哈希链审计追踪
- Ed25519 签名的 Agent 清单
- SSRF 防护
- 秘密零化

### 技术亮点
- 137K+ 行 Rust 代码
- 14 个 crates
- 1,828+ 测试
- 0 clippy 警告
- 40+ 通道适配器
- 53+ 内置工具

## Homepage

访问 [openfang.sh](https://openfang.sh) 了解更多信息。

## License

MIT License
