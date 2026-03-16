# GitNexus - 懒猫微服自动构建项目

> [!NOTE]
> 本项目是 [GitNexus](https://github.com/abhigyanpatwari/GitNexus) 的懒猫微服（LazyCat）自动构建项目，用于自动跟踪上游更新，并通过 `lzcat-trigger` 统一完成构建与发布。

> [!IMPORTANT]
> **Icon 规范**：`icon.png` 文件大小不得超过 **200KB**，建议使用 512x512 像素的 PNG 格式图片。

**GitNexus - Zero-Server Code Intelligence Engine**

## 关于本项目

本项目分为两层工作流：

1. 当前仓库的 `update-image.yml` 只负责解析上游版本并构建/推送 `ghcr.io/<owner>/<repo>:<source_version>` 主镜像
2. 当前仓库的 `trigger-build.yml` 负责定时或手动触发 `CodeEagle/lzcat-trigger`
3. `lzcat-trigger` 统一负责复制镜像到懒猫镜像源、回写 `lzc-manifest.yml`、构建 `.lpk`，并按需发布到应用商店

## GitNexus 简介

GitNexus 是一个客户端知识图谱创建工具，完全运行在浏览器中。只需拖放 GitHub 仓库或 ZIP 文件，即可获得交互式知识图谱和内置的 Graph RAG 代理。是代码探索的理想工具。

## 功能特性

- 客户端知识图谱创建 - 无需服务器，完全在浏览器中运行
- 支持 12+ 编程语言：TypeScript, JavaScript, Python, Java, Kotlin, C, C++, C#, Go, Rust, PHP, Swift
- Graph RAG 代理 - 内置 AI 聊天功能
- 交互式可视化 - Sigma.js + Graphology WebGL 渲染
- 隐私优先 - 代码不上传服务器

## 访问方式

部署后通过懒猫微服分配的域名访问：`https://gitnexus.rx79.heiyu.space/`

## 数据目录

- `/lzcapp/var/data` -> `/data`

## 环境变量

- `NODE_ENV=production`
- `BIND=0.0.0.0`

## 关键环境变量说明

| 变量 | 说明 | 默认值 |
|------|------|--------|
| NODE_ENV | 运行环境 | production |
| BIND | 监听地址 | 0.0.0.0 |

## 自动更新

包含两层工作流：

- `.github/workflows/update-image.yml`：只负责构建并推送 `ghcr.io` 主镜像
- `.github/workflows/trigger-build.yml`：负责触发 `CodeEagle/lzcat-trigger`

## License

[PolyForm Noncommercial](https://polyformproject.org/licenses/noncommercial/1.0.0/)

## 本目录文件

- `lzc-manifest.yml`：懒猫应用定义
- `lzc-build.yml`：构建打包配置
- `Dockerfile.template`：Dockerfile 模板
- `.github/workflows/update-image.yml`：自动更新工作流
- `.github/workflows/test-token.yml`：Token 测试工作流
- `.github/workflows/trigger-build.yml`：统一触发器工作流
- `.workflow.md`：工作流说明
