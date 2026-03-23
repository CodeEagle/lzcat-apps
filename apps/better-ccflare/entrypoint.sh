#!/bin/sh
set -eu

APP_DATA_DIR=/home/bun/.config/better-ccflare

# better-ccflare only allows config files under /home/bun and /tmp.
# Persist the whole app state under the allowed config directory, then keep
# /data as a compatibility symlink for any hardcoded legacy paths.
install -d -o bun -g bun /home/bun/.config "$APP_DATA_DIR" "$APP_DATA_DIR/logs"
chown -R bun:bun /home/bun/.config
rm -rf /data
ln -sfn "$APP_DATA_DIR" /data

exec runuser -u bun -- /usr/local/bin/better-ccflare "$@"
