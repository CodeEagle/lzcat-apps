#!/bin/sh

set -eu

export PYTHONPATH=/app
export PYTHONUNBUFFERED=1

mkdir -p /app/data/projects /app/data/uploads /app/data/temp /app/data/output /app/logs
rm -rf /app/uploads /app/output
ln -s /app/data/uploads /app/uploads
ln -s /app/data/output /app/output

exec celery -A backend.core.celery_app worker \
  --loglevel=info \
  --concurrency="${CELERY_CONCURRENCY:-2}" \
  --queues="celery,processing,video,notification,upload"
