#!/bin/sh
set -eu

# Remap lzcat deploy params (HERMES_WEBUI_AIO_ prefix) to hermes standard env vars
export OPENROUTER_API_KEY="${HERMES_WEBUI_AIO_OPENROUTER_API_KEY:-${OPENROUTER_API_KEY:-}}"
export ANTHROPIC_API_KEY="${HERMES_WEBUI_AIO_ANTHROPIC_API_KEY:-${ANTHROPIC_API_KEY:-}}"
export OPENAI_API_KEY="${HERMES_WEBUI_AIO_OPENAI_API_KEY:-${OPENAI_API_KEY:-}}"
export GOOGLE_API_KEY="${HERMES_WEBUI_AIO_GOOGLE_API_KEY:-${GOOGLE_API_KEY:-}}"

# Default model: env var takes precedence, applied on every startup
if [ -n "${HERMES_WEBUI_AIO_DEFAULT_MODEL:-}" ]; then
    export HERMES_WEBUI_DEFAULT_MODEL="$HERMES_WEBUI_AIO_DEFAULT_MODEL"
fi

exec python /app/server.py
