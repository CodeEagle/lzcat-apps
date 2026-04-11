ARG SOURCE_VERSION=main
ARG BUILD_VERSION=0.1.0
ARG UPSTREAM_REPO=getpaseo/paseo

FROM node:22-bullseye AS builder
ARG SOURCE_VERSION
ARG UPSTREAM_REPO
WORKDIR /usr/src/app

# Install build dependencies for native modules
RUN apt-get update && apt-get install -y git python3 build-essential ca-certificates && rm -rf /var/lib/apt/lists/*

# Clone upstream inside the builder (works in CI)
RUN set -eux; \
    git clone --depth 1 --branch "${SOURCE_VERSION}" https://github.com/${UPSTREAM_REPO}.git . || \
    (git clone https://github.com/${UPSTREAM_REPO}.git . && git checkout "${SOURCE_VERSION}")

# Remove desktop workspace to avoid electron/electron-builder CI failures
RUN rm -rf packages/desktop || true
# Install workspace dependencies and build workspaces (excluding desktop)
RUN npm ci --workspaces --include-workspace-root
RUN npm run build --workspaces --if-present

# Runtime image
FROM node:22-bullseye-slim AS runner
WORKDIR /app
ENV NODE_ENV=production

# Copy built server and node_modules from builder
COPY --from=builder /usr/src/app/dist/server /app/dist/server
COPY --from=builder /usr/src/app/node_modules /app/node_modules
COPY --from=builder /usr/src/app/packages/server/package.json /app/package.json

ENV PASEO_LISTEN=0.0.0.0:6767
EXPOSE 6767
CMD ["node", "dist/server/server/index.js"]
