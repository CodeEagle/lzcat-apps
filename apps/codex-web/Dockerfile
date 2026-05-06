ARG SOURCE_VERSION=main
ARG UPSTREAM_REPO=0xcaff/codex-web

FROM node:22-bookworm AS builder

ARG SOURCE_VERSION
ARG UPSTREAM_REPO

WORKDIR /usr/src/app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    curl \
    git \
    patch \
    python3 \
    unzip \
    && rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    git clone --depth 1 --branch "${SOURCE_VERSION}" "https://github.com/${UPSTREAM_REPO}.git" . || \
    (git clone "https://github.com/${UPSTREAM_REPO}.git" . && git checkout "${SOURCE_VERSION}")

RUN python3 <<'PY'
from pathlib import Path

electron_path = Path("src/server/electron/index.ts")
electron = electron_path.read_text()
electron = electron.replace(
    'function log(method: string, args: unknown[]): void {\n'
    '  console.log(`[electron-main-stub] ${method}`, args);\n'
    '}\n',
    'const EXTERNAL_URL_CHANNEL = "codex_web:open-external-url";\n'
    '\n'
    'function log(method: string, args: unknown[]): void {\n'
    '  console.log(`[electron-main-stub] ${method}`, args);\n'
    '}\n'
    '\n'
    'function isHttpUrl(value: unknown): value is string {\n'
    '  if (typeof value !== "string") {\n'
    '    return false;\n'
    '  }\n'
    '  try {\n'
    '    const parsed = new URL(value);\n'
    '    return parsed.protocol === "http:" || parsed.protocol === "https:";\n'
    '  } catch {\n'
    '    return false;\n'
    '  }\n'
    '}\n'
    '\n'
    'function openExternalUrl(url: string): void {\n'
    '  if (!isHttpUrl(url)) {\n'
    '    return;\n'
    '  }\n'
    '  getIpcMainBridgeState().broadcastToRenderer?.({\n'
    '    type: "ipc-main-event",\n'
    '    channel: EXTERNAL_URL_CHANNEL,\n'
    '    args: [url],\n'
    '  });\n'
    '}\n',
)
electron = electron.replace(
    '        loadURL: async (url: string): Promise<void> => {\n'
    '          log(`BrowserWindow#${this.id}.webContents.loadURL`, [url]);\n'
    '        },\n',
    '        loadURL: async (url: string): Promise<void> => {\n'
    '          log(`BrowserWindow#${this.id}.webContents.loadURL`, [url]);\n'
    '          if (isHttpUrl(url) && !url.startsWith(rendererUrl)) {\n'
    '            openExternalUrl(url);\n'
    '          }\n'
    '        },\n',
)
electron = electron.replace(
    '  show(): void {\n'
    '    log(`BrowserWindow#${this.id}.show`, []);\n'
    '  }\n',
    '  async loadURL(url: string): Promise<void> {\n'
    '    log(`BrowserWindow#${this.id}.loadURL`, [url]);\n'
    '    if (isHttpUrl(url) && !url.startsWith(rendererUrl)) {\n'
    '      openExternalUrl(url);\n'
    '    }\n'
    '  }\n'
    '\n'
    '  show(): void {\n'
    '    log(`BrowserWindow#${this.id}.show`, []);\n'
    '  }\n',
)
electron = electron.replace(
    'const crashReporter = {\n'
    '  start(...args: unknown[]): void {\n'
    '    log("crashReporter.start", args);\n'
    '  },\n'
    '};\n',
    'const crashReporter = {\n'
    '  start(...args: unknown[]): void {\n'
    '    log("crashReporter.start", args);\n'
    '  },\n'
    '};\n'
    '\n'
    'const shellBase = {\n'
    '  async openExternal(url: string): Promise<void> {\n'
    '    log("shell.openExternal", [url]);\n'
    '    openExternalUrl(url);\n'
    '  },\n'
    '  async trashItem(path: string): Promise<void> {\n'
    '    log("shell.trashItem", [path]);\n'
    '  },\n'
    '};\n'
    '\n'
    'const shell = new Proxy(shellBase as Record<string, unknown>, {\n'
    '  get(target, prop) {\n'
    '    if (prop in target) {\n'
    '      return target[prop as keyof typeof shellBase];\n'
    '    }\n'
    '    return createDeepStub(`shell.${String(prop)}`);\n'
    '  },\n'
    '}) as typeof shellBase;\n',
)
electron = electron.replace(
    '    screen,\n'
    '    session,\n'
    '    Tray,\n',
    '    screen,\n'
    '    session,\n'
    '    shell,\n'
    '    Tray,\n',
)
electron = electron.replace(
    '  screen,\n'
    '  session,\n'
    '  Tray,\n',
    '  screen,\n'
    '  session,\n'
    '  shell,\n'
    '  Tray,\n',
)
electron_path.write_text(electron)

