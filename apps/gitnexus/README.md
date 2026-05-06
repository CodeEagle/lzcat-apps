# GitNexus - 懒猫微服自动构建项目

> [!NOTE]
> 本项目是 [GitNexus](https://github.com/abhigyanpatwari/GitNexus) 的懒猫微服（LazyCat）迁移项目，已并入 `lzcat-apps` monorepo，由仓库级共享 workflow 统一完成构建与发布。

> [!IMPORTANT]
> **Icon 规范**：`icon.png` 文件大小不得超过 **200KB**，建议使用 512x512 像素的 PNG 格式图片。

**GitNexus - Zero-Server Code Intelligence Engine**

## 关于本项目

当前项目已经并入 `lzcat-apps` monorepo。镜像构建、镜像复制、manifest 回写和 `.lpk` 构建由仓库级共享 workflow 统一处理；app 目录只保留应用定义和运行文件。

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

自动更新由 `lzcat-apps` 仓库级共享 workflow 负责，配置入口为 `registry/repos/gitnexus.json`。

## License

[PolyForm Noncommercial](https://polyformproject.org/licenses/noncommercial/1.0.0/)

## 本目录文件

- `lzc-manifest.yml`：懒猫应用定义
- `lzc-build.yml`：构建打包配置
- `Dockerfile.template`：Dockerfile 模板
