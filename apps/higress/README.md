# Higress - 懒猫微服自动构建项目

> [!NOTE]
> 本项目是 [Higress](https://github.com/alibaba/higress) 的懒猫微服（LazyCat）自动构建项目，用于自动跟踪上游镜像更新，并通过 `lzcat-trigger` 统一完成构建与发布。

> [!IMPORTANT]
> **Icon 规范**：`icon.png` 文件大小不得超过 **200KB**，建议使用 512x512 像素的 PNG 格式图片。

**Higress - AI Native API Gateway - AI 原生 API 网关**

## 关于本项目

本项目分为两层工作流：
1. 当前仓库的 `update-image.yml` 负责跟踪上游版本，并构建/推送本仓库的 `ghcr.io` 主镜像
2. 当前仓库的 `trigger-build.yml` 负责触发 `CodeEagle/lzcat-trigger`
3. `lzcat-trigger` 统一负责复制镜像到懒猫镜像源、回写 `lzc-manifest.yml`、构建 `.lpk`，并按需发布到应用商店

## Higress 简介

Higress 是基于 Istio 和 Envoy 的云原生 API 网关，可以通过 Go/Rust/JS 编写的 Wasm 插件进行扩展。它提供了数十个开箱即用的通用插件和一个开箱即用的控制台。

### 核心特性

- **AI 网关**: 支持所有主流 LLM 模型提供商，统一协议接入，具备 AI 可观测性、多模型负载均衡、Token 限流和缓存能力
- **MCP Server 托管**: 通过插件机制托管 MCP (Model Context Protocol) 服务器，让 AI Agent 轻松调用各种工具和服务
- **Kubernetes Ingress Controller**: 兼容 K8s nginx ingress controller 的许多注解，支持 Gateway API
- **微服务网关**: 支持从 Nacos、ZooKeeper、Consul、Eureka 等服务注册中心发现微服务
- **安全网关**: 支持 WAF 和多种认证策略（key-auth、hmac-auth、jwt-auth、basic-auth、oidc 等）

### 核心优势

- **生产级**: 源自阿里内部产品，经过 2 年多的生产验证，支持每秒数十万请求的大规模场景
- **流式处理**: 支持真正的完整请求/响应体流式处理，Wasm 插件可以轻松自定义 SSE 等流式协议的处理
- **易扩展**: 提供丰富的官方插件库，覆盖 AI、流量管理、安全防护等常见功能
- **安全易用**: 基于 Ingress API 和 Gateway API 标准，提供开箱即用的 UI 控制台

## 功能特性

- MCP Server 托管 - 统一认证授权、细粒度限流、审计日志
- AI Gateway - 统一 LLM API 接入、可观测性、负载均衡
- Kubernetes Ingress Controller - 兼容 nginx ingress，资源开销更低
- 微服务网关 - 支持 Nacos、Dubbo、Consul 等服务发现
- 安全网关 - WAF、多种认证策略

## Homepage

访问 [https://higress.io](https://higress.io) 了解更多信息。

## License

Apache License 2.0
