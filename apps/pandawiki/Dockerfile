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

mq_go = Path("/src/backend/mq/mq.go")
mq_go.write_text(
    """package mq

import (
\t"context"
\t"fmt"
\t"os"

\t"github.com/google/wire"

\t"github.com/chaitin/panda-wiki/config"
\t"github.com/chaitin/panda-wiki/log"
\t"github.com/chaitin/panda-wiki/mq/nats"
\t"github.com/chaitin/panda-wiki/mq/types"
)

// Message represents a generic message that can be from either Kafka or NATS
type Message interface {
\tGetData() []byte
\tGetTopic() string
}

type MQConsumer interface {
\tStartConsumerHandlers(ctx context.Context) error
\tRegisterHandler(topic string, handler func(ctx context.Context, msg types.Message) error) error
\tClose() error
}

type MQProducer interface {
\tProduce(ctx context.Context, topic string, key string, value []byte) error
}

type noopConsumer struct{}

func (noopConsumer) StartConsumerHandlers(context.Context) error { return nil }
func (noopConsumer) RegisterHandler(string, func(context.Context, types.Message) error) error { return nil }
func (noopConsumer) Close() error { return nil }

type noopProducer struct{}

func (noopProducer) Produce(context.Context, string, string, []byte) error { return nil }

func mqDisabled() bool {
\treturn os.Getenv("PANDAWIKI_DISABLE_MQ") == "true"
}

func NewMQConsumer(config *config.Config, logger *log.Logger) (MQConsumer, error) {
\tif mqDisabled() {
\t\tlogger.Warn("mq disabled, using noop consumer")
\t\treturn noopConsumer{}, nil
\t}
\tif config.MQ.Type == "nats" {
\t\treturn nats.NewMQConsumer(logger, config)
\t}
\treturn nil, fmt.Errorf("invalid mq type: %s", config.MQ.Type)
}

func NewMQProducer(config *config.Config, logger *log.Logger) (MQProducer, error) {
\tif mqDisabled() {
\t\tlogger.Warn("mq disabled, using noop producer")
\t\treturn noopProducer{}, nil
\t}
\tif config.MQ.Type == "nats" {
\t\treturn nats.NewMQProducer(config, logger)
\t}
\treturn nil, fmt.Errorf("invalid mq type: %s", config.MQ.Type)
}

var ProviderSet = wire.NewSet(NewMQConsumer, NewMQProducer)
""",
    encoding="utf-8",
)

