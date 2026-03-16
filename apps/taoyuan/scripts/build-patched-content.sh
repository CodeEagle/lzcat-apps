#!/usr/bin/env bash

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: build-patched-content.sh <upstream_src_dir> <content_dir>

Clone/build helper for TaoYuan's patched static assets.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

UPSTREAM_SRC_DIR="${1:-}"
CONTENT_DIR="${2:-}"

if [[ -z "$UPSTREAM_SRC_DIR" || -z "$CONTENT_DIR" ]]; then
  usage >&2
  exit 1
fi

MAIN_MENU_FILE="$UPSTREAM_SRC_DIR/src/views/MainMenu.vue"

if [[ ! -f "$MAIN_MENU_FILE" ]]; then
  echo "missing file: $MAIN_MENU_FILE" >&2
  exit 1
fi

python3 - "$MAIN_MENU_FILE" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text()

needle = "    void router.push('/game')\n"
patch = """    // New games should persist immediately so players do not lose progress\n    // before the first end-of-day autosave runs.\n    if (!saveStore.saveToSlot(slot)) {\n      showFloat('初始存档创建失败。', 'danger')\n      return\n    }\n\n    void router.push('/game')\n"""

if "saveStore.saveToSlot(slot)" in text:
    sys.exit(0)

if needle not in text:
    raise SystemExit("failed to find router push anchor in MainMenu.vue")

text = text.replace(needle, patch, 1)
path.write_text(text)
PY

cd "$UPSTREAM_SRC_DIR"
if ! command -v pnpm >/dev/null 2>&1; then
  corepack enable
  corepack prepare pnpm@latest --activate
fi
pnpm install --frozen-lockfile
pnpm build

mkdir -p "$CONTENT_DIR"
rsync -a --delete "$UPSTREAM_SRC_DIR/docs/" "$CONTENT_DIR/"
