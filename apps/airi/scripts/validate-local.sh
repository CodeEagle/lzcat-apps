#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# preflight 预检已内置在 full_migrate.py 中，此处做基本文件检查
for f in lzc-manifest.yml lzc-build.yml README.md; do
  [ -f "$ROOT_DIR/$f" ] || { echo "Missing required file: $f" >&2; exit 1; }
done
sh -n "$ROOT_DIR/lazycat/start-airi.sh"
lzc-cli project build "$ROOT_DIR"
