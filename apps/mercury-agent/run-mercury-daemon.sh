#!/bin/sh
# Foreground daemon run by supervisord. Stays out of the way until the user
# completes setup via the web terminal (mercury.yaml is created on first run);
# supervisord autorestart will pick us up when the file appears.
export MERCURY_HOME="${MERCURY_HOME:-/data}"
export HOME="${HOME:-/root}"
. /data/shell-path.sh 2>/dev/null || true

if [ ! -f "${MERCURY_HOME}/mercury.yaml" ]; then
  echo "[mercury-daemon] mercury.yaml not found at ${MERCURY_HOME}; waiting for setup..."
  while [ ! -f "${MERCURY_HOME}/mercury.yaml" ]; do
    sleep 30
  done
  echo "[mercury-daemon] mercury.yaml found, starting daemon"
fi

cd "${MERCURY_HOME}" 2>/dev/null || cd /data
exec /usr/local/bin/mercury start --daemon
