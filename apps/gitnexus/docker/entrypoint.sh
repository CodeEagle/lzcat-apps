#!/bin/sh
set -e

echo "Starting GitNexus services..."

# 强制使用可持久化可写目录，避免 sqlite "Unable to open database file"
export HOME=/data
export GITNEXUS_REGISTRY_DIR=/data/gitnexus-registry
mkdir -p "$GITNEXUS_REGISTRY_DIR"

# 启动前端静态文件服务 (端口 5173)
# Note: serve doesn't support --header flag, headers are handled by nginx
echo "Starting frontend server on port 5173..."
serve -s dist -l 5173 &

# 启动本地 GitHub 代理服务 (端口 8787)
echo "Starting git proxy server on port 8787..."
node /proxy-server.mjs &

# 等待前端启动
sleep 2

# 启动 gitnexus 后端服务 (端口 4747)
echo "Starting gitnexus backend on port 4747..."
gitnexus serve --host 0.0.0.0 --port 4747 &

# 等待后端启动
sleep 2

# 启动 nginx 代理 (端口 8080)
echo "Starting nginx proxy on port 8080..."
nginx -g 'daemon off;'

# 保持容器运行
wait
