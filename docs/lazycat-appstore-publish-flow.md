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

## 2. Playground 图文攻略草稿

攻略面向最终用户，不是迁移记录、测试记录或发布 checklist。生成或人工整理 `apps/<slug>/copywriting/tutorial.md` / `playground.md` 时按下面结构收敛：

1. 标题和一句话概览：说清楚应用是什么、适合谁。
2. 开始前准备：列出账号、provider、测试数据、示例仓库或持久化目录要求。
3. 首次打开：放真实安装实例的主界面截图。
4. 第一条核心任务：给一个可复现的小目标，说明好任务/好输入怎么写。
5. 执行中和结果：至少补执行中状态、完成结果、详情页或日志页截图，不只截空状态。
6. 设置与进阶：有 provider、runtime、插件、员工、外部服务时单独成节，说明适用场景和试跑建议。
7. 使用心得和常见问题：把排障经验改写成用户可执行建议。

公开攻略里不要出现这些内部文本：

- `本次功能测试记录`、`验收记录`、`Browser Use 验收证据`
- `截图/发布攻略时要注意什么`、提交审核提醒、发布安全边界
- API key、GitHub token、私有仓库 URL、真实客户任务、回调 URL、日志密钥

截图素材优先放在 `apps/<slug>/copywriting/assets/`；商店截图放在 `apps/<slug>/store/screenshots/`。同一张图可以复用，但攻略截图更应展示“怎么用”，商店截图更应展示“第一眼价值”。

提交 LazyCat Playground/Workshop 图文攻略前，按下面要求处理：

- 正文截图必须来自真实实例或真实后台页面，不使用 mock、旧图或伪造状态。
- Agent/Runtime 类教程只写已经验证的链路；blocked run 要如实写出 DNS、repo、token 或权限阻塞。
- 上传前检查正文，删除用户指令、助手过程回复、内部 TODO、验证码、token、JWT、callback URL 和隐私信息。
- 上传截图后确认正文图片、封面、标题和分类都已在编辑器中生效。
- 点击“存草稿”或“发布”前都要向用户确认；“发布”需要独立确认。

## 3. 浏览器提交

1. 用 Codex Browser Use 打开 `project-config.json` 中的 `lazycat.developer_apps_url`。
2. 在开发者后台新建 App。
3. 根据 `submission.json` 填写应用名、包名、版本、简介、详情、关键词、主页和许可证。
4. 对移植上游开源项目，取消“应用程序为原创开发或本人是源作者”，填写原作者/组织名称和源项目地址；只有原创项目或本人就是源作者时才保留该声明。
5. 上传 `apps/<slug>/store-submission/assets/icon.png`、`apps/<slug>/store-submission/assets/screenshots/*.png` 和 `dist/<slug>.lpk`。
6. 停在最终创建、提交审核或发布按钮前，向用户确认。
7. 用户确认后再提交，并把后台状态或详情页链接写回本地记录。

## 4. 安全边界

- 上传 `.lpk`、截图和图标属于向 LazyCat 平台传输文件；只有用户明确要求时才执行。
- 创建或提交 App 会影响第三方平台上的开发者记录；即使用户要求执行，也要在最终提交按钮前进行一次明确确认。
- 移植应用不得勾选原创/源作者声明；必须优先填写上游作者、上游仓库和许可证信息。
- 如果页面要求验证码、支付、敏感账号信息或额外权限，停止并交给用户处理。