shim_path = Path("src/browser/shim.ts")
shim = shim_path.read_text()
shim = shim.replace(
    'const RECONNECT_DELAY_MS = 1_000;\n',
    'const RECONNECT_DELAY_MS = 1_000;\n'
    'const EXTERNAL_URL_CHANNEL = "codex_web:open-external-url";\n',
)
shim = shim.replace(
    'export function emitRendererEvent(channel: string, args: unknown[]): void {\n',
    'function openExternalUrl(value: unknown): void {\n'
    '  if (typeof value !== "string") {\n'
    '    return;\n'
    '  }\n'
    '  let parsed: URL;\n'
    '  try {\n'
    '    parsed = new URL(value);\n'
    '  } catch {\n'
    '    return;\n'
    '  }\n'
    '  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {\n'
    '    return;\n'
    '  }\n'
    '  const opened = window.open(parsed.href, "_blank", "noopener,noreferrer");\n'
    '  if (!opened) {\n'
    '    window.location.assign(parsed.href);\n'
    '  }\n'
    '}\n'
    '\n'
    'export function emitRendererEvent(channel: string, args: unknown[]): void {\n',
)
shim = shim.replace(
    '  if (message.type === "ipc-main-event") {\n'
    '    emitRendererEvent(message.channel, message.args);\n'
    '    return;\n'
    '  }\n',
    '  if (message.type === "ipc-main-event") {\n'
    '    if (message.channel === EXTERNAL_URL_CHANNEL) {\n'
    '      openExternalUrl(message.args[0]);\n'
    '      return;\n'
    '    }\n'
    '    emitRendererEvent(message.channel, message.args);\n'
    '    return;\n'
    '  }\n',
)
shim_path.write_text(shim)
PY

RUN npm ci --no-audit --no-fund
RUN npm prune --omit=dev --ignore-scripts --no-audit --no-fund

FROM node:22-bookworm-slim AS runner

ARG CODEX_CLI_VERSION=0.126.0-alpha.15

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    ca-certificates \
    curl \
    git \
    openssh-client \
    tini \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g --omit=dev --no-audit --no-fund "@openai/codex@${CODEX_CLI_VERSION}"

ENV NODE_ENV=production \
    HOME=/data/home \
    CODEX_HOME=/data/home/.codex \
    XDG_CACHE_HOME=/data/cache \
    XDG_CONFIG_HOME=/data/config \
    XDG_DATA_HOME=/data/share \
    TMPDIR=/data/tmp \
    CODEX_CLI_PATH=/usr/local/bin/codex

COPY --from=builder /usr/src/app /opt/codex-web

WORKDIR /workspace
EXPOSE 8214

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8214/ >/dev/null || exit 1

CMD ["tini", "--", "sh", "-c", "install -d -m 700 \"$HOME\" \"$CODEX_HOME\" && install -d -m 755 \"$XDG_CACHE_HOME\" \"$XDG_CONFIG_HOME\" \"$XDG_DATA_HOME\" \"$TMPDIR\" /workspace && exec node /opt/codex-web/src/server/main.js --host 0.0.0.0 --port 8214"]
