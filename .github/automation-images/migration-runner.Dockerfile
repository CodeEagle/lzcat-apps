# lzcat-migration-runner
# Universal worker image for the auto-migration pipeline.
# Published to: ghcr.io/codeeagle/lzcat-migration-runner:{latest,sha-<short>}
#
# Contains:
#   - python 3.12 + repo's scripts/ requirements
#   - docker / podman / buildah / skopeo (container engine bridge)
#   - lzc-cli (LazyCat CLI)
#   - gh (GitHub CLI for Project + repo mutations)
#   - node 20 + npm (for migration scripts that need it)
#   - claude-code CLI (LLM repair via codex_migration_worker)
#
# Multi-arch: amd64 + arm64

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    PATH="/root/.local/bin:/usr/local/bin:${PATH}"

ARG NODE_VERSION=20
ARG LZC_CLI_VERSION=latest

# ---- core toolchain ---------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl wget git jq xz-utils unzip \
        build-essential pkg-config gnupg lsb-release \
        docker.io podman buildah skopeo fuse-overlayfs \
        openssh-client rsync \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# ---- gh CLI -----------------------------------------------------------------
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
        | gpg --dearmor -o /usr/share/keyrings/githubcli.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli.gpg] https://cli.github.com/packages stable main" \
        > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update && apt-get install -y gh \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# ---- node + npm + claude-code ----------------------------------------------
RUN curl -fsSL https://deb.nodesource.com/setup_${NODE_VERSION}.x | bash - \
    && apt-get install -y nodejs \
    && apt-get clean && rm -rf /var/lib/apt/lists/* \
    && npm install -g @anthropic-ai/claude-code \
    && npm cache clean --force

# ---- lzc-cli ----------------------------------------------------------------
# Per LazyCat docs; pin via LZC_CLI_VERSION when reproducibility matters.
RUN curl -fsSL https://lazycat.cloud/install/lzc-cli.sh | bash \
    && lzc-cli --version

# ---- python deps ------------------------------------------------------------
# Two pip-install layers so lockfile changes don't bust the toolchain cache.
COPY scripts/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# ---- runtime config ---------------------------------------------------------
WORKDIR /repo
ENV LZCAT_RUNNER=1

ENTRYPOINT ["/bin/bash"]
