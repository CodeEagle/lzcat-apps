#!/usr/bin/env bash
# local_build.sh — 本地开发验证脚本
#
# 用法:
#   ./scripts/local_build.sh paperclip                    # dry-run（跳过 copy-image / publish / git push）
#   ./scripts/local_build.sh paperclip --check-only       # 只检查版本，不 build
#   ./scripts/local_build.sh paperclip --force-build      # 强制 build（含 Docker）
#   ./scripts/local_build.sh paperclip --install          # 只重打包 content/，安装到设备（秒级）
#   ./scripts/local_build.sh paperclip --install --with-docker  # 重建 Docker image 再安装
#   ./scripts/local_build.sh paperclip --target-version 0.3.2
#   ./scripts/local_build.sh paperclip --no-dry-run       # 完整流程（需要 LZC_CLI_TOKEN）
#
# 环境变量（可在 scripts/.env.local 中配置，不要提交）:
#   GH_PAT / GH_TOKEN — 主凭据；用于 GitHub API，且默认同时用于 GHCR push
#   LZC_CLI_TOKEN   — LazyCat CLI token（非 dry-run 时必须）

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$REPO_ROOT/scripts/.env.local"
DOCKER_SHIM_DIR=""

cleanup() {
  if [ -n "$DOCKER_SHIM_DIR" ] && [ -d "$DOCKER_SHIM_DIR" ]; then
    rm -rf "$DOCKER_SHIM_DIR"
  fi
}
trap cleanup EXIT

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
WITH_DOCKER=false
EXTRA_ARGS=()
for arg in "$@"; do
  case "$arg" in
    --no-dry-run) DRY_RUN=false ;;
    --install) INSTALL=true ;;
    --with-docker) WITH_DOCKER=true ;;
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
  ARGS+=(--force-build)
  if ! $WITH_DOCKER; then
    # 默认跳过 Docker build，只重打包 content/（秒级）
    ARGS+=(--skip-docker)
    echo "==> [SKIP DOCKER] 只重打包 content/，使用 .lazycat-images.json 中已有的镜像"
  fi
fi

ARGS+=("${EXTRA_ARGS[@]}")

export GITHUB_REPOSITORY_OWNER="${GITHUB_REPOSITORY_OWNER:-CodeEagle}"
export GH_TOKEN="${GH_TOKEN:-${GH_PAT:-$(gh auth token 2>/dev/null || true)}}"
export GITHUB_TOKEN="${GH_TOKEN:-}"
export GHCR_USERNAME="${GHCR_USERNAME:-${GITHUB_REPOSITORY_OWNER}}"
if [ -z "${LZC_CLI_TOKEN:-}" ] && command -v lzc-cli >/dev/null 2>&1; then
  LZC_CLI_TOKEN="$(lzc-cli config get token 2>/dev/null | awk 'NF { print $NF; exit }' || true)"
fi
export LZC_CLI_TOKEN="${LZC_CLI_TOKEN:-}"

if ! $DRY_RUN && [ -z "${GH_PAT:-}" ] && command -v gh >/dev/null 2>&1; then
  ACTIVE_SCOPE_LINE="$(gh auth status -t 2>/dev/null | awk '/Active account: true/{active=1; next} active && /Token scopes:/{print; exit}')"
  if [ -n "$ACTIVE_SCOPE_LINE" ] && ! printf '%s\n' "$ACTIVE_SCOPE_LINE" | grep -q "write:packages"; then
    echo "GHCR push requires a GitHub token with write:packages on the active gh account." >&2
    echo "Current active account scopes: ${ACTIVE_SCOPE_LINE#*- Token scopes: }" >&2
    exit 1
  fi
fi

if ! command -v docker >/dev/null 2>&1 && command -v podman >/dev/null 2>&1; then
  PODMAN_MACHINE_NAME="${PODMAN_MACHINE_NAME:-podman-machine-default}"
  if podman machine inspect "$PODMAN_MACHINE_NAME" >/dev/null 2>&1; then
    PODMAN_MACHINE_STATE="$(
      podman machine inspect "$PODMAN_MACHINE_NAME" \
        | ruby -rjson -e 'data = JSON.parse(STDIN.read); puts data.dig(0, "State").to_s'
    )"
    if [ "$PODMAN_MACHINE_STATE" != "running" ]; then
      echo "==> [PODMAN] starting machine $PODMAN_MACHINE_NAME"
      podman machine start "$PODMAN_MACHINE_NAME" >/dev/null
    fi
    PODMAN_SOCKET_PATH="$(
      podman machine inspect "$PODMAN_MACHINE_NAME" \
        | ruby -rjson -e 'data = JSON.parse(STDIN.read); puts data.dig(0, "ConnectionInfo", "PodmanSocket", "Path").to_s'
    )"
    if [ -n "$PODMAN_SOCKET_PATH" ]; then
      export DOCKER_HOST="unix://$PODMAN_SOCKET_PATH"
      export CONTAINER_HOST="$DOCKER_HOST"
      echo "==> [PODMAN] using socket $DOCKER_HOST"
    fi
  fi
  DOCKER_SHIM_DIR="$(mktemp -d "${TMPDIR:-/tmp}/lzcat-docker-shim.XXXXXX")"
  cat >"$DOCKER_SHIM_DIR/docker" <<'EOF'
#!/usr/bin/env bash
exec podman "$@"
EOF
  chmod +x "$DOCKER_SHIM_DIR/docker"
  export PATH="$DOCKER_SHIM_DIR:$PATH"
  echo "==> [PODMAN SHIM] docker commands will be forwarded to podman"
fi

echo "==> Running: python3 scripts/run_build.py ${ARGS[*]}"
echo ""
python3 "$REPO_ROOT/scripts/run_build.py" "${ARGS[@]}"

# 安装到设备
if $INSTALL && [ -f "$LPK_OUTPUT" ]; then
  # 从 manifest 读取 pkgId
  PKG_ID="$(grep -m1 '^package:' "$APP_ROOT/lzc-manifest.yml" | awk '{print $2}' | tr -d '"' || true)"
  echo ""
  echo "==> Installing $LPK_OUTPUT to device..."
  if [ -n "$PKG_ID" ]; then
    echo "==> Uninstalling old version: $PKG_ID"
    lzc-cli app uninstall "$PKG_ID" 2>/dev/null || true
  fi
  lzc-cli app install "$LPK_OUTPUT"
  echo "==> Done."
fi
