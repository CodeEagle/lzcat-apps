#!/bin/sh
# LazyCat entrypoint for copilot-api-plus

# Inject GitHub token if GH_TOKEN is provided
if [ -n "$GH_TOKEN" ]; then
  mkdir -p /root/.local/share/copilot-api-plus
  echo "$GH_TOKEN" > /root/.local/share/copilot-api-plus/github_token
  chmod 600 /root/.local/share/copilot-api-plus/github_token
fi

# Run the original entrypoint
exec /app/entrypoint.sh
