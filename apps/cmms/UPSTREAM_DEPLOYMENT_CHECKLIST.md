# cmms Upstream Deployment Checklist

## 已确认字段
- PROJECT_NAME: cmms
- PROJECT_SLUG: cmms
- UPSTREAM_REPO: Grashjs/cmms
- UPSTREAM_URL: https://github.com/Grashjs/cmms
- HOMEPAGE: https://atlas-cmms.com
- LICENSE: AGPL-3.0
- AUTHOR: Grashjs
- VERSION: 1.5.0
- IMAGE: TODO
- PORT: 3000
- CHECK_STRATEGY: github_release
- BUILD_STRATEGY: upstream_dockerfile

## 预填环境变量
- `POSTGRES_DB`: From compose service postgres (required=False)
- `POSTGRES_USER`: From compose service postgres (required=True)
- `POSTGRES_PASSWORD`: From compose service postgres (required=True)
- `DB_URL`: From compose service api (required=False)
- `DB_USER`: From compose service api (required=True)
- `DB_PWD`: From compose service api (required=True)
- `PUBLIC_API_URL`: From compose service api (required=False)
- `PUBLIC_FRONT_URL`: From compose service api (required=True)
- `GCP_BUCKET_NAME`: From compose service api (required=True)
- `GCP_JSON`: From compose service api (required=True)
- `GCP_PROJECT_ID`: From compose service api (required=True)
- `MAIL_RECIPIENTS`: From compose service api (required=True)
- `SMTP_PWD`: From compose service api (required=True)
- `SMTP_USER`: From compose service api (required=True)
- `SMTP_HOST`: From compose service api (required=True)
- `SMTP_PORT`: From compose service api (required=True)
- `SPRING_PROFILES_ACTIVE`: From compose service api (required=True)
- `JWT_SECRET_KEY`: From compose service api (required=True)
- `MINIO_ENDPOINT`: From compose service api (required=False)
- `MINIO_BUCKET`: From compose service api (required=False)
- `MINIO_ACCESS_KEY`: From compose service api (required=True)
- `MINIO_SECRET_KEY`: From compose service api (required=True)
- `STORAGE_TYPE`: From compose service api (required=False)
- `PUBLIC_MINIO_ENDPOINT`: From compose service api (required=False)
- `INVITATION_VIA_EMAIL`: From compose service frontend (required=False)
- `ENABLE_EMAIL_NOTIFICATIONS`: From compose service api (required=False)
- `ENABLE_SSO`: From compose service frontend (required=False)
- `OAUTH2_PROVIDER`: From compose service frontend (required=False)
- `OAUTH2_CLIENT_ID`: From compose service api (required=True)
- `OAUTH2_CLIENT_SECRET`: From compose service api (required=True)
- `LICENSE_KEY`: From compose service api (required=False)
- `LICENSE_FINGERPRINT_REQUIRED`: From compose service api (required=False)
- `LICENSE_FILE_PATH`: From compose service api (required=False)
- `ALLOWED_ORGANIZATION_ADMINS`: From compose service api (required=False)
- `LOGO_PATHS`: From compose service frontend (required=False)
- `CUSTOM_COLORS`: From compose service frontend (required=False)
- `BRAND_CONFIG`: From compose service frontend (required=False)
- `PADDLE_API_KEY`: From compose service api (required=False)
- `PADDLE_WEBHOOK_SECRET_KEY`: From compose service api (required=False)
- `PADDLE_ENVIRONMENT`: From compose service frontend (required=False)
- `ENABLE_CORS`: From compose service api (required=False)
- `KEYGEN_PRODUCT_TOKEN`: From compose service api (required=False)
- `MAIL_TYPE`: From compose service api (required=False)
- `SENDGRID_API_KEY`: From compose service api (required=False)
- `SENDGRID_FROM_EMAIL`: From compose service api (required=False)
- `SENDGRID_CONTACT_LIST_ID`: From compose service api (required=False)
- `RECAPTCHA_SECRET_KEY`: From compose service api (required=False)
- `API_URL`: From compose service frontend (required=True)
- `GOOGLE_KEY`: From compose service frontend (required=False)
- `GOOGLE_TRACKING_ID`: From compose service frontend (required=False)
- `CLOUD_VERSION`: From compose service frontend (required=False)
- `NODE_ENV`: From compose service frontend (required=False)
- `DEMO_LINK`: From compose service frontend (required=False)
- `PADDLE_SECRET_TOKEN`: From compose service frontend (required=False)
- `RECAPTCHA_SITE_KEY`: From compose service frontend (required=False)
- `MINIO_ROOT_USER`: From compose service minio (required=True)
- `MINIO_ROOT_PASSWORD`: From compose service minio (required=True)
- `POSTGRES_PWD`: From .env.example (required=False)
- `MINIO_USER`: From .env.example (required=False)
- `MINIO_PASSWORD`: From .env.example (required=False)

