FROM debian:bookworm

ARG DEBIAN_FRONTEND=noninteractive
ARG TARGETARCH
ARG WARP_DEB_VERSION=0.2026.04.27.15.32.stable.02

ENV HOME=/home/warp \
    DISPLAY=:0 \
    XDG_RUNTIME_DIR=/tmp/runtime-warp \
    XDG_CONFIG_HOME=/home/warp/.config \
    XDG_DATA_HOME=/home/warp/.local/share \
    XDG_CACHE_HOME=/home/warp/.cache \
    WINIT_UNIX_BACKEND=x11 \
    WGPU_BACKEND=gl \
    LIBGL_ALWAYS_SOFTWARE=1 \
    MESA_LOADER_DRIVER_OVERRIDE=llvmpipe

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
      adwaita-icon-theme \
      ca-certificates \
      curl \
      dbus-x11 \
      fluxbox \
      fontconfig \
      fonts-dejavu-core \
      fonts-noto-color-emoji \
      fonts-noto-cjk \
      gnupg \
      libasound2 \
      libgl1-mesa-dri \
      libnss3 \
      libx11-xcb1 \
      mesa-vulkan-drivers \
      novnc \
      supervisor \
      x11vnc \
      xdg-utils \
      xterm \
      xvfb \
      zsh; \
    install -d -m 0755 /etc/apt/keyrings; \
    curl -fsSL https://releases.warp.dev/linux/keys/warp.asc | gpg --dearmor -o /etc/apt/keyrings/warpdotdev.gpg; \
    case "${TARGETARCH:-amd64}" in \
      amd64) deb_arch=amd64 ;; \
      arm64) deb_arch=arm64 ;; \
      *) echo "unsupported TARGETARCH=${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    echo "deb [arch=${deb_arch} signed-by=/etc/apt/keyrings/warpdotdev.gpg] https://releases.warp.dev/linux/deb stable main" > /etc/apt/sources.list.d/warpdotdev.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends "warp-terminal=${WARP_DEB_VERSION}"; \
    useradd -m -d /home/warp -s /usr/bin/zsh -u 1000 warp; \
    install -d -o warp -g warp -m 0755 /workspace /home/warp; \
    install -d -o warp -g warp -m 0700 /tmp/runtime-warp /home/warp/.warp /home/warp/.ssh /home/warp/.config /home/warp/.cache /home/warp/.local/share /home/warp/.local/state; \
    rm -rf /var/lib/apt/lists/*

COPY supervisord.conf /etc/supervisor/conf.d/warp.conf
COPY entrypoint.sh /usr/local/bin/lazycat-warp-entrypoint
COPY start-warp.sh /usr/local/bin/start-warp

RUN chmod +x /usr/local/bin/lazycat-warp-entrypoint /usr/local/bin/start-warp

EXPOSE 8080

ENTRYPOINT ["/usr/local/bin/lazycat-warp-entrypoint"]