rag_go = Path("/src/backend/store/rag/rag.go")
rag_go.write_text(
    """package rag

import (
\t"context"
\t"fmt"
\t"os"
\t"time"

\t"github.com/cloudwego/eino/schema"
\t"github.com/google/wire"

\t"github.com/chaitin/panda-wiki/config"
\t"github.com/chaitin/panda-wiki/domain"
\t"github.com/chaitin/panda-wiki/log"
)

type QueryRecordsRequest struct {
\tDatasetID           string
\tQuery               string
\tGroupIDs            []int
\tTags                []string
\tSimilarityThreshold float64
\tHistoryMsgs         []*schema.Message
\tMaxChunksPerDoc     int
}

type UpsertRecordsRequest struct {
\tID        string
\tDatasetID string
\tDocID     string
\tTitle     string
\tContent   string
\tGroupIDs  []int
\tTags      []string
}

type DocumentMetadata struct {
\tGroupIDs []int `json:"group_ids"`
}

type Document struct {
\tID          string           `json:"id"`
\tName        string           `json:"name"`
\tDatasetID   string           `json:"dataset_id"`
\tStatus      string           `json:"status"`
\tProgressMsg string           `json:"progress_msg"`
\tMetaData    DocumentMetadata `json:"meta_data"`
\tTags        []string         `json:"tags"`
}

type RAGService interface {
\tCreateKnowledgeBase(ctx context.Context) (string, error)
\tUpsertRecords(ctx context.Context, req *UpsertRecordsRequest) (string, error)
\tQueryRecords(ctx context.Context, req *QueryRecordsRequest) (string, []*domain.NodeContentChunk, error)
\tDeleteRecords(ctx context.Context, datasetID string, docIDs []string) error
\tDeleteKnowledgeBase(ctx context.Context, datasetID string) error
\tUpdateDocumentGroupIDs(ctx context.Context, datasetID string, docID string, groupIds []int) error
\tListDocuments(ctx context.Context, datasetID string, documentIDs []string) ([]Document, error)

\tGetModelList(ctx context.Context) ([]*domain.Model, error)
\tAddModel(ctx context.Context, model *domain.Model) (string, error)
\tUpdateModel(ctx context.Context, model *domain.Model) error
\tUpsertModel(ctx context.Context, model *domain.Model) error
\tDeleteModel(ctx context.Context, model *domain.Model) error
}

type noopRAGService struct {
\tlogger *log.Logger
}

func (s *noopRAGService) CreateKnowledgeBase(context.Context) (string, error) {
\treturn fmt.Sprintf("disabled-%d", time.Now().UnixNano()), nil
}

func (s *noopRAGService) UpsertRecords(_ context.Context, req *UpsertRecordsRequest) (string, error) {
\tif req.DocID != "" {
\t\treturn req.DocID, nil
\t}
\tif req.ID != "" {
\t\treturn req.ID, nil
\t}
\treturn fmt.Sprintf("disabled-doc-%d", time.Now().UnixNano()), nil
}

func (s *noopRAGService) QueryRecords(_ context.Context, req *QueryRecordsRequest) (string, []*domain.NodeContentChunk, error) {
\treturn req.Query, []*domain.NodeContentChunk{}, nil
}

func (s *noopRAGService) DeleteRecords(context.Context, string, []string) error { return nil }
func (s *noopRAGService) DeleteKnowledgeBase(context.Context, string) error { return nil }
func (s *noopRAGService) UpdateDocumentGroupIDs(context.Context, string, string, []int) error { return nil }
func (s *noopRAGService) ListDocuments(context.Context, string, []string) ([]Document, error) {
\treturn []Document{}, nil
}
func (s *noopRAGService) GetModelList(context.Context) ([]*domain.Model, error) {
\treturn []*domain.Model{}, nil
}
func (s *noopRAGService) AddModel(_ context.Context, model *domain.Model) (string, error) {
\tif model.ID != "" {
\t\treturn model.ID, nil
\t}
\treturn fmt.Sprintf("disabled-model-%d", time.Now().UnixNano()), nil
}
func (s *noopRAGService) UpdateModel(context.Context, *domain.Model) error { return nil }
func (s *noopRAGService) UpsertModel(context.Context, *domain.Model) error { return nil }
func (s *noopRAGService) DeleteModel(context.Context, *domain.Model) error { return nil }

func ragDisabled() bool {
\treturn os.Getenv("PANDAWIKI_DISABLE_RAG") == "true"
}

func NewRAGService(config *config.Config, logger *log.Logger) (RAGService, error) {
\tif ragDisabled() {
\t\tlogger.Warn("rag disabled, using noop service")
\t\treturn &noopRAGService{logger: logger.WithModule("store.vector.noop")}, nil
\t}
\tswitch config.RAG.Provider {
\tcase "ct":
\t\treturn NewCTRAG(config, logger)
\tdefault:
\t\treturn nil, fmt.Errorf("unsupported vector provider: %s", config.RAG.Provider)
\t}
}

var ProviderSet = wire.NewSet(NewRAGService)
""",
    encoding="utf-8",
)

text = kb_repo_go.read_text(encoding="utf-8")
text = text.replace(
    'import (\n\t"bytes"\n\t"context"\n\t"encoding/json"\n\t"errors"\n\t"fmt"\n\t"io"\n\t"maps"\n\t"net"\n\t"net/http"\n\t"time"\n',
    'import (\n\t"bytes"\n\t"context"\n\t"encoding/json"\n\t"errors"\n\t"fmt"\n\t"io"\n\t"maps"\n\t"net"\n\t"net/http"\n\t"os"\n\t"time"\n',
)
text = text.replace(
    "func (r *KnowledgeBaseRepository) SyncKBAccessSettingsToCaddy(ctx context.Context, kbList []*domain.KnowledgeBaseListItem) error {\n\tif len(kbList) == 0 {\n\t\treturn nil\n\t}\n",
    "func (r *KnowledgeBaseRepository) SyncKBAccessSettingsToCaddy(ctx context.Context, kbList []*domain.KnowledgeBaseListItem) error {\n\tif os.Getenv(\"PANDAWIKI_DISABLE_CADDY\") == \"true\" {\n\t\tr.logger.Warn(\"caddy disabled, skip sync\")\n\t\treturn nil\n\t}\n\tif len(kbList) == 0 {\n\t\treturn nil\n\t}\n",
)
kb_repo_go.write_text(text, encoding="utf-8")
PY

WORKDIR /src/backend
ENV CGO_ENABLED=0
ENV GOPROXY=https://proxy.golang.org,direct
ENV GOSUMDB=sum.golang.org

RUN --mount=type=cache,target=/go/pkg/mod \
    /bin/sh -c 'i=0; until [ "$i" -ge 5 ]; do go mod download && exit 0; i=$((i+1)); echo "go mod download failed, retry $i/5" >&2; sleep 5; done; exit 1'

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
