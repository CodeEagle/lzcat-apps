#!/usr/bin/env bash

progress_normalize_step() {
  local raw="$1"
  raw="${raw,,}"
  raw="${raw//[^a-z0-9_]/_}"
  raw="${raw//__/_}"
  raw="${raw##_}"
  raw="${raw%%_}"
  if [[ -z "$raw" ]]; then
    raw="migration_progress"
  fi
  printf '%s\n' "$raw"
}

progress_classify_failure() {
  local message="${1,,}"
  if [[ "$message" == *"preflight"* ]]; then
    echo "preflight_failed"
  elif [[ "$message" == *"auth"* || "$message" == *"permission"* || "$message" == *"token"* ]]; then
    echo "auth_failed"
  elif [[ "$message" == *"dispatch"* || "$message" == *"workflow"* || "$message" == *"run"* ]]; then
    echo "workflow_failed"
  elif [[ "$message" == *"artifact"* || "$message" == *".lpk"* || "$message" == *"download"* ]]; then
    echo "package_download_failed"
  elif [[ "$message" == *"install"* || "$message" == *"status"* || "$message" == *"verify"* ]]; then
    echo "install_verify_failed"
  else
    echo "unknown"
  fi
}

progress_enabled() {
  [[ -n "${LAZYCAT_PROGRESS_URL:-}" ]] && command -v curl >/dev/null 2>&1
}

progress_build_payload() {
  local step="$1"
  local status="$2"
  local summary="$3"
  local failure_category="${4:-}"
  local source="${LAZYCAT_PROGRESS_SOURCE:-lazycat_migrate}"

  python3 - "$step" "$status" "$summary" "$failure_category" "$source" <<'PY'
import json
import sys
from datetime import datetime, timezone

step = sys.argv[1]
status = sys.argv[2]
summary = sys.argv[3]
failure_category = sys.argv[4]
source = sys.argv[5]

payload = {
    "schema_version": 1,
    "step": step,
    "status": status,
    "summary": summary,
    "source": source,
    "timestamp": datetime.now(timezone.utc).isoformat(),
}
if failure_category:
    payload["failure_category"] = failure_category

print(json.dumps(payload, ensure_ascii=False))
PY
}

progress_emit() {
  local step
  step="$(progress_normalize_step "$1")"
  local status="$2"
  local summary="$3"
  local failure_category="${4:-}"

  if ! progress_enabled; then
    return 0
  fi

  local payload
  payload="$(progress_build_payload "$step" "$status" "$summary" "$failure_category")"

  local auth_header=()
  if [[ -n "${LAZYCAT_PROGRESS_TOKEN:-}" ]]; then
    auth_header=(-H "Authorization: Bearer ${LAZYCAT_PROGRESS_TOKEN}")
  fi

  curl --silent --show-error --max-time 5 \
    -X POST "${LAZYCAT_PROGRESS_URL}" \
    -H "content-type: application/json" \
    "${auth_header[@]}" \
    -d "$payload" >/dev/null || true
}
