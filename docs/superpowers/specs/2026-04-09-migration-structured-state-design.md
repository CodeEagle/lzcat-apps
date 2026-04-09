# full_migrate.py 结构化状态输出设计

## 目标

让 `full_migrate.py` 的 10 步 SOP 每步产出结构化数据，固化到 `.migration-state.json`。同一个上游输入重复运行，产出完全相同的 `apps/<slug>/` 目录。支持断点续跑、问题追踪、从零复现验证，并通过模式库实现跨 app 经验复用。

## 设计决策记录

| 决策项 | 结论 | 理由 |
|--------|------|------|
| 状态文件位置 | `apps/<slug>/.migration-state.json`，提交进 git | 作为决策审计日志，可 diff |
| 状态失效策略 | `--force` 全量重跑，否则复用已有状态 | 简单可靠，移植场景不需要精细失效判断 |
| 断点续跑 | `--resume` 自动 + `--resume-from N` 显式 | 低成本覆盖两种场景 |
| 步骤数 | 保持 10 步不变 | Steps 5/6 后续可扩展，改编号连锁成本高 |
| 状态文件格式 | 分层：`context`（共享）+ `steps`（每步产出） | 避免 finalized dict 重复 10 次 |

## CLI 参数

```
python3 scripts/full_migrate.py <source>                # 正常运行（有状态则复用）
python3 scripts/full_migrate.py <source> --force         # 忽略状态，全量重跑
python3 scripts/full_migrate.py <source> --resume        # 从最后完成步骤继续
python3 scripts/full_migrate.py <source> --resume-from 5 # 从第 5 步开始
python3 scripts/full_migrate.py <source> --verify        # 从零复现验证
python3 scripts/full_migrate.py --verify-all             # 全量回归测试
python3 scripts/full_migrate.py --stats                  # 自动化覆盖率报告
```

## 状态文件 Schema

### 顶层结构

```jsonc
{
  "schema_version": 1,
  "created_at": "2026-04-09T23:00:00Z",
  "updated_at": "2026-04-09T23:05:00Z",
  "source_input": "owner/repo",

  "context": { /* 跨步骤共享数据 */ },
  "steps": { /* 每步独有产出 */ },
  "problems": [ /* 问题追踪 */ ],
  "verification": { /* 复现验证结果 */ }
}
```

### context.source（Step 1 产出）

```jsonc
{
  "kind": "github_repo | docker_image | compose_url | local_repo",
  "url": "https://github.com/owner/repo",
  "upstream_repo": "owner/repo",
  "homepage": "https://...",
  "commit": "abc1234",
  "default_branch": "main",
  "license": "MIT",
  "github_description": "A self-hosted ...",
  "github_topics": ["self-hosted", "docker"]
}
```

### context.environment（Step 1 产出）

```jsonc
{
  "gh_token_source": "env:GH_TOKEN | gh_auth | none",
  "lzc_cli_token_source": "env:LZC_CLI_TOKEN | lzc_cli_config | none",
  "container_runtime": "docker | podman | none",
  "image_owner": "CodeEagle"
}
```

### context.upstream_deployment（Step 1 产出）

#### files_scanned

记录实际扫描到了哪些文件，确保可审计：

```jsonc
{
  "dockerfiles": ["Dockerfile"],
  "compose_files": ["docker-compose.yml"],
  "env_files": [".env.example"],
  "readmes": ["README.md"],
  "package_jsons": ["package.json"],
  "startup_scripts": ["docker/entrypoint.sh"],
  "config_files": ["config/default.yml"],
  "api_specs": [],
  "icon_candidates": ["public/favicon.png", "docs/logo.svg"],
  "helm_charts": [],
  "k8s_manifests": [],
  "lock_files": ["pnpm-lock.yaml"],
  "build_files": ["Makefile"]
}
```

#### dockerfile_analysis

