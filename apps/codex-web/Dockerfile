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
    'function isLoopbackHost(hostname: string): boolean {\n'
    '  const normalized = hostname.toLowerCase();\n'
    '  return normalized === "localhost" || normalized === "127.0.0.1" || normalized === "::1" || normalized === "[::1]";\n'
    '}\n'
    '\n'
    'function getOAuthCallbackMap(): Map<string, string> {\n'
    '  const bridgeState = getIpcMainBridgeState() as IpcMainBridgeState & { oauthCallbacks?: Map<string, string> };\n'
    '  bridgeState.oauthCallbacks ??= new Map<string, string>();\n'
    '  return bridgeState.oauthCallbacks;\n'
    '}\n'
    '\n'
    'function registerOAuthCallback(url: string): void {\n'
    '  try {\n'
    '    const parsed = new URL(url);\n'
    '    const redirectUri = parsed.searchParams.get("redirect_uri");\n'
    '    const state = parsed.searchParams.get("state");\n'
    '    if (!redirectUri || !state) {\n'
    '      return;\n'
    '    }\n'
    '    const callbackUrl = new URL(redirectUri);\n'
    '    if ((callbackUrl.protocol === "http:" || callbackUrl.protocol === "https:") && isLoopbackHost(callbackUrl.hostname)) {\n'
    '      getOAuthCallbackMap().set(state, callbackUrl.href);\n'
    '    }\n'
    '  } catch {\n'
    '    return;\n'
    '  }\n'
    '}\n'
    '\n'
    'function openExternalUrl(url: string): void {\n'
    '  if (!isHttpUrl(url)) {\n'
    '    return;\n'
    '  }\n'
    '  registerOAuthCallback(url);\n'
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

