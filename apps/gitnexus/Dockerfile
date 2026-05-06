# ============================================
# Stage 1: Build frontend
# ============================================
# Use Debian-based image for glibc compatibility
# gitnexus CLI's kuzu native module requires glibc (not musl)
FROM node:20 AS builder

RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

# Clone and build GitNexus web UI
RUN git clone --depth 1 --branch v1.3.11 https://github.com/abhigyanpatwari/GitNexus.git /tmp/gitnexus && \
    mv /tmp/gitnexus/gitnexus-web /app

WORKDIR /app

RUN npm install
RUN npm run build

# ============================================
# Stage 2: Runtime image with gitnexus CLI + nginx
# ============================================
FROM node:20

WORKDIR /app

# Install nginx and curl
RUN apt-get update && apt-get install -y nginx curl && rm -rf /var/lib/apt/lists/*

# Install global npm packages
RUN npm install -g serve gitnexus@1.3.11

# Copy built frontend
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/public ./public
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/node_modules ./node_modules

# Copy nginx config and entrypoint
COPY docker/nginx.conf /etc/nginx/nginx.conf
COPY docker/entrypoint.sh /entrypoint.sh
COPY docker/proxy-server.mjs /proxy-server.mjs
RUN chmod +x /entrypoint.sh

# Create writable data directories for gitnexus metadata/database
RUN mkdir -p /data/gitnexus-registry && chmod -R 777 /data

# Expose nginx proxy port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8080/ || exit 1

# Start all services via entrypoint
CMD ["/entrypoint.sh"]