```jsonc
{
  "path": "Dockerfile",
  "base_image": "node:20-alpine",
  "stages": 2,
  "final_stage_base": "node:20-alpine",
  "exposed_ports": [3000],
  "volumes": ["/app/data"],
  "user": "node",
  "workdir": "/app",
  "cmd": ["node", "server.js"],
  "entrypoint": null,
  "healthcheck": {
    "test": "curl -f http://localhost:3000/health",
    "interval": "30s",
    "timeout": "5s",
    "retries": 3
  },
  "env_defaults": {
    "NODE_ENV": "production",
    "PORT": "3000"
  }
}
```

#### compose_analysis

```jsonc
{
  "path": "docker-compose.yml",
  "services": {
    "web": {
      "image": "owner/repo:latest",
      "build": {"context": ".", "dockerfile": "Dockerfile"},
      "ports": ["3000:3000"],
      "environment": ["DATABASE_URL=postgres://..."],
      "volumes": ["./data:/app/data"],
      "depends_on": ["postgres"],
      "healthcheck": null,
      "is_primary": true,
      "classification": "application"
    },
    "postgres": {
      "image": "postgres:16-alpine",
      "environment": ["POSTGRES_DB=app"],
      "volumes": ["pgdata:/var/lib/postgresql/data"],
      "classification": "infrastructure"
    }
  },
  "named_volumes": ["pgdata"],
  "has_dev_overrides": false
}
```

#### env_vars

```jsonc
[
  {
    "name": "DATABASE_URL",
    "default": "postgres://app:app@postgres:5432/app",
    "required": true,
    "source": ".env.example",
    "category": "database",
    "description": "PostgreSQL connection string"
  }
]
```

环境变量分类（`category`）：
- `database` — DATABASE_URL, DB_*, POSTGRES_*, MYSQL_*, REDIS_*
- `auth` — SECRET_KEY, JWT_*, SESSION_*, ADMIN_*, DEFAULT_USER*, DEFAULT_PASS*, OIDC_*, OAUTH_*
- `storage` — S3_*, MINIO_*, UPLOAD_*
- `network` — PORT, HOST, BASE_URL, CORS_*
- `feature` — 其他业务变量

#### data_paths

```jsonc
[
  {
    "path": "/app/data",
    "purpose": "application_data | database | config | cache | upload | log | temp",
    "source": "Dockerfile VOLUME | compose volume | entrypoint.sh mkdir | README",
    "writable": true,
    "owner": "node (uid=1000)",
    "group": "node (gid=1000)",
    "mode": "0755",
    "pre_create": true
  }
]
```

#### init_commands

```jsonc
[
  {
    "command": "npx prisma migrate deploy",
    "when": "first_start | every_start | manual",
    "purpose": "database migration",
    "source": "docker/entrypoint.sh:15",
    "run_as": "node"
  }
]
```

#### external_deps

```jsonc
[
  {
    "type": "postgres | mysql | redis | mongo | minio | elasticsearch",
    "image": "postgres:16-alpine",
    "required": true,
    "env_vars_consumed": ["DATABASE_URL"],
    "source": "docker-compose.yml service postgres"
  }
]
```

#### login_mechanism

```jsonc
{
  "needs_login": true,
  "evidence": [
    "README.md mentions 'default admin account'",
    ".env.example has DEFAULT_ADMIN_EMAIL and DEFAULT_ADMIN_PASSWORD"
  ],
  "supports_oidc": false,
  "oidc_evidence": [],
  "fixed_credentials": true,

  "readme_credentials": [
    {
      "username": "admin",
      "password": "admin123",
      "source": "README.md:45",
      "match_type": "table | inline | slash | code_block | env_assignment",
      "raw_text": "| Username | admin | Password | admin123 |",
      "confidence": "high | medium | low"
    }
  ],

  "example_credentials": [
    {
      "username_var": "ADMIN_EMAIL",
      "username_value": "admin@example.com",
      "password_var": "ADMIN_PASSWORD",
      "password_value": "changeme",
      "source": "README.md:72 (docker run example)"
    }
  ],

  "default_user": "admin",
  "default_user_source": "README.md:45 (table)",
  "default_password": "admin123",
  "default_password_source": "README.md:45 (table)",
  "password_is_placeholder": true,
  "has_password_change": true,
  "passwordless_route": "oidc | simple_inject | three_phase_inject | none_needed",
  "oidc_redirect_path": null
}
```

