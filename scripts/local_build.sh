#!/usr/bin/env bash
# local_build.sh — 本地开发验证脚本
#
# 用法:
#   ./scripts/local_build.sh paperclip                    # dry-run（跳过 copy-image / publish / git push）
#   ./scripts/local_build.sh paperclip --check-only       # 只检查版本，不 build
#   ./scripts/local_build.sh paperclip --force-build      # 强制 build
#   ./scripts/local_build.sh paperclip --install          # build 完自动卸载旧版并安装到设备
#   ./scripts/local_build.sh paperclip --target-version 0.3.2
#   ./scripts/local_build.sh paperclip --no-dry-run       # 完整流程（需要 LZC_CLI_TOKEN）
#
# 环境变量（可在 scripts/.env.local 中配置，不要提交）:
#   GH_TOKEN        — GitHub token，用于读取上游版本
#   LZC_CLI_TOKEN   — LazyCat CLI token（非 dry-run 时必须）
#   GHCR_TOKEN      — GHCR push token（非 dry-run 时必须，默认复用 GH_TOKEN）

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$REPO_ROOT/scripts/.env.local"

# 加载本地 env（如果存在）
if [ -f "$ENV_FILE" ]; then
  set -o allexport
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +o allexport
fi

APP="${1:-}"
if [ -z "$APP" ]; then
  echo "Usage: $0 <app-name> [options]" >&2
  echo "Available apps:" >&2
  ls "$REPO_ROOT/registry/repos/" | sed 's/\.json$//' | sort | sed 's/^/  /' >&2
  exit 1
fi
shift

CONFIG_FILE="${APP}.json"
CONFIG_PATH="$REPO_ROOT/registry/repos/$CONFIG_FILE"
if [ ! -f "$CONFIG_PATH" ]; then
  echo "Config not found: $CONFIG_PATH" >&2
  exit 1
fi

APP_ROOT="$REPO_ROOT/apps/$APP"
if [ ! -d "$APP_ROOT" ]; then
  echo "App dir not found: $APP_ROOT" >&2
  exit 1
fi

# 解析自定义参数
DRY_RUN=true
INSTALL=false
EXTRA_ARGS=()
for arg in "$@"; do
  case "$arg" in
    --no-dry-run) DRY_RUN=false ;;
    --install) INSTALL=true ;;
    *) EXTRA_ARGS+=("$arg") ;;
  esac
done

LPK_OUTPUT="$REPO_ROOT/dist/${APP}.lpk"

ARGS=(
  --config-root "$REPO_ROOT/registry"
  --config-file "$CONFIG_FILE"
  --artifact-repo "CodeEagle/lzcat-artifacts"
  --app-root "$APP_ROOT"
  --lzcat-apps-root "$REPO_ROOT"
  --lpk-output "$LPK_OUTPUT"
)

if $DRY_RUN; then
  ARGS+=(--dry-run)
  echo "==> [DRY RUN] 跳过 copy-image / publish / git push"
fi

if $INSTALL; then
  # --install 隐含 --force-build（需要有 lpk）
  ARGS+=(--force-build)
fi

ARGS+=("${EXTRA_ARGS[@]}")

export GITHUB_REPOSITORY_OWNER="${GITHUB_REPOSITORY_OWNER:-CodeEagle}"
export GH_TOKEN="${GH_TOKEN:-$(gh auth token 2>/dev/null || true)}"
export GITHUB_TOKEN="${GH_TOKEN:-}"
export GHCR_TOKEN="${GHCR_TOKEN:-${GH_TOKEN:-}}"
export GHCR_USERNAME="${GHCR_USERNAME:-${GITHUB_REPOSITORY_OWNER}}"
export LZC_CLI_TOKEN="${LZC_CLI_TOKEN:-}"

echo "==> Running: python3 scripts/run_build.py ${ARGS[*]}"
echo ""
python3 "$REPO_ROOT/scripts/run_build.py" "${ARGS[@]}"

# 安装到设备
if $INSTALL && [ -f "$LPK_OUTPUT" ]; then
  # 从 manifest 读取 pkgId
  PKG_ID="$(grep -m1 '^id:' "$APP_ROOT/lzc-manifest.yml" | awk '{print $2}' | tr -d '"' || true)"
  echo ""
  echo "==> Installing $LPK_OUTPUT to device..."
  if [ -n "$PKG_ID" ]; then
    echo "==> Uninstalling old version: $PKG_ID"
    lzc-cli app uninstall "$PKG_ID" 2>/dev/null || true
  fi
  lzc-cli app install "$LPK_OUTPUT"
  echo "==> Done."
fi
