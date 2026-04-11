ARG SOURCE_VERSION=main
ARG BUILD_VERSION=0.1.0
ARG UPSTREAM_REPO=getpaseo/paseo

FROM node:20-bullseye AS builder
ARG SOURCE_VERSION
ARG UPSTREAM_REPO
WORKDIR /usr/src/app

# Install build dependencies for native modules
RUN apt-get update && apt-get install -y git python3 build-essential ca-certificates && rm -rf /var/lib/apt/lists/*

# Prefer using an upstream copy included in build context at ./upstream; fallback to cloning remote
COPY upstream /usr/src/app/upstream
RUN if [ -d /usr/src/app/upstream ] && [ "$(ls -A /usr/src/app/upstream | wc -l)" -gt 0 ]; then \
      echo "Using upstream from build context"; \
      cp -a /usr/src/app/upstream/. /usr/src/app; \
    else \
      git clone https://github.com/${UPSTREAM_REPO}.git . && \
      git checkout "${SOURCE_VERSION}"; \
    fi

# Install workspace dependencies and build server
RUN npm ci --workspaces --include-workspace-root
RUN npm run build --workspace=@getpaseo/server

# Runtime image
FROM node:20-bullseye-slim AS runner
WORKDIR /app
ENV NODE_ENV=production

# Copy built server and node_modules from builder
COPY --from=builder /usr/src/app/dist/server /app/dist/server
COPY --from=builder /usr/src/app/node_modules /app/node_modules
COPY --from=builder /usr/src/app/packages/server/package.json /app/package.json

ENV PASEO_LISTEN=0.0.0.0:6767
EXPOSE 6767
CMD ["node", "dist/server/server/index.js"]
