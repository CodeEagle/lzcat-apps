#!/bin/sh
set -e

# Create all required paperclip directories with correct ownership.
# This runs as root so it can write to the bind-mounted /paperclip volume
# (which is owned by root on first install).
install -d -o node -g node \
  /paperclip/instances/default/logs \
  /paperclip/instances/default/secrets \
  /paperclip/instances/default/data/storage \
  /paperclip/instances/default/data/backups \
  /paperclip/instances/default/workspaces

chown -R node:node /paperclip

exec gosu node "$@"