弱密码判定：
```python
WEAK_PASSWORDS = {
    "admin", "admin123", "password", "123456", "changeme",
    "secret", "default", "test", "demo", "example",
    "pass", "1234", "12345678", "root", "toor",
}
```

#### gpu_assessment

```jsonc
{
  "has_gpu_deps": false,
  "evidence": [],
  "cpu_viable": true,
  "quality_gap": "none | minor | major",
  "aipod_viable": false
}
```

#### icon_candidates

```jsonc
[
  {
    "path": "docs/logo.svg",
    "source": "filesystem scan",
    "size_bytes": 3200,
    "score": 10
  },
  {
    "path": "public/favicon.png",
    "source": "filesystem scan",
    "size_bytes": 15000,
    "score": 8
  }
]
```

图标评分规则：
- logo.png/svg: 10, icon.png/svg: 9, favicon.png/svg: 8, favicon.ico: 7, brand.png/svg: 6
- 搜索目录: `.`, `public`, `static`, `assets`, `images`, `img`, `docs`
- README 中的图片链接: `!\[.*\]\((.*\.png|.*\.svg)\)` 第一张图片

#### project_meta

```jsonc
{
  "name_from_readme": "My Awesome App",
  "name_from_package_json": "my-awesome-app",
  "name_from_github": "my-awesome-app",
  "description_from_readme": "A self-hosted project management tool",
  "description_from_github": "Self-hosted project management",
  "framework_detected": "express | django | flask | fastapi | spring | gin | nextjs | nuxt",
  "language_primary": "typescript | python | go | java | rust",
  "package_manager": "pnpm | npm | yarn | pip | go mod | cargo | maven | gradle"
}
```

### context.route_decision（Step 2 产出）

```jsonc
{
  "route": "single_container | compose_multi | source_build | aipod_hybrid",
  "build_strategy": "official_image | upstream_dockerfile | target_repo_dockerfile | upstream_with_target_template | precompiled_binary",
  "check_strategy": "github_release | github_tag | commit_sha",

  "decision_chain": [
    {"check": "is_docker_image_input", "result": false},
    {"check": "has_compose_file", "result": true},
    {"check": "is_dev_compose", "result": false},
    {"check": "has_official_image", "result": true, "image": "owner/repo:latest"},
    {"check": "selected_route", "result": "compose + official_image"}
  ],

  "primary_service": "web",
  "services_kept": [
    {"name": "web", "reason": "primary application service", "image": "owner/repo:latest"},
    {"name": "postgres", "reason": "required database dependency", "image": "postgres:16-alpine"}
  ],
  "services_dropped": [
    {"name": "redis", "reason": "optional cache, not in critical path"}
  ],

  "version": {
    "upstream": "v2.1.0",
    "normalized": "2.1.0",
    "source_version": "2.1.0",
    "build_version": null,
    "version_source": "github_release"
  },

  "passwordless_decision": {
    "route": "simple_inject",
    "reason": "README documents default credentials, password is placeholder",
    "deploy_params_needed": true,
    "oidc_config": null,
    "inject_config": {
      "type": "builtin://simple-inject-password",
      "when_patterns": ["/#login", "/login"],
      "user_source": "deploy_param:login_user",
      "password_source": "deploy_param:login_password"
    },
    "credential_origin": {
      "from": "readme_credentials[0]",
      "username_kept": true,
      "password_overridden": true,
      "override_reason": "placeholder password detected"
    }
  },

  "icon_decision": {
    "selected": "docs/logo.svg",
    "action": "download_and_convert_to_512x512_png",
    "fallback": "github_avatar"
  },

  "port_decision": {
    "container_port": 3000,
    "evidence": ["Dockerfile EXPOSE 3000", "compose ports 3000:3000"],
    "protocol": "http"
  },

  "risks": [],

  "fingerprint": {
    "base_image_family": "node",
    "has_compose": true,
    "service_count": 2,
    "has_database": true,
    "database_type": "postgres",
    "has_redis": false,
    "auth_type": "builtin_login",
    "build_system": "pnpm",
    "framework": "express",
    "port_protocol": "http",
    "has_gpu": false,
    "matched_pattern": "node-postgres-web"
  }
}
```

