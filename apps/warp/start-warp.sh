#!/bin/sh
set -eu

export HOME=/home/warp
export DISPLAY=:0
export XDG_RUNTIME_DIR=/tmp/runtime-warp
export XDG_CONFIG_HOME=/home/warp/.config
export XDG_DATA_HOME=/home/warp/.local/share
export XDG_CACHE_HOME=/home/warp/.cache
export WINIT_UNIX_BACKEND=x11
export WGPU_BACKEND=gl
export LIBGL_ALWAYS_SOFTWARE=1
export MESA_LOADER_DRIVER_OVERRIDE=llvmpipe

mkdir -p "$XDG_RUNTIME_DIR" "$XDG_CONFIG_HOME" "$XDG_DATA_HOME" "$XDG_CACHE_HOME" /home/warp/.local/state /home/warp/.warp /workspace
chmod 700 "$XDG_RUNTIME_DIR" /home/warp/.warp
cd /workspace

if command -v dbus-run-session >/dev/null 2>&1; then
  exec dbus-run-session -- warp-terminal
fi

exec warp-terminal
