ARG SOURCE_VERSION=v0.12.0
ARG GO_VERSION=1.25.3
ARG UBUNTU_VERSION=22.04
ARG BUILDPLATFORM
ARG TARGETPLATFORM
ARG TARGETOS
ARG TARGETARCH

FROM --platform=$BUILDPLATFORM ubuntu:${UBUNTU_VERSION} AS source

ARG SOURCE_VERSION
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl tar \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src

RUN curl -fsSL "https://codeload.github.com/superplanehq/superplane/tar.gz/${SOURCE_VERSION}" \
    | tar -xz --strip-components=1 -C /src

FROM --platform=$BUILDPLATFORM ubuntu:${UBUNTU_VERSION} AS base

ARG GO_VERSION
ENV DEBIAN_FRONTEND=noninteractive
ENV GO_VERSION=${GO_VERSION}
ENV PATH="/usr/local/go/bin:/go/bin:${PATH}"
ENV GOPATH="/go"
ENV GOBIN="/go/bin"
ENV GOPROXY="https://proxy.golang.org,direct"

WORKDIR /tmp

COPY --from=source /src/scripts/docker ./scripts

RUN bash scripts/install-go.sh "${GO_VERSION}" \
    && bash scripts/install-nodejs.sh \
    && bash scripts/install-postgresql-client.sh \
    && bash scripts/install-gomigrate.sh \
    && bash scripts/install-protoc.sh

WORKDIR /app

COPY --from=source /src/pkg ./pkg
COPY --from=source /src/cmd ./cmd
COPY --from=source /src/go.mod ./go.mod
COPY --from=source /src/go.sum ./go.sum
COPY --from=source /src/db/migrations ./db/migrations
COPY --from=source /src/docker-entrypoint.sh ./docker-entrypoint.sh
COPY --from=source /src/web_src ./web_src
COPY --from=source /src/protos ./protos
COPY --from=source /src/api/swagger ./api/swagger
COPY --from=source /src/rbac ./rbac
COPY --from=source /src/templates ./templates
COPY --from=source /src/release/superplane-demo-image ./release/superplane-demo-image

FROM --platform=$BUILDPLATFORM base AS builder

ARG BASE_URL=https://app.superplane.com
ARG TARGETOS
ARG TARGETARCH

WORKDIR /app

RUN rm -rf build \
    && GOOS=${TARGETOS} GOARCH=${TARGETARCH} CGO_ENABLED=0 go build -o build/superplane cmd/server/main.go

WORKDIR /app/web_src

RUN npm install \
    && VITE_BASE_URL="${BASE_URL}" npm run build

FROM --platform=$TARGETPLATFORM ubuntu:${UBUNTU_VERSION} AS runner

ENV DEBIAN_FRONTEND=noninteractive

LABEL org.opencontainers.image.title="superplane-demo" \
  org.opencontainers.image.description="SuperPlane demo image repackaged for LazyCat." \
  org.opencontainers.image.vendor="SuperPlane" \
  org.opencontainers.image.source="https://github.com/superplanehq/superplane" \
  org.opencontainers.image.url="https://superplane.com" \
  org.opencontainers.image.documentation="https://docs.superplane.com"

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        postgresql \
        postgresql-contrib \
        rabbitmq-server \
        ca-certificates \
        curl \
        openssl \
    && ln -s /usr/lib/postgresql/*/bin/* /usr/local/bin/ \
    && rm -rf /var/lib/apt/lists/*

COPY --from=base /tmp/scripts/install-nodejs.sh /tmp/install-nodejs.sh
COPY --from=base /tmp/scripts/install-postgresql-client.sh /tmp/install-postgresql-client.sh

RUN bash /tmp/install-nodejs.sh \
    && bash /tmp/install-postgresql-client.sh \
    && rm -f /tmp/install-nodejs.sh /tmp/install-postgresql-client.sh

WORKDIR /app

COPY --from=builder /usr/bin/createdb /usr/bin/createdb
COPY --from=builder /usr/bin/migrate /usr/bin/migrate
COPY --from=builder /app/build/superplane /app/build/superplane
COPY --from=builder /app/db/migrations /app/db/migrations
COPY --from=builder /app/pkg/web/assets/dist /app/pkg/web/assets/dist
COPY --from=builder /app/api/swagger /app/api/swagger
COPY --from=builder /app/rbac /app/rbac
COPY --from=builder /app/templates /app/templates
COPY --from=builder /app/release/superplane-demo-image/entrypoint.sh /app/entrypoint.sh
COPY --from=builder /app/release/superplane-demo-image/gen-superplane-env.sh /app/gen-superplane-env.sh
COPY --from=builder /app/release/superplane-demo-image/spinner.sh /app/spinner.sh

RUN chmod +x /app/entrypoint.sh /app/gen-superplane-env.sh /app/spinner.sh \
    && sed -i 's|exec /app/build/superplane >/dev/null 2>&1|exec /app/build/superplane|' /app/entrypoint.sh

EXPOSE 3000

HEALTHCHECK --interval=20s --timeout=5s --start-period=40s --retries=10 \
    CMD curl -fsS http://127.0.0.1:3000/health || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
