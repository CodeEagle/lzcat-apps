#!/usr/bin/env bash
set -u

MODE="${1:---best-effort}"
REQUIRED=0
if [ "${MODE}" = "--required" ]; then
  REQUIRED=1
fi
FAILED=0

NPM_AGENT_PACKAGES="${CC_CONNECT_NPM_AGENT_PACKAGES:-@anthropic-ai/claude-code@latest @openai/codex@latest @google/gemini-cli@latest @iflow-ai/iflow-cli@latest opencode-ai@latest}"
PIP_AGENT_PACKAGES="${CC_CONNECT_PIP_AGENT_PACKAGES:-kimi-cli}"
INSTALL_QODER="${CC_CONNECT_INSTALL_QODER:-1}"

run_step() {
  local label="$1"
  shift
  echo "[agent-cli] ${label}"
  if "$@"; then
    return 0
  fi
  local code=$?
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
  # shellcheck disable=SC2086
  npm install -g --no-audit --no-fund ${NPM_AGENT_PACKAGES}
}

install_pip_agents() {
  [ -n "${PIP_AGENT_PACKAGES}" ] || return 0
  command -v pip3 >/dev/null 2>&1 || {
    echo "pip3 not found" >&2
    return 127
  }
  # Debian images are externally-managed; this container intentionally owns its
  # Python site-packages so the global CLI is available to cc-connect projects.
  # shellcheck disable=SC2086
  pip3 install --no-cache-dir --break-system-packages --upgrade ${PIP_AGENT_PACKAGES}
}

install_qoder() {
  [ "${INSTALL_QODER}" != "0" ] || return 0
  command -v curl >/dev/null 2>&1 || {
    echo "curl not found" >&2
    return 127
  }
  curl -fsSL https://qoder.com/install | bash
  for candidate in \
    "${HOME:-/root}/.qoder/bin/qodercli" \
    "${HOME:-/root}/.local/bin/qodercli" \
    "/root/.qoder/bin/qodercli" \
    "/root/.local/bin/qodercli"; do
    if [ -x "${candidate}" ]; then
      ln -sf "${candidate}" /usr/local/bin/qodercli
      break
    fi
  done
  command -v qodercli >/dev/null 2>&1
}

run_step "install/update npm agent CLIs" install_npm_agents || FAILED=1
run_step "install/update Kimi CLI" install_pip_agents || FAILED=1
run_step "install/update Qoder CLI" install_qoder || FAILED=1

if command -v npm >/dev/null 2>&1; then
  npm cache clean --force >/dev/null 2>&1 || true
fi

if [ "${REQUIRED}" = "1" ] && [ "${FAILED}" = "1" ]; then
  exit 1
fi
