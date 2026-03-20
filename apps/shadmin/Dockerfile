ARG UPSTREAM_REPO=ahaodev/shadmin
ARG UPSTREAM_REF=6ed2c203af236b598e83127e34a8553c16a5b6c5
ARG APP_VERSION=2.1.0
ARG BUILDPLATFORM
ARG TARGETPLATFORM=linux/amd64
ARG TARGETOS=linux
ARG TARGETARCH=amd64

FROM --platform=$BUILDPLATFORM node:22-bookworm AS web-builder

ARG UPSTREAM_REPO
ARG UPSTREAM_REF

RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates git && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /src

RUN git clone https://github.com/${UPSTREAM_REPO}.git . && \
    git checkout "${UPSTREAM_REF}"

WORKDIR /src/web

RUN corepack enable && \
    pnpm install --frozen-lockfile && \
    pnpm run build

FROM --platform=$BUILDPLATFORM golang:1.25-trixie AS go-builder

ARG UPSTREAM_REPO
ARG UPSTREAM_REF
ARG APP_VERSION
ARG TARGETOS
ARG TARGETARCH

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      build-essential \
      ca-certificates \
      gcc-x86-64-linux-gnu \
      libc6-dev-amd64-cross \
      git && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /src

RUN git clone https://github.com/${UPSTREAM_REPO}.git . && \
    git checkout "${UPSTREAM_REF}"

COPY --from=web-builder /src/web/dist /src/web/dist

RUN go install entgo.io/ent/cmd/ent@v0.14.5 && \
    go install github.com/swaggo/swag/cmd/swag@v1.16.6 && \
    go generate ./... && \
    CC=x86_64-linux-gnu-gcc CGO_ENABLED=1 GOOS=${TARGETOS} GOARCH=${TARGETARCH} go build \
      -ldflags="-s -w -X cmd.version=${APP_VERSION} -X cmd.commit=${UPSTREAM_REF} -X cmd.date=${UPSTREAM_REF}" \
      -o /out/shadmin .

FROM --platform=$TARGETPLATFORM debian:trixie-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates curl && \
    rm -rf /var/lib/apt/lists/*

COPY --from=go-builder /out/shadmin /app/shadmin
COPY --from=go-builder /src/.env.example /app/.env.example

RUN mkdir -p /app/.database /app/uploads /app/.logs

EXPOSE 55667

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=5 \
  CMD curl -fsS http://127.0.0.1:55667/ >/dev/null || exit 1

CMD ["./shadmin"]
