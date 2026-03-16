#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

bash /Users/lincoln/Develop/GitHub/skills/lazycat-migrate/scripts/preflight-check.sh "$ROOT_DIR"
sh -n "$ROOT_DIR/lazycat/start-airi.sh"
lzc-cli project build "$ROOT_DIR"
