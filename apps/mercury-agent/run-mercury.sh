#!/bin/sh
# Entry script ttyd spawns for every web-terminal session.
# Boots `mercury` CLI; falls back to bash --login if it exits or is missing.
export MERCURY_HOME="${MERCURY_HOME:-/data}"
cd "${MERCURY_HOME}" 2>/dev/null || cd /data
. /data/shell-path.sh 2>/dev/null || true
if command -v mercury >/dev/null 2>&1; then
  mercury || true
fi
exec bash --login
