FROM node:24-trixie AS build-stage

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl build-essential python3 python3-setuptools \
    && rm -rf /var/lib/apt/lists/*

RUN corepack enable

COPY . .

RUN --mount=type=cache,id=pnpm-store,target=/root/.pnpm-store \
    pnpm install --frozen-lockfile

RUN pnpm -F @proj-airi/stage-web run build \
    && pnpm -F @proj-airi/docs run build:base \
    && mv ./docs/.vitepress/dist ./apps/stage-web/dist/docs \
    && pnpm -F @proj-airi/stage-ui run story:build \
    && mv ./packages/stage-ui/.histoire/dist ./apps/stage-web/dist/ui \
    && pnpm -F @proj-airi/server-schema run build

FROM node:24-trixie-slim AS runtime

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends nginx curl ca-certificates dumb-init \
    && rm -rf /var/lib/apt/lists/* \
    && corepack enable \
    && mkdir -p /var/log/airi /run/nginx

COPY --from=build-stage /app /app
COPY lazycat/nginx.default.conf /etc/nginx/sites-enabled/default
COPY lazycat/start-airi.sh /usr/local/bin/start-airi.sh

RUN chmod +x /usr/local/bin/start-airi.sh

EXPOSE 8080

ENTRYPOINT ["dumb-init", "--"]
CMD ["/usr/local/bin/start-airi.sh"]
