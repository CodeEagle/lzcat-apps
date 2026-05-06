ARG SOURCE_VERSION=main
ARG UPSTREAM_REPO=0xcaff/codex-web

FROM node:22-bookworm AS builder

ARG SOURCE_VERSION
ARG UPSTREAM_REPO

WORKDIR /usr/src/app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    curl \
    git \
    patch \
    python3 \
    unzip \
    && rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    git clone --depth 1 --branch "${SOURCE_VERSION}" "https://github.com/${UPSTREAM_REPO}.git" . || \
    (git clone "https://github.com/${UPSTREAM_REPO}.git" . && git checkout "${SOURCE_VERSION}")

RUN npm ci --no-audit --no-fund
RUN npm prune --omit=dev --ignore-scripts --no-audit --no-fund

FROM node:22-bookworm-slim AS runner

ARG CODEX_CLI_VERSION=0.126.0-alpha.15

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    ca-certificates \
    curl \
    git \
    openssh-client \
    tini \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g --omit=dev --no-audit --no-fund "@openai/codex@${CODEX_CLI_VERSION}"

ENV NODE_ENV=production \
    HOME=/data/home \
    CODEX_HOME=/data/home/.codex \
    XDG_CACHE_HOME=/data/cache \
    XDG_CONFIG_HOME=/data/config \
    XDG_DATA_HOME=/data/share \
    TMPDIR=/data/tmp \
    CODEX_CLI_PATH=/usr/local/bin/codex

COPY --from=builder /usr/src/app /opt/codex-web

WORKDIR /workspace
EXPOSE 8214

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8214/ >/dev/null || exit 1

CMD ["tini", "--", "sh", "-c", "install -d -m 700 \"$HOME\" \"$CODEX_HOME\" && install -d -m 755 \"$XDG_CACHE_HOME\" \"$XDG_CONFIG_HOME\" \"$XDG_DATA_HOME\" \"$TMPDIR\" /workspace && exec node /opt/codex-web/src/server/main.js --host 0.0.0.0 --port 8214"]
