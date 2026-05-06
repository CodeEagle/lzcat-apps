# waoowaoo - 懒猫微服自动构建项目

> [!NOTE]
> 本项目跟踪 [waoowaooAI/waoowaoo](https://github.com/waoowaooAI/waoowaoo) 上游源码，并已并入 `lzcat-apps` monorepo，由仓库级共享 workflow 统一完成镜像复制、清单回写与 `.lpk` 构建。

> [!IMPORTANT]
> **Icon 规范**：`icon.png` 文件大小不得超过 **200KB**，建议使用 512x512 像素的 PNG 格式图片。

## 本次修复

- 修复应用容器里错误调用 `mysqladmin` 等待数据库的问题
- 改为使用 Node 自带 TCP 探测等待 `mysql:3306` 与 `redis:6379`
- 增加 MySQL / Redis healthcheck，让 `depends_on` 真正等待依赖健康
- 明确 `/app/data` 与 `/app/logs` 的持久化挂载
- 将入口健康检查固定到 `/api/system/boot-id`
- 拉长 MySQL / Redis / 应用自身的健康检查宽限期，避免首次安装时被过早判定失败

## 验收结果

这套 manifest 已在 LazyCat 盒子里完成安装验证：

- MySQL、Redis、`waoowaoo`、入口 sidecar 全部进入 `healthy`
- `Prisma db push --skip-generate` 成功
- Next.js `0.0.0.0:3000` 启动成功
- Bull Board 与 worker 正常启动

## 自动构建说明

当前项目的构建入口已经收敛到 `lzcat-apps` 仓库级共享 workflow。app 目录不再保留独立 `update-image.yml` 或 `trigger-build.yml`，相关配置统一维护在 `registry/repos/waoowaoo.json`。

## 上游项目简介

waoowaoo 是一款基于 AI 技术的短剧 / 漫画视频制作工具，支持从小说文本自动生成分镜、角色、场景，并制作成完整视频。

## 技术栈

- Framework: Next.js 15 + React 19
- Database: MySQL + Prisma ORM
- Queue: Redis + BullMQ
- Styling: Tailwind CSS v4
- Auth: NextAuth.js

## Homepage

访问 [https://github.com/waoowaooAI/waoowaoo](https://github.com/waoowaooAI/waoowaoo) 了解更多信息。

## License

MIT License
