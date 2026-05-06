# syntax=docker/dockerfile:1.6
# =============================================================================
# Mercury Agent — single image: ttyd (web terminal) + nginx + mercury CLI
# =============================================================================
FROM node:20-bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive \
    MERCURY_HOME=/data \
    MERCURY_BIN=/usr/local/bin/mercury \
    PATH=/data/bin:/root/.local/bin:/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin

# System deps: nginx, supervisord, bash, curl, git, tini
RUN apt-get update && apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        curl \
        git \
        nginx \
        supervisor \
        tini \
    && rm -rf /var/lib/apt/lists/* \
    && rm -f /etc/nginx/conf.d/default.conf /etc/nginx/sites-enabled/default \
    && mkdir -p /etc/nginx/conf.d /var/log/supervisor /data /app/web

# ttyd statically-linked binary (no apt candidate in bookworm-slim).
ARG TTYD_VERSION=1.7.7
RUN curl -fSL -o /usr/bin/ttyd \
        "https://github.com/tsl0922/ttyd/releases/download/${TTYD_VERSION}/ttyd.x86_64" \
    && chmod +x /usr/bin/ttyd \
    && /usr/bin/ttyd --version

# -----------------------------------------------------------------------------
# Mercury CLI (npm registry, pinned by ARG; default = latest)
# -----------------------------------------------------------------------------
ARG MERCURY_VERSION=latest
RUN npm install -g --no-audit --no-fund "@cosmicstack/mercury-agent@${MERCURY_VERSION}" \
    && command -v mercury \
    && mercury --version || true

# -----------------------------------------------------------------------------
# Static web assets (floatball widget + file explorer page) and entry script
# -----------------------------------------------------------------------------
COPY web/ /app/web/
COPY run-mercury.sh /app/run-mercury.sh
COPY run-mercury-daemon.sh /app/run-mercury-daemon.sh
RUN chmod +x /app/run-mercury.sh /app/run-mercury-daemon.sh

# -----------------------------------------------------------------------------
# nginx + supervisord + entrypoint
# -----------------------------------------------------------------------------
COPY nginx/nginx.conf /etc/nginx/nginx.conf
COPY supervisord.conf /etc/supervisor/supervisord.conf
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 80

HEALTHCHECK --interval=15s --timeout=5s --retries=3 --start-period=20s \
    CMD curl -fsS http://127.0.0.1/healthz > /dev/null || exit 1

ENTRYPOINT ["/usr/bin/tini", "--", "/entrypoint.sh"]
