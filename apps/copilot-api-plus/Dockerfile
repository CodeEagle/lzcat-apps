# Use upstream image
FROM ghcr.io/codeeagle/lazycatimages:copilotApiPlus_82cecc54a2a5

# Copy custom entrypoint that injects GH_TOKEN
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Pre-create token directory and file if GH_TOKEN is provided at build time
ARG GH_TOKEN=""
RUN if [ -n "$GH_TOKEN" ]; then \
      mkdir -p /root/.local/share/copilot-api-plus && \
      echo "$GH_TOKEN" > /root/.local/share/copilot-api-plus/github_token && \
      chmod 600 /root/.local/share/copilot-api-plus/github_token; \
    fi

# Override entrypoint
ENTRYPOINT ["/entrypoint.sh"]
