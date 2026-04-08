#!/bin/sh
set -eu

# Remap lzcat deploy params (HERMES_WEBUI_AIO_ prefix) to hermes standard env vars
export OPENROUTER_API_KEY="${HERMES_WEBUI_AIO_OPENROUTER_API_KEY:-${OPENROUTER_API_KEY:-}}"
export ANTHROPIC_API_KEY="${HERMES_WEBUI_AIO_ANTHROPIC_API_KEY:-${ANTHROPIC_API_KEY:-}}"
export OPENAI_API_KEY="${HERMES_WEBUI_AIO_OPENAI_API_KEY:-${OPENAI_API_KEY:-}}"
export GOOGLE_API_KEY="${HERMES_WEBUI_AIO_GOOGLE_API_KEY:-${GOOGLE_API_KEY:-}}"

# Write default model to hermes config.yaml if provided
DEFAULT_MODEL="${HERMES_WEBUI_AIO_DEFAULT_MODEL:-}"
if [ -n "$DEFAULT_MODEL" ]; then
    CONFIG_DIR="${HERMES_HOME:-/root/.hermes}"
    mkdir -p "$CONFIG_DIR"
    CONFIG_FILE="$CONFIG_DIR/config.yaml"
    if [ ! -f "$CONFIG_FILE" ]; then
        printf 'model:\n  default: "%s"\n' "$DEFAULT_MODEL" > "$CONFIG_FILE"
    fi
fi

exec python /app/server.py