server_path = Path("src/server/main.ts")
server = server_path.read_text()
server = server.replace(
    'type WorkspaceDirectoryEntries = {\n'
    '  directoryPath: string;\n'
    '  parentPath: string | null;\n'
    '  entries: WorkspaceDirectoryEntry[];\n'
    '};\n',
    'type WorkspaceDirectoryEntries = {\n'
    '  directoryPath: string;\n'
    '  parentPath: string | null;\n'
    '  entries: WorkspaceDirectoryEntry[];\n'
    '};\n',
)
server = server.replace(
    'type IpcMainBridgeState = {\n'
    '  broadcastToRenderer?: (message: MainToRendererMessage) => void;\n'
    '  handleRendererInvoke?: (channel: string, args: unknown[]) => Promise<unknown>;\n'
    '  handleRendererSend?: (channel: string, args: unknown[]) => void;\n'
    '};\n',
    'type IpcMainBridgeState = {\n'
    '  broadcastToRenderer?: (message: MainToRendererMessage) => void;\n'
    '  handleRendererInvoke?: (channel: string, args: unknown[]) => Promise<unknown>;\n'
    '  handleRendererSend?: (channel: string, args: unknown[]) => void;\n'
    '  oauthCallbacks?: Map<string, string>;\n'
    '};\n',
)
server = server.replace(
    'function errorMessage(error: unknown): string {\n'
    '  if (error instanceof Error) {\n'
    '    return error.stack ?? error.message;\n'
    '  }\n'
    '  return String(error);\n'
    '}\n',
    'function errorMessage(error: unknown): string {\n'
    '  if (error instanceof Error) {\n'
    '    return error.stack ?? error.message;\n'
    '  }\n'
    '  return String(error);\n'
    '}\n'
    '\n'
    'function escapeHtml(value: string): string {\n'
    '  return value\n'
    '    .replace(/&/g, "&amp;")\n'
    '    .replace(/</g, "&lt;")\n'
    '    .replace(/>/g, "&gt;")\n'
    '    .replace(/"/g, "&quot;")\n'
    "    .replace(/'/g, \"&#39;\");\n"
    '}\n',
)
server = server.replace(
    '  const uploadRoot = await fs.mkdtemp(\n'
    '    path.join(os.tmpdir(), "codex-web-uploads-"),\n'
    '  );\n',
    '  const uploadRoot = await fs.mkdtemp(\n'
    '    path.join(os.tmpdir(), "codex-web-uploads-"),\n'
    '  );\n'
    '  bridgeState.oauthCallbacks ??= new Map<string, string>();\n'
    '  const oauthCallbacks = bridgeState.oauthCallbacks;\n'
    '\n'
    '  function oauthCallbackHtml(title: string, message: string, isError = false): string {\n'
    '    return `<!doctype html>\n'
    '<html lang="en">\n'
    '<head>\n'
    '  <meta charset="utf-8" />\n'
    '  <meta name="viewport" content="width=device-width, initial-scale=1" />\n'
    '  <title>${escapeHtml(title)}</title>\n'
    '  <style>\n'
    '    :root { color-scheme: light dark; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }\n'
    '    body { align-items: center; background: Canvas; color: CanvasText; display: flex; justify-content: center; margin: 0; min-height: 100vh; }\n'
    '    main { max-width: 560px; padding: 32px; width: min(100%, 560px); }\n'
    '    h1 { font-size: 24px; font-weight: 650; margin: 0 0 12px; }\n'
    '    p { color: color-mix(in srgb, CanvasText 72%, Canvas); line-height: 1.55; margin: 0 0 18px; }\n'
    '    .error { color: #b42318; }\n'
    '  </style>\n'
    '</head>\n'
    '<body>\n'
    '  <main>\n'
    '    <h1 class="${isError ? "error" : ""}">${escapeHtml(title)}</h1>\n'
    '    <p>${escapeHtml(message)}</p>\n'
    '  </main>\n'
    '  <script>\n'
    '    window.opener?.postMessage({ type: "codex-web-oauth-callback" }, window.location.origin);\n'
    '  </script>\n'
    '</body>\n'
    '</html>`;\n'
    '  }\n'
    '\n'
    '  async function forwardOAuthCallback(requestUrl: string): Promise<{ ok: boolean; message: string }> {\n'
    '    const incoming = new URL(requestUrl, "http://codex-web.local");\n'
    '    const state = incoming.searchParams.get("state");\n'
    '    if (!state) {\n'
    '      return { ok: false, message: "OpenAI callback did not include OAuth state." };\n'
    '    }\n'
    '    const localCallback = oauthCallbacks.get(state);\n'
    '    if (!localCallback) {\n'
    '      return { ok: false, message: "Codex Web could not find the matching local OAuth session. Start authorization again from Codex Web." };\n'
    '    }\n'
    '    const target = new URL(localCallback);\n'
    '    for (const [name, value] of incoming.searchParams.entries()) {\n'
    '      target.searchParams.set(name, value);\n'
    '    }\n'
    '    try {\n'
    '      const response = await fetch(target, { redirect: "manual" });\n'
    '      if (response.status >= 400) {\n'
    '        return { ok: false, message: `Local Codex callback returned HTTP ${response.status}.` };\n'
    '      }\n'
    '      oauthCallbacks.delete(state);\n'
    '      return { ok: true, message: "Authorization complete. You can close this tab and return to Codex Web." };\n'
    '    } catch (error) {\n'
    '      return { ok: false, message: `Could not forward callback to Codex CLI: ${errorMessage(error)}` };\n'
    '    }\n'
    '  }\n',
)
server = server.replace(
    '  app.post("/__backend/upload", async (request, reply) => {\n',
    '  app.get("/auth/callback", async (request, reply) => {\n'
    '    const result = await forwardOAuthCallback(request.url);\n'
    '    if (!result.ok) {\n'
    '      return reply.code(502).type("text/html; charset=utf-8").send(oauthCallbackHtml("Authorization failed", result.message, true));\n'
    '    }\n'
    '    return reply.type("text/html; charset=utf-8").send(oauthCallbackHtml("Authorization complete", result.message));\n'
    '  });\n'
    '\n'
    '  app.post("/__backend/upload", async (request, reply) => {\n',
)
server_path.write_text(server)