### context.finalized（Step 3 产出）

`bootstrap_migration.finalize_spec()` 的完整输出，JSON 序列化。此 dict 是 Step 4 `bm.write_files()` 的唯一输入——相同 `finalized` 产出相同文件。

### context.registration（Step 3 产出）

```jsonc
{
  "slug": "myapp",
  "monorepo_path": "apps/myapp",
  "config_path": "registry/repos/myapp.json",
  "index_updated": true,
  "independent_repo": {"needed": false, "reason": null}
}
```

### steps（每步产出）

#### Step 1

```jsonc
{
  "completed": true,
  "completed_at": "2026-04-09T23:00:01Z",
  "conclusion": "已识别输入类型为 github_repo",
  "scripts_called": ["full_migrate.py", "git clone"]
}
```

#### Step 2

```jsonc
{
  "completed": true,
  "completed_at": "2026-04-09T23:00:03Z",
  "conclusion": "已自动推断构建路线为 official_image"
}
```

#### Step 3

```jsonc
{
  "completed": true,
  "completed_at": "2026-04-09T23:00:04Z",
  "conclusion": "已完成 monorepo 注册"
}
```

#### Step 4

```jsonc
{
  "completed": true,
  "completed_at": "2026-04-09T23:00:05Z",
  "files_written": [
    "apps/myapp/lzc-manifest.yml",
    "apps/myapp/lzc-build.yml",
    "apps/myapp/icon.png",
    "apps/myapp/README.md",
    "registry/repos/myapp.json"
  ],
  "deploy_params_file": "apps/myapp/lzc-deploy-params.yml",
  "post_write_files": [],
  "force_overwrite": false
}
```

#### Step 5

```jsonc
{
  "completed": true,
  "completed_at": "2026-04-09T23:00:05Z",
  "conclusion": "manifest 已确认"
}
```

#### Step 6

```jsonc
{
  "completed": true,
  "completed_at": "2026-04-09T23:00:05Z",
  "conclusion": "剩余文件已确认",
  "files_confirmed": ["README.md", "lzc-build.yml"]
}
```

#### Step 7

```jsonc
{
  "completed": true,
  "completed_at": "2026-04-09T23:00:06Z",
  "preflight_checks": [
    {"rule": "manifest_exists", "pass": true},
    {"rule": "version_semver", "pass": true, "value": "2.1.0"},
    {"rule": "backend_real_service", "pass": true, "service": "web", "port": 3000},
    {"rule": "no_upstream_registry", "pass": true},
    {"rule": "no_template_placeholders", "pass": true},
    {"rule": "icon_valid", "pass": true, "size_bytes": 45000},
    {"rule": "passwordless_login_configured", "pass": true, "route": "simple_inject"},
    {"rule": "deploy_params_valid", "pass": true}
  ],
  "all_passed": true,
  "git_committed": true,
  "commit_sha": "def5678"
}
```

#### Step 8

```jsonc
{
  "completed": true,
  "completed_at": "2026-04-09T23:01:00Z",
  "build_mode": "reinstall",
  "images_built": [
    {
      "service": "web",
      "source_image": "owner/repo:2.1.0",
      "ghcr_image": "ghcr.io/codeeagle/lazycatimages:myapp_2.1.0",
      "lazycat_image": "registry.lazycat.cloud/xxx/yyy:abc123",
      "digest": "sha256:abc...",
      "cache_hit": false
    }
  ],
  "lpk_path": "dist/myapp.lpk",
  "lpk_size_bytes": 123456
}
```

#### Step 9

