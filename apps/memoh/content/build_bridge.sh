#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: build_bridge.sh [SOURCE_DIR] [TARGET_RUNTIME]

Build the memoh cmd/bridge binary inside a golang container (docker or podman)
and copy the resulting binary to the host runtime directory used by the
LazyCat memoh package.

Arguments:
  SOURCE_DIR     Path to the Memoh repository (default: current directory)
  TARGET_RUNTIME Destination runtime dir on host (default: /lzcapp/var/data/memoh/server/runtime)

Examples:
  # from repo root
  ./apps/memoh/content/build_bridge.sh

  # specify repo root and target runtime
  ./apps/memoh/content/build_bridge.sh /home/user/Memoh /lzcapp/var/data/memoh/server/runtime
EOF
}

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  usage
  exit 0
fi

SOURCE_DIR="${1:-$(pwd)}"
TARGET_RUNTIME="${2:-/lzcapp/var/data/memoh/server/runtime}"

echo "Source dir: $SOURCE_DIR"
echo "Target runtime: $TARGET_RUNTIME"

if [ ! -d "$SOURCE_DIR/cmd/bridge" ]; then
  echo "Error: cmd/bridge not found under $SOURCE_DIR"
  echo "Run this script from the Memoh repo root or pass the repo path as the first arg."
  exit 1
fi

# Detect container engine
ENGINE=""
if command -v podman >/dev/null 2>&1; then
  ENGINE=podman
elif command -v docker >/dev/null 2>&1; then
  ENGINE=docker
else
  echo "Error: neither podman nor docker found. Install one or run on a machine with a container engine."
  exit 1
fi

echo "Using container engine: $ENGINE"

BUILD_DIR="$SOURCE_DIR/build"
mkdir -p "$BUILD_DIR"

echo "Building bridge binary (linux/amd64) inside golang:1.21 container..."
$ENGINE run --rm -v "$SOURCE_DIR":/src -w /src golang:1.21 sh -c "set -e; mkdir -p /src/build; GOOS=linux GOARCH=amd64 go build -trimpath -ldflags='-s -w' -o /src/build/bridge ./cmd/bridge"

if [ ! -f "$BUILD_DIR/bridge" ]; then
  echo "Build failed: $BUILD_DIR/bridge not found"
  exit 2
fi

echo "Build succeeded: $BUILD_DIR/bridge"

# Copy to runtime (may need sudo)
echo "Copying bridge to target runtime: $TARGET_RUNTIME (sudo may be required)"
if [ ! -d "$TARGET_RUNTIME" ]; then
  echo "Creating target runtime directory: $TARGET_RUNTIME"
  sudo mkdir -p "$TARGET_RUNTIME"
fi

sudo cp "$BUILD_DIR/bridge" "$TARGET_RUNTIME/bridge"
sudo chmod +x "$TARGET_RUNTIME/bridge"

# Copy templates if present
if [ -d "$SOURCE_DIR/cmd/bridge/templates" ]; then
  echo "Copying templates to runtime/templates"
  sudo rm -rf "$TARGET_RUNTIME/templates"
  sudo cp -r "$SOURCE_DIR/cmd/bridge/templates" "$TARGET_RUNTIME/templates"
fi

echo "Done. Bridge binary placed at: $TARGET_RUNTIME/bridge"
echo "Restart Memoh server according to your deployment (docker-compose / lzcat). Ensure CONTAINER_BACKEND=local is set and runtime bind is mapped."
