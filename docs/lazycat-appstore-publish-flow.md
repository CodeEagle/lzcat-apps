# LazyCat App Store 上架流程

这个流程用于把已经通过安装验收和 Codex Browser Use 验收的 `.lpk` 提交到 LazyCat 开发者后台。

## 1. 准备提交材料

```bash
python3 scripts/prepare_store_submission.py <slug>
```

脚本会生成：

- `apps/<slug>/store-submission/submission.json`
- `apps/<slug>/store-submission/checklist.md`

它会阻止未通过 Browser Use 验收的应用进入上架准备阶段，并核对 `dist/<slug>.lpk` 内部 `manifest.yml` 的包名和版本。

## 2. 浏览器提交

1. 用 Codex Browser Use 打开 `project-config.json` 中的 `lazycat.developer_apps_url`。
2. 在开发者后台新建 App。
3. 根据 `submission.json` 填写应用名、包名、版本、简介、详情、关键词、主页和许可证。
4. 上传 `icon.png`、`acceptance/*.png` 截图和 `dist/<slug>.lpk`。
5. 停在最终创建、提交审核或发布按钮前，向用户确认。
6. 用户确认后再提交，并把后台状态或详情页链接写回本地记录。

## 3. 安全边界

- 上传 `.lpk`、截图和图标属于向 LazyCat 平台传输文件；只有用户明确要求时才执行。
- 创建或提交 App 会影响第三方平台上的开发者记录；即使用户要求执行，也要在最终提交按钮前进行一次明确确认。
- 如果页面要求验证码、支付、敏感账号信息或额外权限，停止并交给用户处理。

