FROM node:20-bookworm AS frontend-builder

ARG UPSTREAM_REPO=Forget-C/Jellyfish
ARG UPSTREAM_REF=main

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src

RUN curl -fsSL "https://codeload.github.com/${UPSTREAM_REPO}/tar.gz/${UPSTREAM_REF}" \
    | tar -xz --strip-components=1 -C /src

WORKDIR /src/front

ENV VITE_USE_MOCK=false

RUN corepack enable \
    && corepack prepare pnpm@8.15.8 --activate \
    && pnpm install --frozen-lockfile \
    && pnpm run openapi:gen \
    && pnpm exec vite build

FROM python:3.11-slim

ARG UPSTREAM_REPO=Forget-C/Jellyfish
ARG UPSTREAM_REF=main

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000 \
    DATABASE_URL=sqlite+aiosqlite:////data/jellyfish.db \
    LOCAL_STORAGE_DIR=/data/storage \
    JELLYFISH_DATA_DIR=/data

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl nginx \
    && rm -rf /var/lib/apt/lists/* \
    && rm -f /etc/nginx/sites-enabled/default

WORKDIR /opt/jellyfish

RUN curl -fsSL "https://codeload.github.com/${UPSTREAM_REPO}/tar.gz/${UPSTREAM_REF}" \
    | tar -xz --strip-components=1 -C /opt/jellyfish

WORKDIR /opt/jellyfish/backend

RUN python -m pip install --upgrade pip setuptools wheel \
    && python -m pip install .

COPY patches/backend/app/config.py /opt/jellyfish/backend/app/config.py
COPY patches/backend/app/main.py /opt/jellyfish/backend/app/main.py
COPY patches/backend/app/core/storage.py /opt/jellyfish/backend/app/core/storage.py
COPY patches/backend/app/utils /opt/jellyfish/backend/app/utils
COPY lazycat/nginx.conf /etc/nginx/conf.d/default.conf
COPY lazycat/entrypoint.sh /entrypoint.sh
COPY --from=frontend-builder /src/front/dist /var/www/jellyfish

RUN chmod +x /entrypoint.sh \
    && mkdir -p /data/storage /var/www/jellyfish

EXPOSE 8080

HEALTHCHECK --interval=15s --timeout=5s --start-period=40s --retries=5 \
    CMD curl -fsS http://127.0.0.1:8080/health >/dev/null || exit 1

CMD ["/entrypoint.sh"]
