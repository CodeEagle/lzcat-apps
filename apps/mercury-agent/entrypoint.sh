#!/bin/sh
set -eu

DATA_DIR="${MERCURY_HOME:-/data}"
mkdir -p \
  "${DATA_DIR}" \
  "${DATA_DIR}/memory" \
  "${DATA_DIR}/workspace" \
  "${DATA_DIR}/.local/bin" \
  "${DATA_DIR}/bin" \
  /var/log/supervisor

# Persist user-installed CLI tools across container recreations.
if [ ! -e /root/.local ]; then
  ln -s "${DATA_DIR}/.local" /root/.local
elif [ -d /root/.local ] && [ ! -L /root/.local ]; then
  cp -an /root/.local/. "${DATA_DIR}/.local/" 2>/dev/null || true
  rm -rf /root/.local
  ln -s "${DATA_DIR}/.local" /root/.local
fi

# Seed default .env from .env.example on first boot.
if [ ! -f "${DATA_DIR}/.env" ] && [ -f /app/.env.example ]; then
  cp /app/.env.example "${DATA_DIR}/.env"
fi

# Persistent shell PATH for interactive web terminal sessions.
cat > "${DATA_DIR}/shell-path.sh" <<'EOF'
export PATH="/data/bin:$HOME/.local/bin:$PATH"
EOF
for rc in /root/.profile /root/.bashrc; do
  if [ ! -e "$rc" ]; then
    ln -s "${DATA_DIR}/shell-path.sh" "$rc"
  elif ! grep -q '/data/shell-path.sh' "$rc" 2>/dev/null; then
    printf '\n[ -f /data/shell-path.sh ] && . /data/shell-path.sh\n' >> "$rc"
  fi
done

export PATH="/data/bin:/root/.local/bin:${PATH}"

exec /usr/bin/supervisord -c /etc/supervisor/supervisord.conf
