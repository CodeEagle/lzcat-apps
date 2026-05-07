# lzcat-migration-runner
# Universal worker image for the auto-migration pipeline.
# Published to: ghcr.io/codeeagle/lzcat-migration-runner:{latest,sha-<short>}
#
# Contains:
#   - python 3.12 + repo's scripts/ requirements
#   - docker / podman / buildah / skopeo (container engine bridge)
#   - node 20 + npm
#   - @lazycatcloud/lzc-cli (LazyCat CLI, installed via npm)
#   - @anthropic-ai/claude-code (Claude CLI: discovery review + repair worker)
#   - gh (GitHub CLI for Project + repo mutations)
#   - chromium browser + Playwright runtime + bb-browser (so the same
#     worker can run browser-based functional tests after build, no
#     handoff to lzcat-bb-browser image needed for simple cases)
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
# nftables: required by netavark (podman's network plugin). Without it,
# `RUN` lines in podman builds die at "setup network: netavark: nftables
# error: unable to execute nft: No such file or directory" — observed in
# every build cycle until 2026-05-07 (heym run 25485629825 reached the
# `bun install` step but failed there for this reason).
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl wget git jq xz-utils unzip \
        build-essential pkg-config gnupg lsb-release \
        docker.io podman buildah skopeo fuse-overlayfs nftables \
        openssh-client rsync \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# ---- containers/registries.conf --------------------------------------------
# Podman refuses unqualified FROM lines like `oven/bun:1` / `node:20` /
# `python:3.11` unless an unqualified-search registry is declared.
# Defaulting to docker.io matches the docker CLI's behavior so build
# strategies that mirror upstream Dockerfiles (which routinely use
# short names) work out of the box.
RUN mkdir -p /etc/containers \
    && printf 'unqualified-search-registries = ["docker.io"]\n' \
        >> /etc/containers/registries.conf

# ---- gh CLI -----------------------------------------------------------------
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
        | gpg --dearmor -o /usr/share/keyrings/githubcli.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli.gpg] https://cli.github.com/packages stable main" \
        > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update && apt-get install -y gh \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# ---- node + npm + claude-code + lzc-cli -------------------------------------
# lzc-cli is distributed as @lazycatcloud/lzc-cli on npm. Pin via
# LZC_CLI_VERSION at build time when reproducibility matters
# (e.g. LZC_CLI_VERSION=1.4.0 → npm install -g @lazycatcloud/lzc-cli@1.4.0).
RUN curl -fsSL https://deb.nodesource.com/setup_${NODE_VERSION}.x | bash - \
    && apt-get install -y nodejs \
    && apt-get clean && rm -rf /var/lib/apt/lists/* \
    && LZC_PKG="@lazycatcloud/lzc-cli$([ "${LZC_CLI_VERSION}" = "latest" ] || echo @${LZC_CLI_VERSION})" \
    && npm install -g \
         @anthropic-ai/claude-code \
         "${LZC_PKG}" \
    && npm cache clean --force \
    && lzc-cli --version \
    && claude --version

# ---- python deps ------------------------------------------------------------
# Two pip-install layers so lockfile changes don't bust the toolchain cache.
COPY scripts/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# ---- chromium + Playwright + bb-browser -------------------------------------
# Browser stack so the worker can run bb-browser-driven functional
# verification (SKILL.md rule 12 — install success ≠ acceptance) in
# the same job after build/install, instead of handing off to a
# separate lzcat-bb-browser job. Adds ~250 MB to the image.
#
# Approach: pip install playwright (already in requirements.txt as
# playwright>=1.50), then `playwright install --with-deps chromium`
# downloads the upstream-tested chromium build PLUS its system libs
# in one shot — more reliable than apt's distro chromium which lags
# Playwright's pinned version.
#
# bb-browser CLI / MCP server is the Chrome-driving agent used in
# auto-verify; install it globally via the same npm we already have.
ARG BB_BROWSER_VERSION=latest
RUN python3 -m playwright install --with-deps chromium \
    && BB_PKG="bb-browser$([ "${BB_BROWSER_VERSION}" = "latest" ] || echo @${BB_BROWSER_VERSION})" \
    && npm install -g "${BB_PKG}" \
    && npm cache clean --force \
    && bb-browser --version \
    && command -v bb-browser-mcp >/dev/null

# ---- runtime config ---------------------------------------------------------
WORKDIR /repo
ENV LZCAT_RUNNER=1

ENTRYPOINT ["/bin/bash"]
