#!/bin/sh
set -eu

mode="${1:-mcp}"

if [ "$#" -gt 0 ]; then
  shift
fi

case "$mode" in
  all)
    exec python /app/packages/lazycat-markitdown-web/run_services.py "$@"
    ;;
  mcp)
    exec python /app/packages/lazycat-markitdown-web/markitdown_mcp.py "$@"
    ;;
  web)
    exec python /app/packages/lazycat-markitdown-web/markitdown_web.py "$@"
    ;;
  *)
    exec "$mode" "$@"
    ;;
esac
