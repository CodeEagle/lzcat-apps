#!/usr/bin/env bash
set -u

NPM_AGENT_PACKAGES="${CC_CONNECT_NPM_AGENT_PACKAGES:-@anthropic-ai/claude-code@latest @openai/codex@latest @google/gemini-cli@latest @iflow-ai/iflow-cli@latest opencode-ai@latest}"
INSTALL_KIMI="${CC_CONNECT_INSTALL_KIMI:-1}"
INSTALL_QODER="${CC_CONNECT_INSTALL_QODER:-1}"
KIMI_UV_TOOL_DIR="${CC_CONNECT_KIMI_UV_TOOL_DIR:-/usr/local/share/uv/tools}"
KIMI_UV_TOOL_BIN_DIR="${CC_CONNECT_KIMI_UV_TOOL_BIN_DIR:-/usr/local/bin}"
QODER_INSTALL_HOME="${CC_CONNECT_QODER_INSTALL_HOME:-${HOME:-/root}}"

is_executable_file() {
  [ -f "$1" ] && [ -x "$1" ]
}

link_executable() {
  local target="$1"
  local link="$2"
  is_executable_file "${target}" || return 1
  ln -sf "${target}" "${link}"
}

ensure_npm_agent_links() {
  command -v npm >/dev/null 2>&1 || return 0
  local npm_root
  npm_root="$(npm root -g 2>/dev/null || true)"
  [ -n "${npm_root}" ] || return 0

  link_executable "${npm_root}/@anthropic-ai/claude-code/bin/claude.exe" /usr/local/bin/claude || true
  link_executable "${npm_root}/@openai/codex/bin/codex.js" /usr/local/bin/codex || true
  link_executable "${npm_root}/@google/gemini-cli/bundle/gemini.js" /usr/local/bin/gemini || true
  link_executable "${npm_root}/@iflow-ai/iflow-cli/bundle/entry.js" /usr/local/bin/iflow || true
  link_executable "${npm_root}/opencode-ai/bin/opencode" /usr/local/bin/opencode || true
}

find_qoder_binary() {
  local candidate dir
  for candidate in \
    "${HOME:-/root}/.local/bin/qodercli" \
    "${QODER_INSTALL_HOME}/.local/bin/qodercli" \
    "/opt/qoder/.local/bin/qodercli" \
    "/root/.local/bin/qodercli"; do
    if is_executable_file "${candidate}" && "${candidate}" --version >/dev/null 2>&1; then
      printf '%s\n' "${candidate}"
      return 0
    fi
  done

  for dir in \
    "${HOME:-/root}/.qoder/bin/qodercli" \
    "${QODER_INSTALL_HOME}/.qoder/bin/qodercli" \
    "/opt/qoder/.qoder/bin/qodercli" \
    "/root/.qoder/bin/qodercli"; do
    for candidate in "${dir}"/qodercli-*; do
      if is_executable_file "${candidate}" && "${candidate}" --version >/dev/null 2>&1; then
        printf '%s\n' "${candidate}"
        return 0
      fi
    done
  done

  return 1
}

ensure_qoder_link() {
  local binary
  binary="$(find_qoder_binary)" || return 1
  ln -sf "${binary}" /usr/local/bin/qodercli
  command -v qodercli >/dev/null 2>&1
}

ensure_kimi_link() {
  local candidate
  for candidate in \
    "${KIMI_UV_TOOL_BIN_DIR}/kimi" \
    "${HOME:-/root}/.local/bin/kimi" \
    "/data/home/.local/bin/kimi" \
    "/root/.local/bin/kimi"; do
    if is_executable_file "${candidate}"; then
      [ "${candidate}" = "/usr/local/bin/kimi" ] || ln -sf "${candidate}" /usr/local/bin/kimi
      return 0
    fi
  done
  return 1
}

ensure_agent_links() {
  ensure_npm_agent_links
  ensure_kimi_link || true
  ensure_qoder_link || true
}

run_step() {
  local label="$1"
  shift
  echo "[agent-cli] ${label}"
  "$@"
  local code=$?
  if [ "${code}" -eq 0 ]; then
    return 0
  fi
  echo "[agent-cli] warning: ${label} failed with exit code ${code}" >&2
  if [ "${REQUIRED}" = "1" ]; then
    return "${code}"
  fi
  return 0
}

install_npm_agents() {
  [ -n "${NPM_AGENT_PACKAGES}" ] || return 0
  command -v npm >/dev/null 2>&1 || {
    echo "npm not found" >&2
    return 127
  }

  local code=0
  # shellcheck disable=SC2086
  npm install -g --no-audit --no-fund ${NPM_AGENT_PACKAGES} || code=$?
  ensure_npm_agent_links
  return "${code}"
}

install_uv() {
  if command -v uv >/dev/null 2>&1; then
    return 0
  fi
  if is_executable_file /usr/local/bin/uv; then
    return 0
  fi
  command -v curl >/dev/null 2>&1 || {
    echo "curl not found" >&2
    return 127
  }

  local install_dir="${CC_CONNECT_UV_INSTALL_DIR:-/usr/local/bin}"
  mkdir -p "${install_dir}"
  export UV_INSTALL_DIR="${install_dir}"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  command -v uv >/dev/null 2>&1 || is_executable_file "${install_dir}/uv"
}

install_kimi() {
  [ "${INSTALL_KIMI}" != "0" ] || return 0
  install_uv || return $?

  local uv_bin
  uv_bin="$(command -v uv 2>/dev/null || true)"
  [ -n "${uv_bin}" ] || uv_bin="/usr/local/bin/uv"
  is_executable_file "${uv_bin}" || {
    echo "uv not found" >&2
    return 127
  }

  mkdir -p "${KIMI_UV_TOOL_DIR}" "${KIMI_UV_TOOL_BIN_DIR}"
  UV_TOOL_DIR="${KIMI_UV_TOOL_DIR}" \
    UV_TOOL_BIN_DIR="${KIMI_UV_TOOL_BIN_DIR}" \
    "${uv_bin}" tool install --python 3.13 --force kimi-cli
  ensure_kimi_link
  command -v kimi >/dev/null 2>&1
}

install_qoder() {
  [ "${INSTALL_QODER}" != "0" ] || return 0
  command -v curl >/dev/null 2>&1 || {
    echo "curl not found" >&2
    return 127
  }

  mkdir -p "${QODER_INSTALL_HOME}"
  local code=0
  curl -fsSL https://qoder.com/install | HOME="${QODER_INSTALL_HOME}" bash -s -- --force || code=$?
  if ensure_qoder_link; then
    if [ "${code}" -ne 0 ]; then
      echo "[agent-cli] qoder installer failed, using existing qodercli binary" >&2
    fi
    return 0
  fi
  return "${code}"
}

MODE="${1:---best-effort}"
if [ "${MODE}" = "--link-only" ]; then
  ensure_agent_links
  exit 0
fi

REQUIRED=0
if [ "${MODE}" = "--required" ]; then
  REQUIRED=1
fi
FAILED=0

run_step "install/update npm agent CLIs" install_npm_agents || FAILED=1
run_step "install/update Kimi CLI" install_kimi || FAILED=1
run_step "install/update Qoder CLI" install_qoder || FAILED=1

ensure_agent_links

if command -v npm >/dev/null 2>&1; then
  npm cache clean --force >/dev/null 2>&1 || true
fi
if command -v uv >/dev/null 2>&1; then
  uv cache clean >/dev/null 2>&1 || true
fi

if [ "${REQUIRED}" = "1" ] && [ "${FAILED}" = "1" ]; then
  exit 1
fi
