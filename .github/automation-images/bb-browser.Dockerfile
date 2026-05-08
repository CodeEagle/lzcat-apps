# lzcat-bb-browser
# UI verification image: bb-browser (npm) + Playwright base + ffmpeg.
# Published to: ghcr.io/codeeagle/lzcat-bb-browser:{latest,sha-<short>}
#
# bb-browser (https://github.com/epiral/bb-browser, npm: bb-browser)
# is an AI-agent-driven Chrome controller (CLI + MCP server). The image
# bundles it on top of the Microsoft Playwright base, which already
# ships node + chromium + webkit + firefox so we don't have to repeat
# the browser stack.
#
# Used by auto-verify.yml against the box's public *.lazycat.cloud URL:
#   - capture desktop + mobile screenshots (lzc-manifest declared sizes)
#   - run functional smoke (web_probe.py / functional_checker.py)
#   - drive playground walkthrough as an MCP-controlled agent
#
# Multi-arch: amd64 + arm64

FROM mcr.microsoft.com/playwright:v1.50.0-jammy

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Pin via BB_BROWSER_VERSION at build time (e.g. 0.11.3).
ARG BB_BROWSER_VERSION=latest

# ---- system tooling ---------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl wget jq xz-utils gnupg lsb-release \
        ffmpeg \
        python3 python3-pip python3-venv \
        git \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# ---- gh CLI -----------------------------------------------------------------
# auto-verify.yml's "Map check + AI verdict -> Project Status" step shells
# out to project_board.py update, which calls `gh graphql ...` to mutate
# the Project board. Without gh on PATH the step crashes with
# FileNotFoundError ('gh' missing) — observed in stellaclaw run
# 25530143338 even after the bootstrap step was added in f109c1f.
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
        | gpg --dearmor -o /usr/share/keyrings/githubcli.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli.gpg] https://cli.github.com/packages stable main" \
        > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update && apt-get install -y gh \
    && apt-get clean && rm -rf /var/lib/apt/lists/* \
    && gh --version

# ---- bb-browser (npm) -------------------------------------------------------
# Provides binaries: bb-browser, bb-browser-mcp, bb-browser-provider.
RUN BB_PKG="bb-browser$([ "${BB_BROWSER_VERSION}" = "latest" ] || echo @${BB_BROWSER_VERSION})" \
    && npm install -g "${BB_PKG}" \
    && npm cache clean --force \
    && bb-browser --version \
    && command -v bb-browser-mcp >/dev/null

# ---- python deps ------------------------------------------------------------
COPY scripts/requirements-browser.txt /tmp/requirements-browser.txt
RUN pip install --no-cache-dir -r /tmp/requirements-browser.txt

WORKDIR /repo
ENV LZCAT_BROWSER=1

ENTRYPOINT ["/bin/bash"]
