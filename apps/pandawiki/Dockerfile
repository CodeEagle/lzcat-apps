FROM --platform=$BUILDPLATFORM golang:1.24.3-alpine AS builder

ARG SOURCE_VERSION=v3.81.0
ARG BUILD_VERSION=3.81.0
ARG TARGETOS
ARG TARGETARCH

RUN apk add --no-cache ca-certificates curl python3 tzdata

WORKDIR /src

RUN curl -fsSL "https://codeload.github.com/chaitin/PandaWiki/tar.gz/${SOURCE_VERSION}" \
    | tar -xz --strip-components=1 -C /src

RUN python3 - <<'PY'
from pathlib import Path

config_go = Path("/src/backend/config/config.go")
text = config_go.read_text(encoding="utf-8")
text = text.replace(
    'Server:   fmt.Sprintf("nats://%s.13:4222", SUBNET_PREFIX),',
    'Server:   "nats://panda-wiki-nats:4222",',
)
text = text.replace(
    'BaseURL: fmt.Sprintf("http://%s.18:5050", SUBNET_PREFIX),',
    'BaseURL: "http://panda-wiki-raglite:5050",',
)
config_go.write_text(text, encoding="utf-8")

kb_repo_go = Path("/src/backend/repo/pg/knowledge_base.go")
text = kb_repo_go.read_text(encoding="utf-8")
text = text.replace(
    'subnetPrefix := r.config.SubnetPrefix\n\tif subnetPrefix == "" {\n\t\tsubnetPrefix = "169.254.15"\n\t}\n\tapi := fmt.Sprintf("%s.2:8000", subnetPrefix)\n\tapp := fmt.Sprintf("%s.112:3010", subnetPrefix)\n\tstaticFile := fmt.Sprintf("%s.12:9000", subnetPrefix) // minio',
    'api := "panda-wiki-api:8000"\n\tapp := "panda-wiki-app:3010"\n\tstaticFile := "panda-wiki-minio:9000" // minio',
)
kb_repo_go.write_text(text, encoding="utf-8")
PY

WORKDIR /src/backend
ENV CGO_ENABLED=0

RUN --mount=type=cache,target=/go/pkg/mod \
    go mod download

RUN --mount=type=cache,target=/root/.cache/go-build \
    --mount=type=cache,target=/go/pkg/mod \
    --mount=type=cache,target=/tmp \
    /bin/sh -c 'GOOS=${TARGETOS:-linux} GOARCH=${TARGETARCH:-amd64} go build -ldflags "-s -w -extldflags '\''-static'\'' -X github.com/chaitin/panda-wiki/telemetry.Version=${BUILD_VERSION}" -o /build/panda-wiki-api cmd/api/main.go cmd/api/wire_gen.go && \
    GOOS=${TARGETOS:-linux} GOARCH=${TARGETARCH:-amd64} go build -ldflags "-s -w -extldflags '\''-static'\'' -X github.com/chaitin/panda-wiki/telemetry.Version=${BUILD_VERSION}" -o /build/panda-wiki-migrate cmd/migrate/main.go cmd/migrate/wire_gen.go && \
    GOOS=${TARGETOS:-linux} GOARCH=${TARGETARCH:-amd64} go build -ldflags "-s -w -extldflags '\''-static'\'' -X github.com/chaitin/panda-wiki/telemetry.Version=${BUILD_VERSION}" -o /build/panda-wiki-consumer cmd/consumer/main.go cmd/consumer/wire_gen.go'

FROM alpine:3.21

RUN apk update \
    && apk upgrade \
    && apk add --no-cache ca-certificates tzdata \
    && update-ca-certificates 2>/dev/null || true \
    && rm -rf /var/cache/apk/*

WORKDIR /app

COPY --from=builder /build/panda-wiki-api /app/panda-wiki-api
COPY --from=builder /build/panda-wiki-migrate /app/panda-wiki-migrate
COPY --from=builder /build/panda-wiki-consumer /app/panda-wiki-consumer
COPY --from=builder /src/backend/store/pg/migration /app/migration

CMD ["sh", "-c", "/app/panda-wiki-migrate && /app/panda-wiki-api"]
