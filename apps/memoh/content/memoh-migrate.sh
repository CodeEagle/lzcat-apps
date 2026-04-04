#!/bin/sh
set -eu

sh /lzcapp/pkg/content/render-config.sh /app/config.toml
/app/memoh-server migrate up
touch /tmp/migrate-ready
exec tail -f /dev/null
