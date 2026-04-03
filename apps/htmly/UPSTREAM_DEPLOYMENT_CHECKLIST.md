# HTMLy Upstream Deployment Checklist

## 已确认字段
- PROJECT_NAME: HTMLy
- PROJECT_SLUG: htmly
- UPSTREAM_REPO: danpros/htmly
- UPSTREAM_URL: https://github.com/danpros/htmly
- HOMEPAGE: https://www.htmly.com
- LICENSE: GPL-2.0
- AUTHOR: danpros
- VERSION: 3.1.1
- IMAGE: php:8.2-apache-bookworm (target_repo_dockerfile)
- PORT: 80
- CHECK_STRATEGY: github_release
- BUILD_STRATEGY: target_repo_dockerfile

## 真实启动入口
- 上游无官方 Dockerfile、无正式 compose 部署入口。
- 标准安装方式是将源码解压到 Web 根目录后，通过 `install.php` 完成初始化。
- 根目录 `.htaccess` 依赖 Apache `mod_rewrite` 将非静态文件路由到 `index.php`。
- 因此当前 LazyCat 迁移采用自定义 Apache + PHP 镜像，而不是复用“官方镜像”。

## 真实环境要求
- PHP >= 7.2
- PHP extensions: `mbstring`, `xml`, `intl`, `gd`, `zip`
- 安装器会检查 HTTPS wrapper，可用 `openssl` 即可
- Apache 场景下需要启用 `mod_rewrite`

## 真实读写路径
- `/var/www/html/config`
  - `config.ini`
  - `comments.ini`
  - `users/*.ini`
  - `config/.htaccess`
- `/var/www/html/content`
  - 文章内容
  - 上传图片
  - 主题相关可写数据
- `/var/www/html/cache`
  - 页面缓存
  - `installedVersion.json`

## 首次启动与初始化
- 首次访问 `install.php` 生成 `config/config.ini` 与管理员用户配置。
- 安装成功后，页面会跳转到 `add/content?type=post`。
- 上游代码会尝试删除 `install.php`；当前迁移改为静默尝试，不把“根目录不可写”视为安装失败。

## 外部依赖
- 无数据库依赖
- 无 Redis / 对象存储依赖
- 可选第三方集成:
  - Facebook comments
  - Disqus
  - Google / Cloudflare login protection
  - Google Analytics / gtag

## 当前 LazyCat 方案
- 单服务 `htmly`
- 入口: `http://htmly:80/`
- 构建方式: `apps/htmly/Dockerfile`
- 数据持久化:
  - `/lzcapp/var/data/htmly/config -> /var/www/html/config`
  - `/lzcapp/var/data/htmly/content -> /var/www/html/content`
  - `/lzcapp/var/data/htmly/cache -> /var/www/html/cache`
- 安装时通过 `setup_script` 把镜像内默认文件补齐到持久化目录

## 已知风险 / 待验收项
- [ ] 验证 PHP 8.2 下 `install.php`、登录、发文、上传图片流程无兼容性问题
- [ ] 验证 `.htaccess` 在 LazyCat 环境下的 Apache rewrite 生效
- [ ] 验证升级后持久化目录不会被镜像内默认内容覆盖
- [ ] 验证 `config/.htaccess` 在 bind mount 后已被正确种入数据目录

## 退出条件
- [ ] `./scripts/local_build.sh htmly --check-only` 通过
- [ ] Docker 构建通过，镜像内 Apache/PHP 扩展完整
- [ ] `.lpk` 安装后可完成 Web 初始化
- [ ] `/login`、发文、图片上传、缓存写入全部正常
