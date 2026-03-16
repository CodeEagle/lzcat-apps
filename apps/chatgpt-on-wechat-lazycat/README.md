# ChatGPT-on-WeChat 懒猫微服

[ChatGPT-on-WeChat](https://github.com/zhayujie/chatgpt-on-wechat) 是一个支持多种消息平台的 AI 聊天机器人项目。

## 功能特性

- **多平台支持**: 微信公众号、企业微信、飞书、钉钉、Web 控制台
- **多模型支持**: ChatGPT、Claude、Gemini、通义千问、智谱 AI 等
- **插件系统**: 支持自定义插件扩展功能
- **语音支持**: 支持语音识别和语音合成

## 快速开始

应用已配置 Mock 值，启动后可直接使用，但需要在设置中配置有效的 API 密钥。

### 配置 API 密钥

1. 访问 `http://localhost:9899/chat`
2. 进入设置页面
3. 填入你的 API 密钥（OpenAI、Claude 等）

## 环境变量

### 必需配置

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `OPEN_AI_API_KEY` | `sk-placeholder-replace-in-settings` | OpenAI API 密钥（Mock 值，需替换） |

### 可选配置

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `CHANNEL_TYPE` | `web` | 渠道类型 |
| `MODEL` | `chatgpt` | 模型类型 |
| `OPEN_AI_API_BASE` | `https://api.openai.com/v1` | OpenAI 兼容接口地址 |
| `CONVERSATION_MAX_TOKENS` | `4096` | 会话最大 token 数 |
| `CHARACTER_DESC` | `你是一个智能助手` | 角色描述 |

## 支持的渠道

| 渠道 | `CHANNEL_TYPE` | 说明 |
|------|---------------|------|
| Web | `web` | Web 控制台（默认） |
| 微信公众号 | `wechatmp` | 需要公众号配置 |
| 企业微信 | `wechatcom` | 企业微信应用 |
| 飞书 | `feishu` | 飞书机器人 |
| 钉钉 | `dingtalk` | 钉钉机器人 |

## 支持的模型

| 模型 | 配置变量 | 说明 |
|------|---------|------|
| ChatGPT | `OPEN_AI_API_KEY` | OpenAI GPT 系列 |
| Claude | `CLAUDE_API_KEY` | Anthropic Claude |
| Gemini | `GEMINI_API_KEY` | Google Gemini |
| 通义千问 | `DASHSCOPE_API_KEY` | 阿里云通义千问 |
| 智谱 AI | `ZHIPU_AI_API_KEY` | 智谱 GLM |
| Moonshot | `MOONSHOT_API_KEY` | 月之暗面 Kimi |

## 相关链接

- 项目源码：https://github.com/zhayujie/chatgpt-on-wechat
- 官方文档：https://docs.chatgpt-on-wechat.com/
