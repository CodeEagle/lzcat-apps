FROM node:20-bookworm AS builder

    ARG UPSTREAM_REPO=noopolis/moltnet
    ARG UPSTREAM_REF=main
    ARG SOURCE_VERSION=unknown
    ARG BUILD_VERSION=0.1.0

    RUN apt-get update \
        && apt-get install -y --no-install-recommends ca-certificates curl \
        && rm -rf /var/lib/apt/lists/*

    WORKDIR /src

    RUN curl -fsSL "https://codeload.github.com/${UPSTREAM_REPO}/tar.gz/${UPSTREAM_REF}" \
        | tar -xz --strip-components=1 -C /src

    WORKDIR /src/web

    RUN npm ci \
&& npm run build

    FROM nginx:1.27-alpine

    ARG SOURCE_VERSION=unknown
    ARG BUILD_VERSION=0.1.0

    LABEL org.opencontainers.image.version="${BUILD_VERSION}" \
          org.opencontainers.image.revision="${SOURCE_VERSION}"

    RUN rm -rf /usr/share/nginx/html/*

    COPY --from=builder /src/web/dist/ /usr/share/nginx/html/

    EXPOSE 80

    CMD ["nginx", "-g", "daemon off;"]
