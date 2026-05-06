# hucre 懒猫微服迁移包

[hucre](https://github.com/productdevbook/hucre) 本质上是一个零依赖 TypeScript 电子表格引擎，而非传统后端服务。其上游仓库同时提供 `web/` 目录下的浏览器 playground，但该前端并非“纯静态导出”，而是经 Nitro 构建为 Node server 运行时。本目录即以该演示站为迁移目标，将其封装为 LazyCat 单服务应用。

## 上游信息

- 上游仓库: https://github.com/productdevbook/hucre
- 上游主页: https://github.com/productdevbook/hucre
- 上游许可证: MIT
- 上游作者: productdevbook
- 当前上游版本:
  - `source_version`: `0.1.0`
  - `build_version`: `0.1.1`

## 迁移路线

- 上游形态: TypeScript 库仓库，无官方 Dockerfile、无 compose、无独立后端服务
- LazyCat 形态: 单服务 Web 应用 `hucre-web`
- 容器内进程:
  - Nitro Node server 对外监听 `3000`
  - 构建阶段从上游仓库拉取源码，在 `web/` 子目录执行 `pnpm build`
  - 运行阶段执行 `.output/server/index.mjs`

## 上游部署清单

- 真实入口:
  - `web/package.json` 中 `build` 为 `vite build`
  - `web/vite.config.ts` 使用 `nitro()` 插件
  - 产物由 Nitro 输出到 `web/.output/`，其中真正运行入口为 `web/.output/server/index.mjs`
- 端口:
  - 上游仓库仅提供前端开发命令 `vite dev` / `vite preview`
  - 迁移包运行时由 Nitro server 监听 `3000`
- 环境变量:
  - 上游 `web/` 构建与运行均未声明必填环境变量
- 数据目录:
  - 无容器内持久化写路径
  - 交互数据由浏览器侧文件选择、下载与内存态处理完成
- 初始化命令:
  - 无数据库初始化、无首启迁移命令
- 外部依赖:
  - 无数据库、Redis、对象存储或鉴权依赖

## 使用方式

安装后直接打开 LazyCat 分配之入口域名即可。应用提供以下浏览器侧演示能力：

- 读取 XLSX
- 生成 XLSX
- CSV 解析与导出
- Schema 校验
- Streaming 示例
- ODS 示例
- HTML / Markdown / JSON 导出
- 格式化示例

## 数据与权限

本应用不在容器内写入业务数据，因此不声明 `/lzcapp/var` 挂载。用户上传的文件仅在浏览器会话中处理；生成文件由浏览器直接下载到本地。

## 自动构建

当前项目已经并入 `CodeEagle/lzcat-apps` monorepo：

- 应用目录：`apps/hucre/`
- 构建配置：`registry/repos/hucre.json`
- 配置索引：`registry/repos/index.json`

镜像构建与 `.lpk` 打包继续复用 monorepo 现有共享流程；本目录只保留应用定义与 Dockerfile。
