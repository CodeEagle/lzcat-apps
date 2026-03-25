# cmms

本目录由 `scripts/bootstrap_migration.py` 生成，用于把上游 `Grashjs/cmms` 初始化为懒猫微服迁移项目。

## 上游项目
- Upstream Repo: Grashjs/cmms
- Homepage: https://atlas-cmms.com
- License: AGPL-3.0
- Author: Grashjs
- Version Strategy: `github_release` -> 当前初稿版本 `1.5.0`

## 当前迁移骨架
- Build Strategy: `upstream_dockerfile`
- Primary Subdomain: `cmms`
- Image Targets: `frontend`
- Service Port: `3000`

### Services
- `postgres` -> `registry.lazycat.cloud/placeholder/cmms:postgres`
- `api` -> `registry.lazycat.cloud/placeholder/cmms:api`
- `frontend` -> `registry.lazycat.cloud/placeholder/cmms:frontend`
- `minio` -> `registry.lazycat.cloud/placeholder/cmms:minio`

## 环境变量

| 变量名 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- |
| POSTGRES_DB | No | atlas | From compose service postgres |
| POSTGRES_USER | No | rootUser | From compose service postgres |
| POSTGRES_PASSWORD | No | mypassword | From compose service postgres |
| DB_URL | No | postgres/atlas | From compose service api |
| DB_USER | No | rootUser | From compose service api |
| DB_PWD | No | mypassword | From compose service api |
| PUBLIC_API_URL | No | http://localhost:8080 | From compose service api |
| PUBLIC_FRONT_URL | No | http://localhost:3000 | From compose service api |
| GCP_BUCKET_NAME | Yes | - | From compose service api |
| GCP_JSON | Yes | - | From compose service api |
| GCP_PROJECT_ID | Yes | - | From compose service api |
| MAIL_RECIPIENTS | Yes | - | From compose service api |
| SMTP_PWD | Yes | - | From compose service api |
| SMTP_USER | Yes | - | From compose service api |
| SMTP_HOST | No | smtp.gmail.com | From compose service api |
| SMTP_PORT | No | 587 | From compose service api |
| SPRING_PROFILES_ACTIVE | Yes | - | From compose service api |
| JWT_SECRET_KEY | No | sD1HBM6ngcaDLMzDqgA9Pn9LEECNAp0C1EOHIR/D+q4= | From compose service api |
| MINIO_ENDPOINT | No | http://minio:9000 | From compose service api |
| MINIO_BUCKET | No | atlas-bucket | From compose service api |
| MINIO_ACCESS_KEY | No | minio | From compose service api |
| MINIO_SECRET_KEY | No | minio123 | From compose service api |
| STORAGE_TYPE | No | minio | From compose service api |
| PUBLIC_MINIO_ENDPOINT | No | http://localhost:9000 | From compose service api |
| INVITATION_VIA_EMAIL | No | false | From compose service frontend |
| ENABLE_EMAIL_NOTIFICATIONS | No | false | From compose service api |
| ENABLE_SSO | No | false | From compose service frontend |
| OAUTH2_PROVIDER | No | - | From compose service frontend |
| OAUTH2_CLIENT_ID | Yes | - | From compose service api |
| OAUTH2_CLIENT_SECRET | Yes | - | From compose service api |
| LICENSE_KEY | No | - | From compose service api |
| LICENSE_FINGERPRINT_REQUIRED | No | true | From compose service api |
| LICENSE_FILE_PATH | No | - | From compose service api |
| ALLOWED_ORGANIZATION_ADMINS | No | - | From compose service api |
| LOGO_PATHS | No | - | From compose service frontend |
| CUSTOM_COLORS | No | - | From compose service frontend |
| BRAND_CONFIG | No | - | From compose service frontend |
| PADDLE_API_KEY | No | - | From compose service api |
| PADDLE_WEBHOOK_SECRET_KEY | No | - | From compose service api |
| PADDLE_ENVIRONMENT | No | sandbox | From compose service frontend |
| ENABLE_CORS | No | true | From compose service api |
| KEYGEN_PRODUCT_TOKEN | No | - | From compose service api |
| MAIL_TYPE | No | smtp | From compose service api |
| SENDGRID_API_KEY | No | - | From compose service api |
| SENDGRID_FROM_EMAIL | No | - | From compose service api |
| SENDGRID_CONTACT_LIST_ID | No | - | From compose service api |
| RECAPTCHA_SECRET_KEY | No | - | From compose service api |
| API_URL | No | http://localhost:8080 | From compose service frontend |
| GOOGLE_KEY | No | - | From compose service frontend |
| GOOGLE_TRACKING_ID | No | - | From compose service frontend |
| CLOUD_VERSION | No | false | From compose service frontend |
| NODE_ENV | No | production | From compose service frontend |
| DEMO_LINK | No | - | From compose service frontend |
| PADDLE_SECRET_TOKEN | No | - | From compose service frontend |
| RECAPTCHA_SITE_KEY | No | - | From compose service frontend |
| MINIO_ROOT_USER | No | minio | From compose service minio |
| MINIO_ROOT_PASSWORD | No | minio123 | From compose service minio |

## 数据目录

| 宿主路径 | 容器路径 | 说明 |
| --- | --- | --- |
| /lzcapp/var/db/cmms/postgres | /var/lib/postgresql/data | From compose service postgres |
| /lzcapp/var/data/cmms/api/images | /app/static/images | From compose service api |
| /lzcapp/var/data/cmms/api/config | /app/static/config | From compose service api |
| /lzcapp/var/data/cmms/minio | /data | From compose service minio |

## 首次启动/验收提醒

- 自动扫描到 compose 文件：docker-compose.yml
- 主服务推断为 `frontend`，入口端口 `3000`。
- 依赖服务镜像已写入 dependencies，首次完整构建时会自动 copy-image。
- 扫描到 env 示例文件：.env.example, .env.example
- 扫描到 README：README.MD, README.md, README.md
- frontend 启动前会显式 export 运行时变量，避免空字符串变量在 runtime-env-cra 阶段被丢失。

## 下一步

1. 补完 `UPSTREAM_DEPLOYMENT_CHECKLIST.md`，把真实入口、环境变量、写路径和初始化动作全部核实清楚。
2. 按真实部署拓扑修正 `lzc-manifest.yml`，不要直接沿用占位镜像、端口或命令。
3. 如果是源码构建，补齐 `Dockerfile` / `Dockerfile.template`、`content/`、`overlay_paths` 等资产。
4. 初稿补全后执行 `./scripts/local_build.sh cmms --check-only`，再进入实际构建与验收。
