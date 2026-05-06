# TaoYuan - 懒猫微服迁移项目

> [!NOTE]
> 本项目将上游 [setube/taoyuan](https://github.com/setube/taoyuan) 迁移为懒猫微服（LazyCat）应用，优先复用上游官方镜像，并提供自动跟踪上游 Release 的构建工作流。

**桃源乡** 是一款纯前端运行的文字版田园模拟经营游戏，灵感来自《星露谷物语》，采用像素风与中国风视觉设计。

## 上游信息

- 上游仓库: [setube/taoyuan](https://github.com/setube/taoyuan)
- 上游主页: [https://github.com/setube/taoyuan](https://github.com/setube/taoyuan)
- 当前上游版本: `2.2.0`
- 上游镜像: `ghcr.io/setube/taoyuan:2.2.0`
- 许可证: `CC BY-NC 4.0`
- 作者: `setube`

## 迁移说明

这个应用是纯静态 Web 游戏，容器内由 `nginx` 提供页面服务：

- 容器监听端口: `80`
- 懒猫入口: `http://taoyuan-web:80/`
- 必填环境变量: 无
- 容器持久化目录: 无

游戏进度和设置默认保存在浏览器 `localStorage` 中，不写入容器文件系统。应用内还自带存档导入导出和 WebDAV 云同步能力，因此本迁移不额外挂载 `/lzcapp/var` 数据目录。

## 当前补丁

上游 `2.2.0` 的 Web 版存档依赖 `localStorage`，且自动存档触发点在“结束一天”后。为避免玩家首次新开局、尚未睡过一晚就关闭页面时看起来像“每次打开都是新档”，当前迁移包额外覆盖了一版前端静态资源：

- 新游戏创建完成后立即写入初始存档槽位
- 通过 `content/` + `setup_script` 在安装时覆盖官方镜像中的站点文件

这是一层前端补丁，不改变上游镜像中的 nginx 和运行端口。

## 使用方式

安装应用后，直接通过懒猫分配的子域名访问即可开始游戏。

首次使用建议：

1. 创建新存档。
2. 如需跨设备同步，进入游戏内存档管理配置 WebDAV。
3. 如需备份，使用游戏内导出功能下载 `.tyx` 存档文件。

## 仓库文件

- [lzc-manifest.yml](/Users/lincoln/Develop/GitHub/lzcat/TaoYuan/lzc-manifest.yml): LazyCat 应用定义
- [lzc-build.yml](/Users/lincoln/Develop/GitHub/lzcat/TaoYuan/lzc-build.yml): LazyCat 打包配置
- [icon.png](/Users/lincoln/Develop/GitHub/lzcat/TaoYuan/icon.png): 应用图标

## 自动更新工作流

当前项目已经并入 `lzcat-apps` monorepo，自动更新由仓库级共享 workflow 负责：

1. 读取 `registry/repos/taoyuan.json` 的构建配置。
2. 拉取对应上游版本并同步补丁版 `content/`。
3. 构建或复制镜像，回写 manifest 中的镜像地址与版本。
4. 统一构建 `.lpk` 并进入后续验收链路。

## 本地校验建议

如需继续验收，下一步建议：

1. 运行仓库工作流，确认镜像复制和 `.lpk` 构建通过。
2. 下载生成的 `.lpk`，在懒猫环境安装。
3. 启动后检查首页是否能正常进入游戏、刷新后 `localStorage` 存档是否保留、WebDAV 上传下载是否正常。
