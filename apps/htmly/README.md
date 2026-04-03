# HTMLy - 懒猫微服迁移项目

> [!NOTE]
> 本目录将上游 [danpros/htmly](https://github.com/danpros/htmly) 迁移为懒猫微服（LazyCat）应用，采用仓库内自定义 Dockerfile 构建 Apache + PHP 运行时，并保留 HTMLy 的 Web 安装流程。

## 上游信息

- 上游仓库: [danpros/htmly](https://github.com/danpros/htmly)
- 上游主页: [https://www.htmly.com](https://www.htmly.com)
- 当前上游版本: `3.1.1`
- 最新 GitHub Release 发布时间: `2025-11-03`
- 许可证: `GPL-2.0`
- 作者: `danpros`

## 迁移说明

HTMLy 是单服务、无数据库的 PHP 博客系统。上游源码依赖 Apache `.htaccess` 重写规则，并要求以下 PHP 扩展：

- `mbstring`
- `xml`
- `intl`
- `gd`
- `zip`

当前迁移包使用 `php:8.2-apache-bookworm` 作为基础镜像，并在构建时完成这些动作：

1. 下载对应 release tag 的源码归档。
2. 启用 Apache `rewrite`、`expires`、`headers`、`deflate` 模块。
3. 将 `/var/www/` 改为允许 `AllowOverride All`，保证 HTMLy 的 `.htaccess` 生效。
4. 对安装器做一层最小补丁，使其检查 `config/`、`content/`、`cache/` 的写权限，而不是要求整个站点根目录可写。

## 持久化目录

| 宿主路径 | 容器路径 | 用途 |
| --- | --- | --- |
| `/lzcapp/var/data/htmly/content` | `/var/www/html/content` | 文章、上传文件、主题内容 |
| `/lzcapp/var/data/htmly/cache` | `/var/www/html/cache` | HTMLy 文件缓存 |
| `/lzcapp/var/data/htmly/config` | `/var/www/html/config` | 站点配置、用户配置、评论配置 |

安装时 `setup_script` 会从镜像内的 `/opt/htmly-dist` 向以上目录补齐默认内容，但不会覆盖已有用户数据。

## 使用方式

安装应用后：

1. 打开懒猫分配的子域名。
2. 首次访问 `https://<your-domain>/install.php` 完成站点初始化。
3. 初始化完成后，通过 `https://<your-domain>/login` 进入后台。

如果只想以只读站点方式使用，也可以手动基于 `config/config.ini.example` 生成 `config.ini`，然后删除或忽略 `install.php`。

## 仓库文件

- [lzc-manifest.yml](/Volumes/ORICO/Development/Github/lzcat/lzcat-apps/apps/htmly/lzc-manifest.yml): LazyCat 应用定义
- [lzc-build.yml](/Volumes/ORICO/Development/Github/lzcat/lzcat-apps/apps/htmly/lzc-build.yml): LazyCat 打包配置
- [Dockerfile](/Volumes/ORICO/Development/Github/lzcat/lzcat-apps/apps/htmly/Dockerfile): 构建 Apache + PHP 运行时
- [install.php.patch](/Volumes/ORICO/Development/Github/lzcat/lzcat-apps/apps/htmly/install.php.patch): 对上游安装器的最小补丁

## 自动更新工作流

当前项目已经并入 `lzcat-apps` monorepo，自动更新由仓库级共享 workflow 负责：

1. 读取 `registry/repos/htmly.json` 的构建配置。
2. 跟踪上游 GitHub Release，解析最新 release tag。
3. 用 repo 内 `Dockerfile` 构建镜像，并回写 manifest 中的镜像地址与版本。
4. 统一构建 `.lpk` 并进入后续验收链路。

## 本地校验建议

如需继续验收，下一步建议：

1. 运行 `./scripts/local_build.sh htmly --check-only` 检查版本解析和配置完整性。
2. 运行实际构建，确认镜像能够正常拉取源码并完成 PHP 扩展安装。
3. 下载生成的 `.lpk` 后安装到 LazyCat 设备，验证 `install.php`、`/login`、文章创建和图片上传路径是否正常。
