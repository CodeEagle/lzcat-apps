# lzcat-bb-browser
# UI verification image: bb-browser + Playwright + ffmpeg.
# Published to: ghcr.io/codeeagle/lzcat-bb-browser:{latest,sha-<short>}
#
# Used by auto-verify.yml against the box's public *.lazycat.cloud URL:
#   - capture desktop + mobile screenshots (lzc-manifest declared sizes)
#   - run functional smoke (web_probe.py / functional_checker.py)
#   - record video of the playground walkthrough
#
# Multi-arch: amd64 + arm64

FROM mcr.microsoft.com/playwright:v1.50.0-jammy

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

ARG BB_BROWSER_VERSION=latest

# ---- system tooling ---------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl jq xz-utils \
        ffmpeg \
        python3 python3-pip python3-venv \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# ---- bb-browser (LazyCat's verification harness) ---------------------------
# NOTE: install URL is a placeholder; replace with the canonical LazyCat
# bb-browser distribution endpoint when available.
RUN mkdir -p /opt/bb-browser \
    && curl -fsSL "https://lazycat.cloud/install/bb-browser-${BB_BROWSER_VERSION}.tgz" \
        | tar -xz -C /opt/bb-browser \
    && ln -s /opt/bb-browser/bin/bb-browser /usr/local/bin/bb-browser \
    && bb-browser --version

# ---- python deps ------------------------------------------------------------
COPY scripts/requirements-browser.txt /tmp/requirements-browser.txt
RUN pip install --no-cache-dir -r /tmp/requirements-browser.txt

WORKDIR /repo
ENV LZCAT_BROWSER=1

ENTRYPOINT ["/bin/bash"]
