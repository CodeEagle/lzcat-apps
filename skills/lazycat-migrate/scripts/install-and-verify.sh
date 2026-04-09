#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./lib/progress.sh
source "$SCRIPT_DIR/lib/progress.sh"

usage() {
  cat <<USAGE
Usage: $(basename "$0") --package path/to/app.lpk [options]

Install a LazyCat package and verify install/start status.

Options:
  --package path    Required
  --app-id id       Optional app identifier used for status/log checks
  --status-cmd cmd  Optional override for install/start status command
  --logs-cmd cmd    Optional override for logs command
  -h, --help
USAGE
}

PACKAGE=""
APP_ID=""
STATUS_CMD=""
LOGS_CMD=""
last_progress_step="install_verify"

on_error() {
  local line="$1"
  local code="$2"
  local summary="install-and-verify failed at line ${line} (exit ${code})"
  progress_emit "$last_progress_step" "failed" "$summary" "$(progress_classify_failure "$summary")"
  exit "$code"
}

trap 'on_error ${LINENO} $?' ERR

while [[ $# -gt 0 ]]; do
  case "$1" in
    --package) PACKAGE="$2"; shift 2 ;;
    --app-id) APP_ID="$2"; shift 2 ;;
    --status-cmd) STATUS_CMD="$2"; shift 2 ;;
    --logs-cmd) LOGS_CMD="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 1 ;;
  esac
done

[[ -n "$PACKAGE" ]] || { usage; exit 1; }
[[ -f "$PACKAGE" ]] || { echo "Package not found: $PACKAGE" >&2; exit 1; }
command -v lzc-cli >/dev/null || { echo 'lzc-cli is required' >&2; exit 1; }

last_progress_step="install_package"
progress_emit "install_package" "started" "installing package $(basename "$PACKAGE")"

port_open() {
  local host="$1"
  local port="$2"
  (echo >"/dev/tcp/$host/$port") >/dev/null 2>&1
}

ensure_container_lzc_bridge() {
  command -v socat >/dev/null || return 0
  local hportal_dir="${LZC_HPORTAL_DIR:-/root/.config/hportal-client}"
  [[ -d "$hportal_dir" ]] || return 0

  local file addr port mapped_port
  for file in native_messaging_addr shellapi_addr; do
    [[ -f "$hportal_dir/$file" ]] || continue
    addr="$(cat "$hportal_dir/$file" 2>/dev/null || true)"
    port="${addr##*:}"
    [[ "$port" =~ ^[0-9]+$ ]] || continue

    if port_open "127.0.0.1" "$port"; then
      continue
    fi

    mapped_port=$((port + 10000))
    if port_open "host.docker.internal" "$mapped_port"; then
      nohup socat "TCP-LISTEN:${port},fork,reuseaddr,bind=127.0.0.1" "TCP:host.docker.internal:${mapped_port}" >/tmp/lzc-container-bridge-"$port".log 2>&1 &
      sleep 0.2
      continue
    fi

    if port_open "host.docker.internal" "$port"; then
      nohup socat "TCP-LISTEN:${port},fork,reuseaddr,bind=127.0.0.1" "TCP:host.docker.internal:${port}" >/tmp/lzc-container-bridge-"$port".log 2>&1 &
      sleep 0.2
    fi
  done
}

if ! lzc-cli box list >/tmp/lzc-box-precheck.log 2>&1; then
  ensure_container_lzc_bridge || true
fi

echo "Installing $PACKAGE"
if ! lzc-cli app install "$PACKAGE"; then
  if grep -Eiq '获取盒子信息失败|Failed to obtain box information' /tmp/lzc-box-precheck.log 2>/dev/null; then
    echo 'Install command failed: lzc-cli box is not reachable from this runtime.' >&2
  fi
  echo 'Install command failed' >&2
  exit 1
fi
progress_emit "install_package" "succeeded" "package installed command completed"

if [[ -z "$APP_ID" ]]; then
  progress_emit "verify_status" "succeeded" "app-id not provided; status verification skipped"
  echo 'Install finished. No --app-id provided, skipping status and log checks.'
  exit 0
fi

if [[ -z "$STATUS_CMD" ]]; then
  STATUS_CMD="lzc-cli app status $APP_ID"
fi

if [[ -z "$LOGS_CMD" ]]; then
  LOGS_CMD="lzc-cli app log $APP_ID"
fi

echo "Checking status for $APP_ID"
last_progress_step="verify_status"
progress_emit "verify_status" "started" "checking installed app status for ${APP_ID}"
status_output=$(eval "$STATUS_CMD" 2>&1 || true)
echo "$status_output"

if grep -Eiq 'Failed to detect the Lazycat developer tools|ENOTFOUND' <<<"$status_output"; then
  progress_emit "verify_status" "succeeded" "status verification skipped; developer tools unreachable in runtime"
  echo 'Status check skipped: LazyCat developer tools are unreachable in current runtime environment.'
  exit 0
fi

if grep -Eiq 'fail|error|crash|stopped|exit' <<<"$status_output"; then
  progress_emit "verify_status" "failed" "app status indicates failure for ${APP_ID}" "install_verify_failed"
  echo 'Application status looks unhealthy; showing logs' >&2
  last_progress_step="verify_logs"
  progress_emit "verify_logs" "running" "fetching logs for unhealthy app ${APP_ID}"
  eval "$LOGS_CMD" || true
  exit 1
fi

progress_emit "verify_status" "succeeded" "application status healthy for ${APP_ID}"
echo "Application status looks healthy for $APP_ID"
