#!/usr/bin/env bash

set -euo pipefail

require_command() {
  local cmd="$1"
  command -v "$cmd" >/dev/null 2>&1 || {
    echo "$cmd is required" >&2
    exit 1
  }
}

ensure_gh_auth() {
  local expected_user="${1:-CodeEagle}"
  local current_user=""
  local token=""

  require_command gh

  current_user="$(gh api user --jq '.login' 2>/dev/null || true)"

  if [[ "$current_user" != "$expected_user" ]] && gh auth status >/dev/null 2>&1; then
    echo "Switching gh auth to $expected_user"
    if gh auth switch --help 2>&1 | grep -q -- ' -u'; then
      gh auth switch -u "$expected_user" >/dev/null 2>&1 || true
    fi
    current_user="$(gh api user --jq '.login' 2>/dev/null || true)"
  fi

  if [[ "$current_user" != "$expected_user" ]]; then
    token="${GH_TOKEN:-${GITHUB_TOKEN:-}}"
    if [[ -n "$token" ]]; then
      current_user="$(GH_TOKEN="$token" gh api user --jq '.login' 2>/dev/null || true)"
    fi
  fi

  if [[ "$current_user" != "$expected_user" ]]; then
    echo "Expected gh auth user $expected_user, got ${current_user:-<unknown>}" >&2
    exit 1
  fi
}

repo_name_from_upstream() {
  local upstream_repo="$1"
  printf '%s\n' "${upstream_repo##*/}"
}