```jsonc
{
  "completed": true,
  "completed_at": "2026-04-09T23:01:05Z",
  "lpk_path": "dist/myapp.lpk",
  "lpk_sha256": "sha256:...",
  "manifest_verified": {
    "version_match": true,
    "all_images_lazycat": true,
    "services_checked": [
      {"service": "web", "image": "registry.lazycat.cloud/xxx/yyy:abc123", "correct": true}
    ]
  }
}
```

#### Step 10

```jsonc
{
  "completed": true,
  "completed_at": "2026-04-09T23:02:00Z",
  "install_result": "success",
  "package_id": "cloud.lazycat.app.myapp",
  "app_status": "Installed",
  "services_running": [
    {"service": "web", "container_status": "running", "uptime": "2m"}
  ],
  "endpoints_verified": [
    {"path": "/", "status_code": 200, "response_time_ms": 350}
  ],
  "passwordless_verified": true,
  "data_persistence_verified": true
}
```

### problems（问题追踪）

```jsonc
[
  {
    "id": "p1",
    "step": 8,
    "created_at": "2026-04-09T23:01:30Z",
    "description": "GHCR package is private, copy-image fails with UNAUTHORIZED",
    "category": "preflight | build | artifact | install | startup | route",
    "status": "open | resolved | backported",
    "resolution": "Set GHCR package to public via GitHub UI",
    "resolved_at": "2026-04-09T23:03:00Z",
    "backport": {
      "target": "full_migrate.py | bootstrap_migration.py | skill",
      "description": "Add anonymous pull pre-check before copy-image",
      "committed": false
    }
  }
]
```

生命周期：
- `open` → 遇到问题，记录现象，脚本中断
- `resolved` → 手动解决后记录方法，`--resume` 继续
- `backported` → 解决方法已沉淀到脚本代码中

规则：Step 10 验收时，存在 `resolved` 但 `backport.committed: false` 的 problem 必须列出"待回写"清单。

### verification（复现验证）

```jsonc
{
  "last_run": "2026-04-09T23:10:00Z",
  "result": "pass | fail",
  "diffs": [
    {
      "step": 4,
      "file": "apps/myapp/lzc-manifest.yml",
      "diff_type": "content_mismatch",
      "detail": "line 15: env var order differs"
    }
  ],
  "pending_backports": ["p1"],
  "automation_score": {
    "total_steps": 10,
    "auto_completed": 8,
    "manual_interventions": 2,
    "problems_encountered": 3,
    "problems_backported": 2,
    "problems_pending": 1,
    "verify_pass": true,
    "score": 0.80
  }
}
```

## Step 1/2 文件扫描清单

### Step 1 扫描的文件

#### 构建与部署描述

| 文件/模式 | 扫描方式 | 提取内容 |
|-----------|---------|---------|
| `Dockerfile` / `Containerfile` | rglob 递归 | FROM、EXPOSE、CMD/ENTRYPOINT、VOLUME、HEALTHCHECK、USER、ENV、WORKDIR |
| `docker-compose.yml` 系列 | rglob 递归 | services 拓扑、ports、volumes、environment、depends_on、healthcheck、image、build |
| `nginx.conf` / `Caddyfile` / `default.conf` | 固定路径 + `deploy/` `nginx/` | proxy_pass 目标、upstream、location |
| `vite.config.ts/js/mjs/cjs` / `nitro.config.ts/js` | 固定路径 | proxy 配置、server.port、build output |
| `entrypoint.sh` / `start.sh` / `init.sh` / `run.sh` / `docker-entrypoint.sh` | rglob + 固定名称 | 启动命令、初始化逻辑、目录创建、权限设置 |
| `supervisord.conf` | rglob | 进程列表、启动顺序、日志路径 |
| `Makefile` / `justfile` | 根目录 | build/run/dev target |
| `helm/` / `kubernetes/` / `k8s/` 下的 `*.yaml` | 目录检测 + rglob | service port、volume mounts、env、probe |

#### 环境变量与配置

