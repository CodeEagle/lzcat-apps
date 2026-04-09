# docker2lzc 集成规范

`docker2lzc` 是社区工具，适合把 Compose 项目快速转成初稿。这里定义“怎么用”和“用完后必须做什么”。

## 1. 适用条件
- 上游明确提供 `docker-compose.yml`
- 需要快速梳理服务、端口、环境变量、挂载与路由候选
- 团队接受“先出草稿再回归标准流程”

不适用：
- 非 Compose 项目（纯镜像、源码构建、二进制分发）
- 需要严格对齐当前 monorepo 已集成的正式发布链路，且团队不接受中间草稿回归
- 已进入修复/回归阶段（此时优先走 `repair-and-acceptance-sop`）

## 2. 推荐使用方式

仅把它用于 `[4/10]` 到 `[6/10]` 的初稿生成，不要跨到构建和发布阶段。

```bash
npm install -g docker2lzc
docker2lzc
```

## 3. 产物回归要求（强制）

工具跑完后，必须把产物对齐到本仓库标准：

- 文件名统一到 `lzc-manifest.yml`、`lzc-build.yml`、`README.md`、`icon.png`
- 如果工具生成 `manifest.yml`，必须合并回 `lzc-manifest.yml`，不能双轨维护
- 如果工具直接产出 `.lpk`，只作为本地参考，不作为最终交付包
- 最终镜像地址必须收敛到 `registry.lazycat.cloud/...`
- 所有镜像（包含依赖镜像）都必须通过 `lzc-cli appstore copy-image` 获取加速地址后再写入 manifest
- 执行 `copy-image` 前先查缓存（`lzc-cli appstore my-images` 或等价方式）；命中时优先复用，未命中再复制
- `version` 必须是纯 semver `X.Y.Z`
- `application.upstreams[].backend` 必须是真实服务名 + 容器内端口

## 4. 用后必跑流程

即使使用了 `docker2lzc`，后续步骤也不能省：

1. 预检（由 `full_migrate.py` 内置逻辑自动完成）
2. 构建（由 `full_migrate.py` 调用 `run_build.py`，或通过 `local_build.sh` 单独触发）
3. 下载 `.lpk`（由 `full_migrate.py` 自动完成）
4. 安装验收（由 `full_migrate.py` 或独立使用 `skills/lazycat-migrate/scripts/install-and-verify.sh`）

只要这条链路没走完，就不能判定“迁移完成”。

## 5. 高频偏差与修正

- 偏差：工具输出镜像仍是上游 registry，或只处理了主镜像
- 修正：对所有服务镜像逐一执行 `lzc-cli appstore copy-image`，统一改为返回的 `registry.lazycat.cloud/...` 地址后再构建

- 偏差：工具输出 version 非纯 semver
- 修正：拆分 `source_version` 与 `build_version`，manifest 只保留 `build_version`

- 偏差：工具直接生成 `.lpk` 后即交付
- 修正：按本 skill 的 workflow 和验收链路重建并验证最终包

- 偏差：路由看起来可访问，但服务健康检查失败
- 修正：按 `workflow-and-validation.md` 继续做状态、日志和容器级验证
