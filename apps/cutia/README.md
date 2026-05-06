# Cutia - 懒猫微服自动构建项目

> [!NOTE]
> 本项目是 [Cutia](https://cutia.msgbyte.com) 的懒猫微服（LazyCat）自动构建项目，用于自动跟踪上游代码更新并构建镜像发布到懒猫应用商店。

> [!IMPORTANT]
> **Icon 规范**：`icon.png` 文件大小不得超过 **200KB**，建议使用 512x512 像素的 PNG 格式图片。

**Cutia - 开源浏览器视频编辑器**

## 关于本项目

本项目会自动监测 [msgbyte/cutia](https://github.com/msgbyte/cutia) 的代码更新，当有新版本时：
1. 从源码构建 Docker 镜像
2. 发布到懒猫镜像源
3. 更新 `lzc-manifest.yml` 配置

## Cutia 简介

Cutia 是一个开源的浏览器视频编辑器，是 CapCut 的开源替代品。

### 功能特性

- 隐私优先 - 本地优先的编辑理念
- 基于时间线的多轨道工作流程
- 实时预览编辑效果
- 无水印导出
- 开源免费

### 技术栈

- Next.js 16
- Bun (包管理器)
- TypeScript
- PostgreSQL + Redis (可选)

## 目录说明

| 宿主机路径 | 容器内路径 | 用途 |
|------------|------------|------|
| `/lzcapp/var/data/cutia` | `/data` | 应用数据 |
| `/lzcapp/var/db/cutia/postgres` | `/var/lib/postgresql/data` | PostgreSQL 数据库 |

## 环境变量说明

| 变量 | 说明 | 示例 |
|------|------|------|
| `BETTER_AUTH_SECRET` | Better Auth 认证密钥 | (需自行设置) |
| `UPSTASH_REDIS_REST_TOKEN` | Redis 认证令牌 | (需自行设置) |

## 首次配置

1. 部署应用后访问 Web 界面
2. 注册账号即可开始使用

## Homepage

访问 [https://cutia.msgbyte.com](https://cutia.msgbyte.com) 了解更多信息。

## License

MIT License
