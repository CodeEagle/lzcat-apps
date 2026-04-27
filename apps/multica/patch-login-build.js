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

const lazyCatLoginSource = fs.readFileSync(loginPath, "utf8");
const lazyCatLabelBefore = "Continue with Google";
const lazyCatLabelAfter = "Continue with LazyCat";

if (!lazyCatLoginSource.includes(lazyCatLabelBefore)) {
  throw new Error("expected Google login label not found");
}

fs.writeFileSync(loginPath, lazyCatLoginSource.replace(lazyCatLabelBefore, lazyCatLabelAfter));
console.log("Patched login OAuth button label for LazyCat OIDC");

const webLoginPath = `${sourceRoot}/apps/web/app/(auth)/login/page.tsx`;
const webLoginSource = fs.readFileSync(webLoginPath, "utf8");
const lazyCatOIDCBefore = `      cliCallback={
        cliCallbackRaw && validateCliCallback(cliCallbackRaw)
          ? { url: cliCallbackRaw, state: cliState }
          : undefined
      }
      onTokenObtained={setLoggedInCookie}`;
const lazyCatOIDCAfter = `      cliCallback={
        cliCallbackRaw && validateCliCallback(cliCallbackRaw)
          ? { url: cliCallbackRaw, state: cliState }
          : undefined
      }
      onGoogleLogin={() => {
        const target = new URL("/auth/oidc/start", window.location.origin);
        if (googleState) target.searchParams.set("state", googleState);
        window.location.href = target.toString();
      }}
      onTokenObtained={setLoggedInCookie}`;

if (!webLoginSource.includes(lazyCatOIDCBefore)) {
  throw new Error("expected web login props block not found");
}

fs.writeFileSync(webLoginPath, webLoginSource.replace(lazyCatOIDCBefore, lazyCatOIDCAfter));
console.log("Patched web login page to start LazyCat OIDC");

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
