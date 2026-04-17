# Multica

开源 AI 代理管理平台，将 AI 编程代理转变为真正的团队成员。

## 架构

| 服务 | 技术 | 端口 |
|------|------|------|
| Frontend | Next.js 16 (standalone) | 3000 |
| Backend | Go + WebSocket | 8080 |
| Database | PostgreSQL 17 + pgvector | 5432 |

## 访问

安装后访问：`https://multica.<device>.lazycat.cloud`

## 首次登录（免密）

1. 打开应用，在邮箱字段输入任意邮箱（或由安装时配置的 `login_email` 自动填充）
2. 点击「发送验证码」
3. **验证码字段输入 `888888`**（开发模式下的万能验证码）
4. 点击「验证」即可登录

> 验证码 `888888` 在未配置 `RESEND_API_KEY` 的情况下始终有效（非生产模式）。

## 免密登录（LazyCat）

应用已配置 LazyCat Inject，会自动填充邮箱和验证码。只需在安装时设置 `login_email` deploy param，即可实现一键登录。

## 数据持久化

| 目录 | 说明 |
|------|------|
| `/lzcapp/var/data/postgres/` | PostgreSQL 数据库文件 |
| `/lzcapp/var/data/uploads/` | 用户上传文件 |

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `JWT_SECRET` | JWT 签名密钥 | 已预设（生产环境请修改） |
| `RESEND_API_KEY` | Resend 邮件服务 API Key | 空（禁用真实邮件，启用 888888 主码） |
| `DATABASE_URL` | PostgreSQL 连接串 | 自动配置 |

## 上游项目

- GitHub: https://github.com/multica-ai/multica
- 本地 fork: https://github.com/CodeEagle/multica

## 构建说明

- Backend：从 `Dockerfile` 构建 Go 二进制
- Frontend：从 `Dockerfile.web` 构建 Next.js standalone 输出
  - 构建参数 `REMOTE_API_URL=http://multica-backend:8080`（服务端代理到后端 API）
- Database：使用官方 `pgvector/pgvector:pg17` 镜像
