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
        procps \
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

# ---- developer toolchains (rust + go + bun) ---------------------------------
# Pre-bake the common compiled-language toolchains so claude planner /
# codex repair can `cargo check`, `go build -n`, `bun install --dry-run`,
# etc. directly on the runner before writing a Dockerfile.template.
# Without these, the canonical build container (FROM rust:1-slim /
# golang:1.22-alpine / etc.) is the only place these tools exist —
# fine for the actual build, but locks the AI repair worker out of
# any quick local validation.
#
# Total bloat: ~800 MB. Acceptable for a pre-built shared runner.
#
#   rust    — rustup w/ stable toolchain (cargo, rustc)
#   go 1.22 — official release tarball
#   bun     — JS runtime/package manager (used by oven/bun:1
#             style upstream Dockerfiles, e.g. heym)
#
# (openjdk-17 was attempted but python:3.12-slim's apt repo doesn't
# carry it; Java migrations are rare enough we install on-demand
# via apt at cycle time when actually needed.)
ENV RUSTUP_HOME=/usr/local/rustup \
    CARGO_HOME=/usr/local/cargo \
    PATH=/usr/local/cargo/bin:/usr/local/go/bin:/root/.bun/bin:${PATH}

RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
        | sh -s -- -y --default-toolchain stable --profile minimal --no-modify-path \
    && cargo --version && rustc --version

ARG GO_VERSION=1.22.7
RUN ARCH="$(dpkg --print-architecture)" \
    && case "$ARCH" in \
         amd64) GO_ARCH=amd64 ;; \
         arm64) GO_ARCH=arm64 ;; \
         *) echo "unsupported arch: $ARCH" >&2; exit 1 ;; \
       esac \
    && curl -fsSL "https://go.dev/dl/go${GO_VERSION}.linux-${GO_ARCH}.tar.gz" \
        | tar -C /usr/local -xz \
    && go version

RUN curl -fsSL https://bun.sh/install | bash \
    && bun --version

# ---- runtime config ---------------------------------------------------------
WORKDIR /repo
ENV LZCAT_RUNNER=1

ENTRYPOINT ["/bin/bash"]