shim_path = Path("src/browser/shim.ts")
shim = shim_path.read_text()
shim = shim.replace(
    'const RECONNECT_DELAY_MS = 1_000;\n',
    'const RECONNECT_DELAY_MS = 1_000;\n'
    'const EXTERNAL_URL_CHANNEL = "codex_web:open-external-url";\n',
)
shim = shim.replace(
    'export function emitRendererEvent(channel: string, args: unknown[]): void {\n',
    'function isLoopbackHost(hostname: string): boolean {\n'
    '  const normalized = hostname.toLowerCase();\n'
    '  return normalized === "localhost" || normalized === "127.0.0.1" || normalized === "::1" || normalized === "[::1]";\n'
    '}\n'
    '\n'
    'function isLoopbackCallbackParameter(name: string): boolean {\n'
    '  const normalized = name.toLowerCase();\n'
    '  return normalized === "redirect_uri" || normalized === "redirect_url" || normalized === "callback_uri" || normalized === "callback_url" || normalized === "callback" || normalized.endsWith("_redirect_uri") || normalized.endsWith("_redirect_url") || normalized.endsWith("_callback_uri") || normalized.endsWith("_callback_url");\n'
    '}\n'
    '\n'
    'function webCallbackUrlFor(callbackUrl: URL): string {\n'
    '  return new URL(`${callbackUrl.pathname}${callbackUrl.search}${callbackUrl.hash}`, window.location.origin).href;\n'
    '}\n'
    '\n'
    'function rewriteLoopbackCallback(parsed: URL): string | null {\n'
    '  if ((parsed.protocol === "http:" || parsed.protocol === "https:") && isLoopbackHost(parsed.hostname)) {\n'
    '    return webCallbackUrlFor(parsed);\n'
    '  }\n'
    '  let rewritten: URL | null = null;\n'
    '  for (const [name, rawValue] of Array.from(parsed.searchParams.entries())) {\n'
    '    if (!isLoopbackCallbackParameter(name)) {\n'
    '      continue;\n'
    '    }\n'
    '    try {\n'
    '      const callbackUrl = new URL(rawValue);\n'
    '      if ((callbackUrl.protocol === "http:" || callbackUrl.protocol === "https:") && isLoopbackHost(callbackUrl.hostname)) {\n'
    '        rewritten ??= new URL(parsed.href);\n'
    '        rewritten.searchParams.set(name, webCallbackUrlFor(callbackUrl));\n'
    '      }\n'
    '    } catch {\n'
    '      continue;\n'
    '    }\n'
    '  }\n'
    '  return rewritten?.href ?? null;\n'
    '}\n'
    '\n'
    'function externalUrlForWeb(value: unknown): string | null {\n'
    '  if (typeof value !== "string") {\n'
    '    return null;\n'
    '  }\n'
    '  let parsed: URL;\n'
    '  try {\n'
    '    parsed = new URL(value);\n'
    '  } catch {\n'
    '    return null;\n'
    '  }\n'
    '  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {\n'
    '    return null;\n'
    '  }\n'
    '  return rewriteLoopbackCallback(parsed) ?? parsed.href;\n'
    '}\n'
    '\n'
    'function webUrlForLoopbackAuth(value: unknown): string | null {\n'
    '  if (typeof value !== "string") {\n'
    '    return null;\n'
    '  }\n'
    '  let parsed: URL;\n'
    '  try {\n'
    '    parsed = new URL(value, window.location.href);\n'
    '  } catch {\n'
    '    return null;\n'
    '  }\n'
    '  return rewriteLoopbackCallback(parsed);\n'
    '}\n'
    '\n'
    'function openExternalUrl(value: unknown): void {\n'
    '  const href = externalUrlForWeb(value);\n'
    '  if (!href) {\n'
    '    return;\n'
    '  }\n'
    '  const opened = window.open(href, "_blank", "noopener,noreferrer");\n'
    '  if (!opened) {\n'
    '    window.location.assign(href);\n'
    '  }\n'
    '}\n'
    '\n'
    'function findAnchor(target: EventTarget | null): HTMLAnchorElement | null {\n'
    '  if (!(target instanceof Element)) {\n'
    '    return null;\n'
    '  }\n'
    '  return target.closest("a[href]") as HTMLAnchorElement | null;\n'
    '}\n'
    '\n'
    'function installExternalNavigationGuards(): void {\n'
    '  document.addEventListener("click", (event) => {\n'
    '    if (event.defaultPrevented || event.button !== 0) {\n'
    '      return;\n'
    '    }\n'
    '    const anchor = findAnchor(event.target);\n'
    '    const href = anchor?.href;\n'
    '    const webHref = webUrlForLoopbackAuth(href);\n'
    '    if (!webHref) {\n'
    '      return;\n'
    '    }\n'
    '    event.preventDefault();\n'
    '    event.stopImmediatePropagation();\n'
    '    openExternalUrl(webHref);\n'
    '  }, true);\n'
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
shim = shim.replace(
    '\nensureSocket();\n\nexport const contextBridge = {\n',
    '\ninstallExternalNavigationGuards();\n'
    'ensureSocket();\n'
    '\nexport const contextBridge = {\n',
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