| 文件/模式 | 扫描方式 | 提取内容 |
|-----------|---------|---------|
| `.env.example` / `.env.sample` / `.env.template` | rglob | 变量名、默认值、注释 |
| `.env` / `.env.production` / `.env.local` | rglob | key 名（不取 secret 值） |
| `config/` 目录 | 目录扫描 | 配置文件列表、格式 |
| `application.yml` / `application.properties` | rglob | Spring Boot 端口、数据源 |
| `settings.py` / `config.py` | rglob | Django/Flask 端口、数据库 |
| `appsettings.json` | rglob | .NET 端口、连接串 |

#### 项目元信息

| 文件/模式 | 扫描方式 | 提取内容 |
|-----------|---------|---------|
| `README*` | rglob | 项目名、描述、docker run 命令、端口、数据目录、默认凭据 |
| `package.json` | rglob 排除 node_modules | name、description、scripts、dependencies |
| `pyproject.toml` | rglob | name、description、dependencies |
| `go.mod` | 根目录 | module name、dependencies |
| `Cargo.toml` | 根目录 | name、description、dependencies |
| `pom.xml` / `build.gradle` | 根目录 | groupId、artifactId、dependencies |
| `LICENSE` | 根目录 | 许可证类型 |
| GitHub API | REST | description、topics、license、latest release |

#### 认证与登录

