#!/bin/sh

set -eu

export PYTHONPATH=/app
export PYTHONUNBUFFERED=1

mkdir -p /app/data/projects /app/data/uploads /app/data/temp /app/data/output /app/logs

# Keep legacy root paths mapped into the persisted data tree.
rm -rf /app/uploads /app/output
ln -s /app/data/uploads /app/uploads
ln -s /app/data/output /app/output

if [ ! -f /app/data/autoclip.db ]; then
  python - <<'PY'
import sys
sys.path.insert(0, '/app')
from backend.core.database import engine, Base
from backend.models import project, task, clip, collection, bilibili
Base.metadata.create_all(bind=engine)
PY
fi

python - <<'PY' || true
import os
import redis
redis_url = os.getenv('REDIS_URL', 'redis://redis:6379/0')
try:
    redis.Redis.from_url(redis_url, decode_responses=True).ping()
    print(f'Redis连接成功: {redis_url}')
except Exception as exc:
    print(f'Redis连接失败: {exc}')
PY

python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 &
UVICORN_PID=$!
NGINX_PID=

cleanup() {
  [ -n "${UVICORN_PID:-}" ] && kill "$UVICORN_PID" 2>/dev/null || true
  [ -n "${NGINX_PID:-}" ] && kill "$NGINX_PID" 2>/dev/null || true
}

trap cleanup INT TERM

# Wait for uvicorn to be ready before starting nginx, to avoid 502 on startup health checks.
i=0
while [ $i -lt 30 ]; do
  if curl -s -o /dev/null http://127.0.0.1:8000/openapi.json 2>/dev/null; then
    break
  fi
  sleep 1
  i=$((i + 1))
done

nginx -g 'daemon off;' &
NGINX_PID=$!

while kill -0 "$UVICORN_PID" 2>/dev/null && kill -0 "$NGINX_PID" 2>/dev/null; do
  sleep 2
done

cleanup
wait "$UVICORN_PID" 2>/dev/null || true
wait "$NGINX_PID" 2>/dev/null || true
exit 1
