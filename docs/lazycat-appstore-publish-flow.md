# LazyCat App Store 上架流程

这个流程用于把已经通过安装验收和 Codex Browser Use 验收的 `.lpk` 提交到 LazyCat 开发者后台。

## 1. 准备提交材料

先生成网页内容区域截图，禁止使用系统截图、桌面截图或带浏览器外框的截图：

```bash
python3 scripts/capture_web_screenshot.py <slug> \
  --url https://<slug>.<box-domain>/ \
  --wait-text "<页面内可见文案>"
```

截图会写入 `apps/<slug>/acceptance/`，并生成 `web-screenshots.json` 记录截图来源、URL 和 viewport。这个 metadata 是后续上架准备的强制门禁。

```bash
python3 scripts/prepare_store_submission.py <slug>
```

脚本会生成：

- `apps/<slug>/store-submission/submission.json`
- `apps/<slug>/store-submission/checklist.md`

它会阻止未通过 Browser Use 验收、缺少网页内截图 metadata 的应用进入上架准备阶段，并核对 `dist/<slug>.lpk` 内部 `manifest.yml` 的包名和版本。

## 2. 浏览器提交

1. 用 Codex Browser Use 打开 `project-config.json` 中的 `lazycat.developer_apps_url`。
2. 在开发者后台新建 App。
3. 根据 `submission.json` 填写应用名、包名、版本、简介、详情、关键词、主页和许可证。
4. 对移植上游开源项目，取消“应用程序为原创开发或本人是源作者”，填写原作者/组织名称和源项目地址；只有原创项目或本人就是源作者时才保留该声明。
5. 上传 `apps/<slug>/store-submission/assets/icon.png`、`apps/<slug>/store-submission/assets/screenshots/*.png` 和 `dist/<slug>.lpk`。
6. 停在最终创建、提交审核或发布按钮前，向用户确认。
7. 用户确认后再提交，并把后台状态或详情页链接写回本地记录。

## 3. 安全边界

- 上传 `.lpk`、截图和图标属于向 LazyCat 平台传输文件；只有用户明确要求时才执行。
- 创建或提交 App 会影响第三方平台上的开发者记录；即使用户要求执行，也要在最终提交按钮前进行一次明确确认。
- 移植应用不得勾选原创/源作者声明；必须优先填写上游作者、上游仓库和许可证信息。
- 如果页面要求验证码、支付、敏感账号信息或额外权限，停止并交给用户处理。