| 文件/模式 | 扫描方式 | 提取内容 |
|-----------|---------|---------|
| `.env*` auth 变量 | 变量名正则 | OIDC_*、OAUTH_*、AUTH_*、JWT_*、ADMIN_*、DEFAULT_USER*、DEFAULT_PASS* |
| Dockerfile ENV auth 变量 | 正则扫描 | 同上 |
| compose environment auth 变量 | 解析已有数据 | 同上 |
| README 默认凭据 | 多模式正则 | 表格/行内/斜杠/代码块/环境变量赋值形式的 username/password |
| `openapi.yaml` / `swagger.json` | rglob | /auth/*、/login、securitySchemes |

README 默认凭据扫描模式：
- 表格：`\| Username \| admin \|`
- 行内：`username: admin` / `password: changeme`
- 斜杠：`credentials: admin/admin123`
- 代码块：`` `admin` / `admin123` ``
- 环境变量赋值：`ADMIN_PASSWORD=changeme`

弱密码判定集合：`admin`, `admin123`, `password`, `123456`, `changeme`, `secret`, `default`, `test`, `demo`, `example`, `pass`, `1234`, `12345678`, `root`, `toor`

#### 图标

| 文件/模式 | 扫描方式 | 提取内容 |
|-----------|---------|---------|
| `logo.png/svg`, `icon.png/svg`, `favicon.*`, `brand.*` | rglob 常见目录 | 文件路径、大小、评分 |
| `public/` `static/` `assets/` `images/` `img/` `docs/` 下的图片 | rglob `*.png` `*.svg` `*.ico` | 按文件名评分 |
| README 图片链接 | 正则 `!\[.*\]\((.*\.png\|.*\.svg)\)` | 第一张图片 URL |
| GitHub API | REST | owner avatar_url（兜底） |

### Step 2 决策依赖

| 数据源（来自 Step 1） | 决策 |
|------|------|
| `dockerfile_analysis` | 有无 Dockerfile → build_strategy |
| `compose_analysis` | 有无 compose + 服务拓扑 → route |
| `compose_analysis.services[].classification` | infra vs app → 保留哪些服务 |
| `env_vars[].category` | 数据库变量 → 需要依赖服务 |
| `gpu_assessment` | GPU 依赖 → AIPod 路线 |
| `login_mechanism` | 登录方式 → passwordless_route |
| `icon_candidates` | 图标评分 → 选哪个 icon |
| `project_meta.framework_detected` | 框架 → 构建命令 |
| GitHub release info | 有无 binary → precompiled_binary 路线 |
| `fingerprint` → 模式库匹配 | 已知模式 → 复用默认值 |

## 模式库

### 位置

`registry/patterns/<pattern-id>.json`

### Schema

```jsonc
{
  "pattern_id": "node-postgres-web",
  "match_rules": {
    "base_image_contains": ["node"],
    "has_database": true,
    "database_type": "postgres"
  },
  "defaults": {
    "build_strategy": "upstream_dockerfile",
    "postgres_env_template": {},
    "common_data_paths": ["/app/data", "/app/uploads"],
    "typical_port": 3000
  },
  "known_pitfalls": [
    "Node apps often need NODE_ENV=production",
    "Prisma needs migrate deploy in setup_script"
  ],
  "source_apps": ["outline", "hoppscotch", "plane"]
}
```

### 成长机制

- `--verify` pass 后自动检查当前 fingerprint 是否已有匹配模式
- 无匹配 → 提示"新模式候选"
- 有匹配 → 合并本次参数到已有模式

## 代码改造要点

### 1. 状态读写层（新增）

```python
def load_state(app_dir: Path) -> dict | None:
    """读取已有状态文件，不存在则返回 None"""

def save_state(app_dir: Path, state: dict) -> None:
    """原子写入（先写 .tmp 再 rename），自动更新 updated_at"""

def get_last_completed_step(state: dict) -> int:
    """从 steps 中找到最后一个 completed=true 的步骤号"""

def should_skip_step(state: dict, step: int) -> bool:
    """判断某步是否已完成且可跳过"""

def add_problem(state: dict, step: int, description: str, category: str) -> str:
    """追加问题记录，返回 problem id"""
```

### 2. main() 改造

```python
def main() -> int:
    args = parse_args()
    repo_root = ...

    # 状态恢复
    existing_state = None if args.force else load_state(app_dir)

    if args.resume_from:
        start_step = args.resume_from
    elif args.resume and existing_state:
        start_step = get_last_completed_step(existing_state) + 1
    else:
        start_step = 1

    state = existing_state or new_empty_state(args.source)

    for step in range(start_step, 11):
        if should_skip_step(state, step):
            continue
        try:
            run_step(step, state, ...)
            save_state(app_dir, state)
        except MigrationProblem as e:
            add_problem(state, step, str(e), e.category)
            save_state(app_dir, state)
            return 1
```

### 3. 序列化边界

- `Path` → `str`（相对于 repo_root）
- `dataclass` → `dict`
- `set` → sorted `list`
- `None` → `null`
- `finalized` dict 已经是 JSON-friendly

### 4. 鸡生蛋问题

`app_dir` 依赖 `slug`，`slug` 在 Step 2 才确定：
- Steps 1-2 状态暂存内存
- Step 2 确定 slug 后首次 `save_state()`
- `--resume` 时扫描 `apps/*/.migration-state.json` 匹配 `source_input`

### 5. verify 模式

```python
def run_verify(source: str, repo_root: Path) -> int:
    baseline = load_state(app_dir)
    with tempfile.TemporaryDirectory() as tmp:
        # clone repo to tmp, run full migration
        new_state = run_full_migration(source, tmp_repo_root)
        # compare context and step 4 file outputs
        diffs = compare_states(baseline, new_state, repo_root, tmp_repo_root)
        baseline["verification"] = build_verify_report(diffs)
        save_state(app_dir, baseline)
        return 0 if not diffs else 1
```

## 实施阶段

| 阶段 | 内容 | 产出 |
|------|------|------|
| Phase 1 | 状态读写层 + Step 1-3 结构化输出 + save_state | 状态文件可生成 |
| Phase 2 | Step 4-10 结构化输出 + --resume/--resume-from | 断点续跑可用 |
| Phase 3 | problems 追踪 + Step 10 待回写清单 | 问题闭环 |
| Phase 4 | --verify 从零复现 + diff 报告 | 确定性验证 |
| Phase 5 | --verify-all + --stats + automation_score | 回归套件 + 覆盖率 |
| Phase 6 | fingerprint + registry/patterns/ 模式库 | 跨 app 经验复用 |
| Phase 7 | 新增文件扫描（启动脚本、认证检测、图标、框架配置） | Step 1 信息更完整 |
