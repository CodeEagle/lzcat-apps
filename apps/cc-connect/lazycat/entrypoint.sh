#!/usr/bin/env bash
set -euo pipefail

DATA_DIR="${CC_CONNECT_DATA_DIR:-/data}"
CONFIG_FILE="${CC_CONNECT_CONFIG:-${DATA_DIR}/config.toml}"
MANAGEMENT_TOKEN="${CC_CONNECT_MANAGEMENT_TOKEN:-}"
BRIDGE_TOKEN="${CC_CONNECT_BRIDGE_TOKEN:-cc-connect-bridge}"
WEBHOOK_TOKEN="${CC_CONNECT_WEBHOOK_TOKEN:-}"

mkdir -p \
  "${DATA_DIR}" \
  "${DATA_DIR}/home" \
  "${DATA_DIR}/home/.config" \
  "${DATA_DIR}/home/.local/share" \
  "${DATA_DIR}/home/.cache" \
  "${DATA_DIR}/home/.agents/skills" \
  "${DATA_DIR}/home/.claude" \
  "${DATA_DIR}/home/.codex" \
  "${DATA_DIR}/state" \
  "${DATA_DIR}/workspaces" \
  "${DATA_DIR}/bin"

export HOME="${HOME:-${DATA_DIR}/home}"
export XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-${HOME}/.config}"
export XDG_DATA_HOME="${XDG_DATA_HOME:-${HOME}/.local/share}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-${HOME}/.cache}"
export CODEX_HOME="${CODEX_HOME:-${HOME}/.codex}"
export PATH="${DATA_DIR}/bin:${PATH}"

if [ "${CC_CONNECT_UPDATE_AGENT_CLIS_ON_START:-1}" != "0" ] && [ -x /usr/local/bin/update-agent-clis.sh ]; then
  (
    echo "[agent-cli] startup update started at $(date -Is)"
    /usr/local/bin/update-agent-clis.sh --best-effort
    echo "[agent-cli] startup update finished at $(date -Is)"
  ) >>"${DATA_DIR}/state/agent-cli-update.log" 2>&1 &
fi

if [ ! -f "${CONFIG_FILE}" ]; then
  umask 077
  cat >"${CONFIG_FILE}" <<EOF
data_dir = "${DATA_DIR}/state"
attachment_send = "on"

[log]
level = "info"

[management]
enabled = true
port = 9820
token = "${MANAGEMENT_TOKEN}"
cors_origins = ["*"]

[bridge]
enabled = true
port = 9810
token = "${BRIDGE_TOKEN}"
path = "/bridge/ws"
cors_origins = ["*"]

[webhook]
enabled = true
port = 9111
token = "${WEBHOOK_TOKEN}"
path = "/hook"
EOF
fi

exec cc-connect --config "${CONFIG_FILE}" "$@"
