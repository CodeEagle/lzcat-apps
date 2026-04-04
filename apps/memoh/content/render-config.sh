#!/bin/sh
set -eu

TARGET_PATH="${1:?target config path required}"
CONFIG_DIR="/lzcapp/var/data/memoh/config"
CONFIG_FILE="${CONFIG_DIR}/config.toml"

mkdir -p "${CONFIG_DIR}"

if [ ! -f "${CONFIG_FILE}" ]; then
  cat > "${CONFIG_FILE}" <<EOF
[log]
level = "info"
format = "text"

[server]
addr = "0.0.0.0:8080"

[admin]
username = "admin"
password = "${LAZYCAT_APP_ID}-admin"
email = "admin@${LAZYCAT_APP_DOMAIN}"

[auth]
jwt_secret = "${LAZYCAT_APP_ID}-${LAZYCAT_BOX_DOMAIN}-jwt"
jwt_expires_in = "168h"

timezone = "UTC"

[containerd]
socket_path = "/run/containerd/containerd.sock"
namespace = "default"

[workspace]
default_image = "debian:bookworm-slim"
snapshotter = "overlayfs"
data_root = "/opt/memoh/data"
runtime_dir = "/opt/memoh/runtime"

[postgres]
host = "postgres"
port = 5432
user = "memoh"
password = "memoh123"
database = "memoh"
sslmode = "disable"

[qdrant]
base_url = "http://qdrant:6334"
api_key = ""
timeout_seconds = 10

[browser_gateway]
host = "browser"
port = 8083
server_addr = "server:8080"

[web]
host = "0.0.0.0"
port = 8082
EOF
fi

cp "${CONFIG_FILE}" "${TARGET_PATH}"
