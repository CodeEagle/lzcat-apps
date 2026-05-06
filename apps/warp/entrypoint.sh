#!/bin/sh
set -eu

install -d -o warp -g warp -m 0755 /home/warp /workspace
install -d -o warp -g warp -m 0700 \
  /tmp/runtime-warp \
  /home/warp/.warp \
  /home/warp/.ssh \
  /home/warp/.config \
  /home/warp/.cache \
  /home/warp/.local/share \
  /home/warp/.local/state \
  /home/warp/.config/warp-terminal \
  /home/warp/.local/share/warp-terminal \
  /home/warp/.local/state/warp-terminal \
  /home/warp/.cache/warp-terminal

if [ ! -f /home/warp/.zshrc ]; then
  printf 'export TERM=xterm-256color\ncd /workspace\n' > /home/warp/.zshrc
fi

chown -R warp:warp /home/warp /workspace /tmp/runtime-warp

exec /usr/bin/supervisord -c /etc/supervisor/conf.d/warp.conf
