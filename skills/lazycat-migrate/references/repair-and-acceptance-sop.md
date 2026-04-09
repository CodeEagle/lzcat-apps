# 已发布应用修复 SOP

用于“用户反馈某个已经提交审核、已经上架、已经有 release `.lpk` 的应用启动失败 / 数据不持久化 / 配置丢失”这类场景。目标不是先猜，而是先复现线上包，再用修复包覆盖验证。

## 1. 先区分三个仓库角色

- `源码上游`：真实应用代码来源
- `移植仓库`：维护 `lzc-manifest.yml`、workflow、LazyCat 包的仓库
- `本地工作目录`：当前修复和验证目录

如果用户给的是 `CodeEagle/<app>` 这类自动构建仓库，要继续确认它 README / workflow 指向的真实上游，不要把移植仓库误当源码上游。

## 2. 先验 release 包，不要直接验本地改动

顺序固定：

1. 查目标移植仓库的 latest release / workflow 产物
2. 下载 `.lpk`
3. 安装 release 包
4. 先看 `lzc-cli app status`
5. 再进盒子看 compose / container 级状态

只有先复现线上包，后面的“修没修好”才有对照物。

## 3. `lzc-cli` 能力不够时，直接下钻盒子

如果 `lzc-cli app log` 不可用或信息太少，优先走盒子里的底层命令：

- `lzc-docker-compose ls`
- `lzc-docker-compose -p <project> ps -a`
- `lzc-docker-compose -p <project> logs --tail=200`
- `lzc-docker inspect <container>`
- `lzc-docker top <container>`
- `lzc-docker exec <container> ...`

验收口径从“包是否安装”下钻到“服务是否真正运行、是否监听端口、是否进入 healthy”。

## 4. 现网故障优先分四类

### A. release 包本身坏了

- 例：安装后主服务直接起不来，或 sidecar 一直等不到后端端口
- 做法：先保留 release 包作为复现场景，再在本地目录修 manifest / 脚本 / README

### B. 依赖就绪竞争

- 例：数据库、Redis、对象存储首次初始化慢，应用过早执行初始化或启动
- 做法：把等待逻辑放到应用 `command` 前半段，优先使用镜像内一定存在的工具
- 不要默认依赖 `mysqladmin`、`psql`、`redis-cli` 在应用镜像里存在
- 更稳妥的通用做法是使用应用镜像自带运行时做 TCP / HTTP 探测

### C. 路径与持久化不一致

- 例：代码同时写 `/app/data`、`/app/uploads`、`/app/output`
- 做法：先找真实读写路径，再统一映射到持久化目录
- 如果上游历史路径混乱，优先在启动脚本里补软链或兼容层，而不是只改 README

### C1. 启动时报“创建目录没权限”

- 默认根因不是“权限不够就 chmod 777”，而是写路径、挂载路径、运行用户、初始化时机四者不一致
- 先确认容器实际运行用户：`lzc-docker inspect <container>` 看 `Config.User`
- 再确认失败目录是不是上游真实写路径，而不是文档里随手写的示例路径
- 再确认该目录是否应该持久化；如果应该，就映射到 `binds`；如果不应该，也要落在镜像内该用户可写路径
- 对扫描清单里确认会被访问但当前不存在的目录，默认补预创建逻辑，不要等应用启动时报错后再回头加
- 如果上游代码混用旧目录和新目录，优先补软链或兼容目录，不要只修其中一个路径
- 只有在路径、挂载和运行用户都对齐后，才考虑最小必要的 `chown` / `chmod`
- 不要用“改成 root 跑”当常规解法，除非已确认上游就是 root-only 且没有更小的兼容修复

### D. 安装器 / Compose 转义问题

- 例：manifest 里的 shell 变量在容器里被提前展开成空字符串
- 做法：凡是要留到容器里执行的 shell 变量与 `$((...))`，在 manifest 里优先写成 `$$`
- 验证方式不是肉眼看 manifest，而是 `lzc-docker inspect` 看容器最终 `Cmd`

## 5. 看到 `Created` 不要误判成镜像拉取失败

如果 compose `ps -a` 里某个主服务是 `Created`：

- 先看 `depends_on` 是否卡在 `service_healthy`
- 再看 healthcheck 本身是否合理
- 再看主服务命令是否被安装器改写或被 shell 转义破坏

`Created` 常常表示“还没到启动条件”，不是“镜像没拉下来”。

## 6. 覆盖验收必须走两轮

第一轮：release 包

- 目标：证明问题真实存在

第二轮：本地修复包

- 目标：证明修复真的消掉了同一个问题

覆盖安装后至少检查：

- `lzc-cli app status <app-id>`
- `lzc-docker-compose -p <project> ps -a`
- 主服务日志是否完成初始化 / 启动 / 监听
- sidecar 或入口 health 是否转为 healthy

## 7. 发布前的最小闭环

对移植仓库修复现网问题时，最少要完成：

1. 本地目录修复
2. 本地预检（由 `full_migrate.py` 内置逻辑或手工检查 manifest 结构）
3. 本地 `lzc-cli project build`
4. 盒子安装修复包并验收
5. 把同样的改动同步回真实移植仓库

如果有权限，继续：

6. 推送修复分支
7. 创建 PR

## 8. 本轮可复用结论

- 已发布应用问题，优先“复现 release 包 -> 本地修复 -> 覆盖安装验证”
- `lzc-cli` 信息不足时，直接下钻 `debug.bridge` 暴露出的 Docker / Compose 能力
- 应用镜像内的依赖等待逻辑要避免假设额外客户端存在
- manifest 里的 shell 变量需要按容器最终命令视角检查转义是否正确
- 数据持久化问题要以“真实读写路径”而不是 README 描述为准
