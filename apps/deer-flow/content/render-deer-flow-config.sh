#!/bin/sh
set -eu

CONFIG_PATH="${DEER_FLOW_CONFIG_PATH:-/lzcapp/var/data/deer-flow/config/config.yaml}"
CONFIG_ENV_PATH="${DEER_FLOW_CONFIG_ENV_PATH:-/lzcapp/var/data/deer-flow/config/model.env}"
READY_MARKER="${DEER_FLOW_READY_MARKER:-/lzcapp/var/data/deer-flow/config/.lazycat-config-ready}"
CONFIG_DIR="$(dirname "$CONFIG_PATH")"
mkdir -p "$CONFIG_DIR"

quote_yaml() {
  printf '"%s"' "$(printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g')"
}

if [ -f "$CONFIG_ENV_PATH" ]; then
  # shellcheck disable=SC1090
  . "$CONFIG_ENV_PATH"
fi

provider="${DEER_FLOW_MODEL_PROVIDER_PRESET:-openai}"
model_name="${DEER_FLOW_MODEL_NAME:-default-chat}"
display_name="${DEER_FLOW_MODEL_DISPLAY_NAME:-Default Chat Model}"
model_id="${DEER_FLOW_MODEL_ID:-gpt-4.1-mini}"
base_url="${DEER_FLOW_MODEL_BASE_URL:-}"
api_key_value="${DEER_FLOW_MODEL_API_KEY:-}"
api_key_ref='\$DEER_FLOW_MODEL_API_KEY'
use_responses_api="${DEER_FLOW_MODEL_USE_RESPONSES_API:-false}"
temperature="${DEER_FLOW_MODEL_TEMPERATURE:-0.7}"

if [ "$provider" = "openrouter" ] && [ -z "$base_url" ]; then
  base_url="https://openrouter.ai/api/v1"
fi

{
  echo "# Generated from LazyCat deployment parameters."
  echo "# Re-open App Detail -> Deployment Parameters to update this config."
  echo "config_version: 3"
  echo "log_level: info"
  echo
  echo "models:"
  echo "  - name: $(quote_yaml "$model_name")"
  echo "    display_name: $(quote_yaml "$display_name")"
  echo "    use: langchain_openai:ChatOpenAI"
  echo "    model: $(quote_yaml "$model_id")"
  echo "    api_key: $api_key_ref"
  echo "    max_tokens: 4096"
  echo "    temperature: $temperature"
  if [ -n "$base_url" ]; then
    echo "    base_url: $(quote_yaml "$base_url")"
  fi
  if [ "$use_responses_api" = "true" ]; then
    echo "    use_responses_api: true"
    echo "    output_version: responses/v1"
  fi
  echo
  cat <<'EOF'
tool_groups:
  - name: web
  - name: file:read
  - name: file:write
  - name: bash

tools:
  - name: web_search
    group: web
    use: deerflow.community.tavily.tools:web_search_tool
    max_results: 5
  - name: web_fetch
    group: web
    use: deerflow.community.jina_ai.tools:web_fetch_tool
    timeout: 10
  - name: image_search
    group: web
    use: deerflow.community.image_search.tools:image_search_tool
    max_results: 5
  - name: ls
    group: file:read
    use: deerflow.sandbox.tools:ls_tool
  - name: read_file
    group: file:read
    use: deerflow.sandbox.tools:read_file_tool
  - name: write_file
    group: file:write
    use: deerflow.sandbox.tools:write_file_tool
  - name: str_replace
    group: file:write
    use: deerflow.sandbox.tools:str_replace_tool
  - name: bash
    group: bash
    use: deerflow.sandbox.tools:bash_tool

sandbox:
  use: deerflow.sandbox.local:LocalSandboxProvider

skills:
  path: /lzcapp/var/data/deer-flow/skills
  container_path: /mnt/skills

title:
  enabled: true
  max_words: 6
  max_chars: 60
  model_name: null

summarization:
  enabled: true
EOF
} > "$CONFIG_PATH"

if [ -n "$model_id" ] && [ -n "$api_key_value" ]; then
  printf 'ready\n' > "$READY_MARKER"
else
  rm -f "$READY_MARKER"
fi
