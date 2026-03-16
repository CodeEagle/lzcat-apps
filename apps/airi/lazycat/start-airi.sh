#!/bin/sh
set -eu

mkdir -p /var/log/airi /run/nginx

pnpm -F @proj-airi/server start > /var/log/airi/server.log 2>&1 &
SERVER_PID=$!

nginx -g 'daemon off;' > /var/log/airi/nginx.log 2>&1 &
NGINX_PID=$!

cleanup() {
  kill "$SERVER_PID" 2>/dev/null || true
  kill "$NGINX_PID" 2>/dev/null || true
}

trap cleanup INT TERM EXIT

while kill -0 "$SERVER_PID" 2>/dev/null && kill -0 "$NGINX_PID" 2>/dev/null; do
  sleep 1
done
