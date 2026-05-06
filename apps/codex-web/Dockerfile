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

server_path = Path("src/server/main.ts")
server = server_path.read_text()
server = server.replace(
    'import { randomUUID } from "node:crypto";\n',
    'import { spawn, type ChildProcess } from "node:child_process";\n'
    'import { randomUUID } from "node:crypto";\n',
)
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
    '};\n'
    '\n'
    'type DeviceAuthSession = {\n'
    '  child: ChildProcess | null;\n'
    '  code: string | null;\n'
    '  error: string | null;\n'
    '  expiresAt: number;\n'
    '  output: string;\n'
    '  startedAt: number;\n'
    '  status: "starting" | "waiting" | "complete" | "error";\n'
    '  url: string | null;\n'
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
    '}\n'
    '\n'
    'function stripAnsi(value: string): string {\n'
    '  return value.replace(/\\x1B\\[[0-?]*[ -/]*[@-~]/g, "");\n'
    '}\n',
)
server = server.replace(
    '  const uploadRoot = await fs.mkdtemp(\n'
    '    path.join(os.tmpdir(), "codex-web-uploads-"),\n'
    '  );\n',
    '  const uploadRoot = await fs.mkdtemp(\n'
    '    path.join(os.tmpdir(), "codex-web-uploads-"),\n'
    '  );\n'
    '  let deviceAuthSession: DeviceAuthSession | null = null;\n'
    '\n'
    '  function parseDeviceAuthOutput(session: DeviceAuthSession): void {\n'
    '    const cleanOutput = stripAnsi(session.output);\n'
    '    const urlMatch = cleanOutput.match(/https:\\/\\/auth\\.openai\\.com\\/codex\\/device/);\n'
    '    const codeMatch = cleanOutput.match(/\\b[A-Z0-9]{4}-[A-Z0-9]{4,6}\\b/);\n'
    '    if (urlMatch) {\n'
    '      session.url = urlMatch[0];\n'
    '    }\n'
    '    if (codeMatch) {\n'
    '      session.code = codeMatch[0];\n'
    '    }\n'
    '    if (session.url && session.code && session.status === "starting") {\n'
    '      session.status = "waiting";\n'
    '      session.expiresAt = Date.now() + 15 * 60 * 1000;\n'
    '    }\n'
    '  }\n'
    '\n'
    '  function startDeviceAuthSession(): DeviceAuthSession {\n'
    '    if (\n'
    '      deviceAuthSession &&\n'
    '      (deviceAuthSession.status === "starting" || deviceAuthSession.status === "waiting") &&\n'
    '      deviceAuthSession.expiresAt > Date.now()\n'
    '    ) {\n'
    '      return deviceAuthSession;\n'
    '    }\n'
    '\n'
    '    const child = spawn(process.env.CODEX_CLI_PATH ?? "codex", ["login", "--device-auth"], {\n'
    '      cwd: "/workspace",\n'
    '      env: process.env,\n'
    '      stdio: ["ignore", "pipe", "pipe"],\n'
    '    });\n'
    '    const session: DeviceAuthSession = {\n'
    '      child,\n'
    '      code: null,\n'
    '      error: null,\n'
    '      expiresAt: Date.now() + 15 * 60 * 1000,\n'
    '      output: "",\n'
    '      startedAt: Date.now(),\n'
    '      status: "starting",\n'
    '      url: null,\n'
    '    };\n'
    '    deviceAuthSession = session;\n'
    '\n'
    '    child.stdout?.on("data", (chunk: Buffer) => {\n'
    '      session.output += chunk.toString("utf8");\n'
    '      parseDeviceAuthOutput(session);\n'
    '    });\n'
    '    child.stderr?.on("data", (chunk: Buffer) => {\n'
    '      session.output += chunk.toString("utf8");\n'
    '      parseDeviceAuthOutput(session);\n'
    '    });\n'
    '    child.on("error", (error) => {\n'
    '      session.status = "error";\n'
    '      session.error = errorMessage(error);\n'
    '      session.child = null;\n'
    '    });\n'
    '    child.on("close", (code) => {\n'
    '      session.child = null;\n'
    '      if (code === 0) {\n'
    '        session.status = "complete";\n'
    '      } else if (session.status !== "error") {\n'
    '        session.status = "error";\n'
    '        session.error = `codex login --device-auth exited with code ${code ?? "unknown"}`;\n'
    '      }\n'
    '    });\n'
    '\n'
    '    return session;\n'
    '  }\n'
    '\n'
    '  function deviceAuthResponse(session: DeviceAuthSession): Record<string, unknown> {\n'
    '    parseDeviceAuthOutput(session);\n'
    '    return {\n'
    '      code: session.code,\n'
    '      error: session.error,\n'
    '      expiresAt: session.expiresAt,\n'
    '      status: session.status,\n'
    '      url: session.url,\n'
    '    };\n'
    '  }\n'
    '\n'
    '  function deviceAuthHtml(session: DeviceAuthSession): string {\n'
    '    const payload = JSON.stringify(deviceAuthResponse(session));\n'
    '    return `<!doctype html>\n'
    '<html lang="en">\n'
    '<head>\n'
    '  <meta charset="utf-8" />\n'
    '  <meta name="viewport" content="width=device-width, initial-scale=1" />\n'
    '  <title>Codex ChatGPT Authorization</title>\n'
    '  <style>\n'
    '    :root { color-scheme: light dark; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }\n'
    '    body { align-items: center; background: Canvas; color: CanvasText; display: flex; justify-content: center; margin: 0; min-height: 100vh; }\n'
    '    main { max-width: 560px; padding: 32px; width: min(100%, 560px); }\n'
    '    h1 { font-size: 24px; font-weight: 650; margin: 0 0 12px; }\n'
    '    p { color: color-mix(in srgb, CanvasText 72%, Canvas); line-height: 1.55; margin: 0 0 18px; }\n'
    '    a.button { align-items: center; background: CanvasText; border-radius: 8px; color: Canvas; display: inline-flex; font-weight: 650; min-height: 42px; padding: 0 16px; text-decoration: none; }\n'
    '    code { border: 1px solid color-mix(in srgb, CanvasText 16%, Canvas); border-radius: 8px; display: inline-block; font-size: 32px; font-weight: 700; letter-spacing: .06em; margin: 6px 0 20px; padding: 12px 14px; }\n'
    '    .muted { font-size: 14px; }\n'
    '    .error { color: #b42318; }\n'
    '  </style>\n'
    '</head>\n'
    '<body>\n'
    '  <main>\n'
    '    <h1>Authorize Codex with ChatGPT</h1>\n'
    '    <p id="status">Preparing device authorization...</p>\n'
    '    <p><a id="link" class="button" href="https://auth.openai.com/codex/device" target="_blank" rel="noopener noreferrer">Open ChatGPT authorization</a></p>\n'
    '    <code id="code">----</code>\n'
    '    <p class="muted" id="hint">Enter this code on the authorization page. This tab will update after Codex is authorized.</p>\n'
    '  </main>\n'
    '  <script>\n'
    '    let state = ${payload};\n'
    '    const status = document.getElementById("status");\n'
    '    const link = document.getElementById("link");\n'
    '    const code = document.getElementById("code");\n'
    '    const hint = document.getElementById("hint");\n'
    '    function render(next) {\n'
    '      state = next;\n'
    '      if (state.url) link.href = state.url;\n'
    '      code.textContent = state.code || "----";\n'
    '      if (state.status === "complete") {\n'
    '        status.textContent = "Authorization complete. Return to Codex Web and refresh the app if it has not updated automatically.";\n'
    '        hint.textContent = "Your credentials were stored in the Codex home directory for this app.";\n'
    '        return;\n'
    '      }\n'
    '      if (state.status === "error") {\n'
    '        status.textContent = state.error || "Authorization failed.";\n'
    '        status.className = "error";\n'
    '        return;\n'
    '      }\n'
    '      status.textContent = state.code ? "Use this one-time code to authorize Codex." : "Preparing device authorization...";\n'
    '      window.setTimeout(poll, 2000);\n'
    '    }\n'
    '    async function poll() {\n'
    '      try {\n'
    '        const response = await fetch("/__codex-web/device-auth/status", { cache: "no-store" });\n'
    '        render(await response.json());\n'
    '      } catch {\n'
    '        window.setTimeout(poll, 3000);\n'
    '      }\n'
    '    }\n'
    '    render(state);\n'
    '  </script>\n'
    '</body>\n'
    '</html>`;\n'
    '  }\n',
)
server = server.replace(
    '  app.post("/__backend/upload", async (request, reply) => {\n',
    '  app.get("/__codex-web/device-auth", async (_request, reply) => {\n'
    '    const session = startDeviceAuthSession();\n'
    '    return reply.type("text/html; charset=utf-8").send(deviceAuthHtml(session));\n'
    '  });\n'
    '\n'
    '  app.get("/__codex-web/device-auth/status", async (_request, reply) => {\n'
    '    const session = startDeviceAuthSession();\n'
    '    return reply.send(deviceAuthResponse(session));\n'
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
    'function usesLoopbackCallback(parsed: URL): boolean {\n'
    '  if (isLoopbackHost(parsed.hostname)) {\n'
    '    return true;\n'
    '  }\n'
    '  for (const [name, rawValue] of Array.from(parsed.searchParams.entries())) {\n'
    '    if (!isLoopbackCallbackParameter(name)) {\n'
    '      continue;\n'
    '    }\n'
    '    try {\n'
    '      const callbackUrl = new URL(rawValue);\n'
    '      if ((callbackUrl.protocol === "http:" || callbackUrl.protocol === "https:") && isLoopbackHost(callbackUrl.hostname)) {\n'
    '        return true;\n'
    '      }\n'
    '    } catch {\n'
    '      continue;\n'
    '    }\n'
    '  }\n'
    '  return false;\n'
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
    '  if (usesLoopbackCallback(parsed)) {\n'
    '    return new URL("/__codex-web/device-auth", window.location.origin).href;\n'
    '  }\n'
    '  return parsed.href;\n'
    '}\n'
    '\n'
    'function deviceAuthUrlForLoopbackAuth(value: unknown): string | null {\n'
    '  if (typeof value !== "string") {\n'
    '    return null;\n'
    '  }\n'
    '  let parsed: URL;\n'
    '  try {\n'
    '    parsed = new URL(value, window.location.href);\n'
    '  } catch {\n'
    '    return null;\n'
    '  }\n'
    '  if ((parsed.protocol === "http:" || parsed.protocol === "https:") && usesLoopbackCallback(parsed)) {\n'
    '    return new URL("/__codex-web/device-auth", window.location.origin).href;\n'
    '  }\n'
    '  return null;\n'
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
    '    const deviceAuthHref = deviceAuthUrlForLoopbackAuth(href);\n'
    '    if (!deviceAuthHref) {\n'
    '      return;\n'
    '    }\n'
    '    event.preventDefault();\n'
    '    event.stopImmediatePropagation();\n'
    '    openExternalUrl(deviceAuthHref);\n'
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
