import fs from "node:fs";

const sourceRoot = process.env.MULTICA_SOURCE_ROOT || "/app";
const loginPath = `${sourceRoot}/packages/views/auth/login-page.tsx`;
const loginSource = fs.readFileSync(loginPath, "utf8");

const loginBefore = `onClick={() => {
                setStep("email");
                setCode("");
                setError("");
              }}`;

const loginAfter = `onClick={() => {
                window.location.href = "/";
              }}`;

if (!loginSource.includes(loginBefore)) {
  throw new Error("expected login Back button handler not found");
}

fs.writeFileSync(loginPath, loginSource.replace(loginBefore, loginAfter));
console.log("Patched login Back button to return to home");

const coreProviderPath = `${sourceRoot}/packages/core/platform/core-provider.tsx`;
const coreProviderSource = fs.readFileSync(coreProviderPath, "utf8");

const wsParamBefore = `  apiBaseUrl = "",
  wsUrl = "ws://localhost:8080/ws",`;

const wsParamAfter = `  apiBaseUrl = "",
  wsUrl,`;

const wsProviderBefore = `        <WSProvider
          wsUrl={wsUrl}`;

const wsProviderAfter = `        <WSProvider
          wsUrl={wsUrl || (typeof window !== "undefined" ? \`\${window.location.protocol === "https:" ? "wss" : "ws"}://\${window.location.host}/ws/\` : "ws://localhost:8080/ws")}`;

if (!coreProviderSource.includes(wsParamBefore) || !coreProviderSource.includes(wsProviderBefore)) {
  throw new Error("expected CoreProvider WebSocket defaults not found");
}

fs.writeFileSync(
  coreProviderPath,
  coreProviderSource
    .replace(wsParamBefore, wsParamAfter)
    .replace(wsProviderBefore, wsProviderAfter),
);
console.log("Patched CoreProvider WebSocket URL to use current LazyCat origin");

const webProvidersPath = `${sourceRoot}/apps/web/components/web-providers.tsx`;
const webProvidersSource = fs.readFileSync(webProvidersPath, "utf8");

const webProvidersBefore = "`${proto}//${window.location.host}/ws`";
const webProvidersAfter = "`${proto}//${window.location.host}/ws/`";

if (!webProvidersSource.includes(webProvidersBefore)) {
  throw new Error("expected WebProviders derived WebSocket URL not found");
}

fs.writeFileSync(webProvidersPath, webProvidersSource.replace(webProvidersBefore, webProvidersAfter));
console.log("Patched WebProviders WebSocket URL to use /ws/ for LazyCat prefix routing");
