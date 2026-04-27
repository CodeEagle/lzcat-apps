# syntax=docker/dockerfile:1.6

ARG SOURCE_VERSION=v1.3.2
ARG BUILD_VERSION=1.3.2
ARG UPSTREAM_REPO=chenhg5/cc-connect
ARG BUILDPLATFORM=linux/amd64
ARG TARGETPLATFORM=linux/amd64
ARG TARGETOS=linux
ARG TARGETARCH=amd64

FROM --platform=$BUILDPLATFORM node:22-bookworm AS web-builder

ARG SOURCE_VERSION
ARG UPSTREAM_REPO

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl python3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src

RUN curl -fsSL "https://codeload.github.com/${UPSTREAM_REPO}/tar.gz/${SOURCE_VERSION}" \
    | tar -xz --strip-components=1 -C /src

COPY lazycat/patch_lazycat.py /tmp/patch_lazycat.py
RUN python3 /tmp/patch_lazycat.py /src --web-only

WORKDIR /src/web
RUN npm install --no-audit --no-fund \
    && npm run build

FROM --platform=$BUILDPLATFORM golang:1.25-trixie AS go-builder

ARG SOURCE_VERSION
ARG BUILD_VERSION
ARG UPSTREAM_REPO
ARG TARGETOS
ARG TARGETARCH

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl python3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src

RUN curl -fsSL "https://codeload.github.com/${UPSTREAM_REPO}/tar.gz/${SOURCE_VERSION}" \
    | tar -xz --strip-components=1 -C /src

COPY --from=web-builder /src/web/dist /src/web/dist
COPY lazycat/patch_lazycat.py /tmp/patch_lazycat.py
RUN python3 /tmp/patch_lazycat.py /src --server-only

RUN GOCACHE=/tmp/go-build-cache \
    GOTOOLCHAIN=local CGO_ENABLED=0 GOOS=${TARGETOS} GOARCH=${TARGETARCH} \
    go build \
      -ldflags="-s -w -X main.version=${BUILD_VERSION} -X main.commit=${SOURCE_VERSION} -X main.buildTime=lazycat" \
      -o /out/cc-connect ./cmd/cc-connect

FROM --platform=$TARGETPLATFORM node:22-bookworm-slim AS runtime

ENV DEBIAN_FRONTEND=noninteractive \
    CC_CONNECT_DATA_DIR=/data \
    CC_CONNECT_CONFIG=/data/config.toml \
    HOME=/data/home \
    XDG_CONFIG_HOME=/data/home/.config \
    XDG_DATA_HOME=/data/home/.local/share \
    XDG_CACHE_HOME=/data/home/.cache \
    PATH=/data/bin:/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
      bash \
      ca-certificates \
      curl \
      git \
      openssh-client \
      python3 \
      python3-pip \
      sqlite3 \
      tini \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /data /data/home /data/state /data/workspaces /data/bin

COPY lazycat/update-agent-clis.sh /usr/local/bin/update-agent-clis.sh

# Default agent CLIs are installed into the image. Build fails if the default
# set cannot be installed, so the LPK does not ship without runnable agents.
RUN chmod +x /usr/local/bin/update-agent-clis.sh \
    && /usr/local/bin/update-agent-clis.sh --required

COPY --from=go-builder /out/cc-connect /usr/local/bin/cc-connect
COPY lazycat/entrypoint.sh /usr/local/bin/entrypoint.sh

RUN chmod +x /usr/local/bin/cc-connect /usr/local/bin/entrypoint.sh

WORKDIR /data/workspaces

EXPOSE 9820 9810 9111

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=5 \
  CMD curl -fsS http://127.0.0.1:9820/api/v1/status >/dev/null || exit 1

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/entrypoint.sh"]
