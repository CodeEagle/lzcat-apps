# Atlas CMMS (LazyCat Migration)

这是 [Grashjs/cmms](https://github.com/Grashjs/cmms) 的 LazyCat 迁移项目。

## 上游信息

- 上游仓库: https://github.com/Grashjs/cmms
- 官网: https://atlas-cmms.com
- 许可证: AGPL-3.0
- 上游版本: v1.5.0

## 应用说明

Atlas CMMS 是一个面向资产、工单与维护流程的自托管 CMMS 平台，包含前端、后端、PostgreSQL 与 MinIO 四个服务。

- `frontend`：Web 入口
- `api`：后端接口与业务逻辑
- `postgres`：关系型数据库
- `minio`：对象存储

安装后通过 `https://cmms.<your-lazycat-domain>` 访问。

## 必填环境变量

| 变量名 | 说明 |
| --- | --- |
| `POSTGRES_USER` | PostgreSQL 用户名 |
| `POSTGRES_PWD` | PostgreSQL 密码 |
| `MINIO_USER` | MinIO 管理员用户名 |
| `MINIO_PASSWORD` | MinIO 管理员密码 |
| `JWT_SECRET_KEY` | 后端 JWT 密钥（建议 `openssl rand -base64 32` 生成） |

## 常用可选环境变量

| 变量名 | 说明 | 默认值 |
| --- | --- | --- |
| `PUBLIC_FRONT_URL` | 前端公开地址 | `http://localhost:3000` |
| `PUBLIC_API_URL` | 后端公开地址 | `http://localhost:8080` |
| `PUBLIC_MINIO_ENDPOINT` | MinIO 对外地址 | `http://localhost:9000` |
| `ENABLE_EMAIL_NOTIFICATIONS` | 是否启用邮件通知 | `false` |
| `ENABLE_SSO` | 是否启用单点登录 | `false` |

## 数据目录

| 路径 | 用途 |
| --- | --- |
| `/lzcapp/var/data/cmms/logo` | Logo 与品牌图片 |
| `/lzcapp/var/data/cmms/config` | 后端自定义配置 |
| `/lzcapp/var/db/cmms/postgres` | PostgreSQL 数据 |
| `/lzcapp/var/data/cmms/minio` | MinIO 数据 |

## 首次启动说明

1. 建议先设置强密码和随机 `JWT_SECRET_KEY`。
2. 首次启动后等待数据库与对象存储初始化。
3. 访问 Web 页面完成组织与管理员初始化配置。

## 参考文档

- 官方文档: https://docs.atlas-cmms.com
- 上游 Docker Compose: https://github.com/Grashjs/cmms/blob/main/docker-compose.yml