## 预填数据路径
- `/var/lib/postgresql/data` <= `/lzcapp/var/db/cmms/postgres` (From compose service postgres)
- `/app/static/images` <= `/lzcapp/var/data/cmms/api/images` (From compose service api)
- `/app/static/config` <= `/lzcapp/var/data/cmms/api/config` (From compose service api)
- `/data` <= `/lzcapp/var/data/cmms/minio` (From compose service minio)

## 预填启动说明
- 自动扫描到 compose 文件：docker-compose.yml
- 主服务推断为 `frontend`，入口端口 `3000`。
- 依赖服务镜像已写入 dependencies，首次完整构建时会自动 copy-image。
- 扫描到 env 示例文件：.env.example, .env.example
- 扫描到 README：README.MD, README.md, README.md

## 必扫清单
- [ ] Dockerfile / Containerfile / compose / helm / entrypoint / startup script 的真实启动入口
- [ ] README / 部署文档 / `.env.example` / sample config 中声明的环境变量
- [ ] 数据目录、配置目录、缓存目录、上传目录、日志目录、临时目录的真实读写路径
- [ ] 首次启动初始化命令、迁移命令、建库建表命令、管理员初始化命令
- [ ] 数据库、Redis、对象存储、auth / OAuth / JWT / callback / secret 等外部依赖配置
- [ ] 每个真实目录是否需要预创建、由谁创建、以什么 owner/group/mode 创建

## 当前服务拓扑初稿
- `postgres`
  image: `registry.lazycat.cloud/placeholder/cmms:postgres`
  binds: `/lzcapp/var/db/cmms/postgres:/var/lib/postgresql/data`
  environment: `POSTGRES_DB=atlas, POSTGRES_USER, POSTGRES_PASSWORD=${POSTGRES_PWD}`
