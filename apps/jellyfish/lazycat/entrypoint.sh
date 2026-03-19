#!/bin/sh
set -eu

mkdir -p "${JELLYFISH_DATA_DIR:-/data}" "${LOCAL_STORAGE_DIR:-/data/storage}"

cd /opt/jellyfish/backend

uvicorn app.main:app --host 127.0.0.1 --port "${PORT:-8000}" &
UVICORN_PID=$!

cleanup() {
  kill "$UVICORN_PID" 2>/dev/null || true
}

trap cleanup INT TERM

nginx -g 'daemon off;' &
NGINX_PID=$!

wait "$UVICORN_PID" "$NGINX_PID"
