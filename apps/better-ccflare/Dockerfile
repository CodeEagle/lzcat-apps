FROM oven/bun:1 AS builder

ARG BUILD_VERSION

WORKDIR /src

ADD https://github.com/tombii/better-ccflare/archive/refs/tags/v${BUILD_VERSION}.tar.gz /tmp/source.tar.gz

RUN test -n "$BUILD_VERSION" && \
    mkdir -p /src && \
    tar -xzf /tmp/source.tar.gz --strip-components=1 -C /src && \
    rm -f /tmp/source.tar.gz

RUN bun install --frozen-lockfile
RUN bun run build

FROM oven/bun:1

LABEL org.opencontainers.image.source="https://github.com/CodeEagle/lzcat-apps" \
      org.opencontainers.image.title="better-ccflare" \
      org.opencontainers.image.description="Claude API proxy with dashboard, request analytics, and account load balancing"

COPY --from=builder /src/apps/cli/dist/better-ccflare /usr/local/bin/better-ccflare

RUN mkdir -p /data /data/logs && \
    chown -R bun:bun /data /home/bun

ENV HOME=/home/bun \
    NODE_ENV=production \
    PORT=8080 \
    BETTER_CCFLARE_HOST=0.0.0.0 \
    BETTER_CCFLARE_DB_PATH=/data/better-ccflare.db \
    BETTER_CCFLARE_CONFIG_PATH=/data/better-ccflare.json \
    BETTER_CCFLARE_LOG_DIR=/data/logs

USER bun

WORKDIR /home/bun
EXPOSE 8080
VOLUME ["/data"]

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD ["bun", "-e", "fetch('http://127.0.0.1:8080/health').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"]

ENTRYPOINT ["/usr/local/bin/better-ccflare"]
CMD ["--serve", "--port", "8080"]