- `api`
  image: `registry.lazycat.cloud/placeholder/cmms:api`
  depends_on: `postgres, minio`
  binds: `/lzcapp/var/data/cmms/api/images:/app/static/images, /lzcapp/var/data/cmms/api/config:/app/static/config`
  environment: `DB_URL=postgres/atlas, DB_USER=${POSTGRES_USER}, DB_PWD=${POSTGRES_PWD}, PUBLIC_API_URL=https://cmms.${LAZYCAT_BOX_DOMAIN}/api, PUBLIC_FRONT_URL, GCP_BUCKET_NAME, GCP_JSON, GCP_PROJECT_ID, MAIL_RECIPIENTS, SMTP_PWD, SMTP_USER, SMTP_HOST, SMTP_PORT, SPRING_PROFILES_ACTIVE, JWT_SECRET_KEY, MINIO_ENDPOINT=http://minio:9000, MINIO_BUCKET=atlas-bucket, MINIO_ACCESS_KEY=${MINIO_USER}, MINIO_SECRET_KEY=${MINIO_PASSWORD}, STORAGE_TYPE=${STORAGE_TYPE:-minio}, PUBLIC_MINIO_ENDPOINT=https://cmms.${LAZYCAT_BOX_DOMAIN}/minio, INVITATION_VIA_EMAIL=${INVITATION_VIA_EMAIL:-false}, ENABLE_EMAIL_NOTIFICATIONS=${ENABLE_EMAIL_NOTIFICATIONS:-false}, ENABLE_SSO=${ENABLE_SSO:-false}, OAUTH2_PROVIDER, OAUTH2_CLIENT_ID, OAUTH2_CLIENT_SECRET, LICENSE_KEY=${LICENSE_KEY:-}, LICENSE_FINGERPRINT_REQUIRED=${LICENSE_FINGERPRINT_REQUIRED:-true}, LICENSE_FILE_PATH=${LICENSE_FILE_PATH:-}, ALLOWED_ORGANIZATION_ADMINS=${ALLOWED_ORGANIZATION_ADMINS:-}, LOGO_PATHS, CUSTOM_COLORS, BRAND_CONFIG, PADDLE_API_KEY=${PADDLE_API_KEY:-}, PADDLE_WEBHOOK_SECRET_KEY=${PADDLE_WEBHOOK_SECRET_KEY:-}, PADDLE_ENVIRONMENT=${PADDLE_ENVIRONMENT:-sandbox}, ENABLE_CORS=${ENABLE_CORS:-true}, KEYGEN_PRODUCT_TOKEN=${KEYGEN_PRODUCT_TOKEN:-}, MAIL_TYPE=${MAIL_TYPE:-smtp}, SENDGRID_API_KEY=${SENDGRID_API_KEY:-}, SENDGRID_FROM_EMAIL=${SENDGRID_FROM_EMAIL:-}, SENDGRID_CONTACT_LIST_ID=${SENDGRID_CONTACT_LIST_ID:-}, RECAPTCHA_SECRET_KEY=${RECAPTCHA_SECRET_KEY:-}`
- `frontend`
  image: `registry.lazycat.cloud/placeholder/cmms:frontend`
  depends_on: `api`
  environment: `API_URL=https://cmms.${LAZYCAT_BOX_DOMAIN}/api, GOOGLE_KEY=${GOOGLE_KEY:-}, GOOGLE_TRACKING_ID=${GOOGLE_TRACKING_ID:-}, INVITATION_VIA_EMAIL=${INVITATION_VIA_EMAIL:-false}, CLOUD_VERSION=${CLOUD_VERSION:-false}, NODE_ENV=production, ENABLE_SSO=${ENABLE_SSO:-false}, OAUTH2_PROVIDER=${OAUTH2_PROVIDER:-}, LOGO_PATHS=${LOGO_PATHS:-}, CUSTOM_COLORS=${CUSTOM_COLORS:-}, BRAND_CONFIG=${BRAND_CONFIG:-}, DEMO_LINK=${DEMO_LINK:-}, PADDLE_SECRET_TOKEN=${PADDLE_SECRET_TOKEN:-}, PADDLE_ENVIRONMENT=${PADDLE_ENVIRONMENT:-sandbox}, RECAPTCHA_SITE_KEY=${RECAPTCHA_SITE_KEY:-}`
- `minio`
  image: `registry.lazycat.cloud/placeholder/cmms:minio`
  binds: `/lzcapp/var/data/cmms/minio:/data`
  environment: `MINIO_ROOT_USER=${MINIO_USER}, MINIO_ROOT_PASSWORD=${MINIO_PASSWORD}`

## 退出条件
- [ ] 入口、端口、环境变量、真实写路径、初始化命令、数据库/auth 配置全部确认完毕
- [ ] `lzc-manifest.yml` 中的镜像地址已替换为真实的 `registry.lazycat.cloud/...`
- [ ] 构建策略相关文件（Dockerfile / template / content / overlay）已补齐
- [ ] 可以进入预检、构建、下载 `.lpk`、安装验收阶段
