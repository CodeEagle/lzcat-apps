# Shadmin - 懒猫微服迁移项目

> [!NOTE]
> 本目录将 [ahaodev/shadmin](https://github.com/ahaodev/shadmin) 迁移为懒猫微服单容器应用，当前路线基于上游源码构建，并直接由 `CodeEagle/lzcat-apps` monorepo 负责构建与产包。

**Shadmin** 是一个基于 Go + React 的 RBAC 权限管理系统，内置后台管理界面、认证与角色权限控制。

## 上游信息

- Upstream repo: [ahaodev/shadmin](https://github.com/ahaodev/shadmin)
- Homepage: [github.com/ahaodev/shadmin](https://github.com/ahaodev/shadmin)
- Latest upstream commit used for initial migration: `6ed2c203af236b598e83127e34a8553c16a5b6c5` (`2026-03-20`)
- Upstream app version used for initial migration: `2.1.0`
- License used here: `MIT`

> [!IMPORTANT]
> 上游文档把日志目录写成 `./logs`，但代码实际写入的是 `./.logs/`。本迁移按代码真实写路径挂载和预创建目录。

## 迁移说明

- 运行形态：单容器 Go + React 应用
- 容器入口：`http://shadmin:55667/`
- 懒猫入口：应用首页
- 对外能力：
  - `GET /`：后台管理 Web UI
  - `POST /api/v1/auth/login`：登录接口
  - `GET /swagger/index.html`：Swagger 文档

## 为什么不是直接复用镜像

上游仓库当前提供的是源码仓库，没有稳定发布的镜像 tag 或 release 包可直接复用，因此这里采用源码构建，并在构建阶段：

1. 拉取固定 upstream commit 的源码
2. 构建 React 前端
3. 编译包含嵌入式前端资源的 Go 二进制
4. 打包为单容器运行镜像

## 数据目录

| 宿主机路径 | 容器内路径 | 用途 |
|------------|------------|------|
| `/lzcapp/var/db` | `/app/.database` | SQLite 数据库 |
| `/lzcapp/var/uploads` | `/app/uploads` | 本地文件存储 |
| `/lzcapp/var/logs` | `/app/.logs` | 应用日志 |

## 关键环境变量

- `APP_ENV=production`
- `PORT=:55667`
- `DB_TYPE=sqlite`
- `ACCESS_TOKEN_SECRET=${LAZYCAT_APP_ID}-${LAZYCAT_BOX_DOMAIN}-access-token`
- `REFRESH_TOKEN_SECRET=${LAZYCAT_APP_ID}-${LAZYCAT_BOX_DOMAIN}-refresh-token`
- `ADMIN_USERNAME=admin`
- `ADMIN_PASSWORD=change-me-123`
- `ADMIN_EMAIL=admin@shadmin.local`
- `STORAGE_TYPE=disk`
- `STORAGE_BASE_PATH=/app/uploads`

## 首次启动

1. 安装并启动应用
2. 打开应用首页
3. 使用默认账号 `admin` / `change-me-123` 登录
4. 登录后立即在系统中修改管理员密码

> 默认管理员仅在首次初始化数据库时创建。之后即使修改环境变量，也不会自动覆盖已有管理员密码。

## 已知注意点

- 上游代码里声明了 `/api/v1/health` 为公开接口，但当前仓库中没有实现对应路由，因此本迁移使用首页 `/` 作为健康检查探针
- 默认数据库为 SQLite；如需 PostgreSQL 或 MySQL，可自行调整 `DB_TYPE` 和 `DB_DSN`
- 默认文件存储为本地磁盘；如需 MinIO，可切换 `STORAGE_TYPE=minio` 并补齐 `S3_*` 变量

## 本目录文件

- `lzc-manifest.yml`：懒猫应用定义
- `lzc-build.yml`：构建打包配置
- `Dockerfile`：源码构建镜像
- `icon.png`：应用图标

## 构建方式

当前 `shadmin` 不再使用独立 GitHub 仓库构建。构建、镜像复制、产包与发布统一走 `CodeEagle/lzcat-apps` monorepo 现有入口：

- GitHub Actions：monorepo 根目录下的 `.github/workflows/trigger-build.yml`
- 本地验证：`scripts/local_build.sh shadmin ...`
