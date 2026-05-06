#!/bin/sh
set -eu

CONFIG_DIR="/lzcapp/config"
CONFIG_FILE="$CONFIG_DIR/config.json"
APP_CONFIG_LINK="/app/config.json"

mkdir -p /app/tmp
mkdir -p "$CONFIG_DIR"
mkdir -p /lzcapp/var/workspace

# Older broken releases could leave config.json as a directory via a file bind.
# Only remove that exact bad shape; keep valid files untouched.
if [ -d "$CONFIG_FILE" ]; then
  echo "Removing legacy config directory at $CONFIG_FILE"
  rm -rf "$CONFIG_FILE"
fi

# If /app/config.json itself was turned into a directory, remove only that bad case.
if [ -d "$APP_CONFIG_LINK" ] && [ ! -L "$APP_CONFIG_LINK" ]; then
  echo "Removing legacy app config directory at $APP_CONFIG_LINK"
  rm -rf "$APP_CONFIG_LINK"
fi

if [ ! -f "$CONFIG_FILE" ]; then
  cat >"$CONFIG_FILE" <<'EOF'
{
  "channel_type": "web",
  "web_port": 9899,
  "model": "chatgpt",
  "conversation_max_tokens": 4096,
  "character_desc": "你是一个智能助手",
  "agent": true,
  "agent_workspace": "/root/cow"
}
EOF
  echo "Created default config.json"
fi

ln -snf "$CONFIG_FILE" "$APP_CONFIG_LINK"
