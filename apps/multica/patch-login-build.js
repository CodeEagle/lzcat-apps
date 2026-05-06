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
const googleIconBlock = `                <svg className="mr-2 h-4 w-4" viewBox="0 0 24 24">
                  <path
                    d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"
                    fill="#4285F4"
                  />
                  <path
                    d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                    fill="#34A853"
                  />
                  <path
                    d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
                    fill="#FBBC05"
                  />
                  <path
                    d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                    fill="#EA4335"
                  />
                </svg>
`;

if (!lazyCatLoginSource.includes(lazyCatLabelBefore) || !lazyCatLoginSource.includes(googleIconBlock)) {
  throw new Error("expected Google login label not found");
}

fs.writeFileSync(
  loginPath,
  lazyCatLoginSource
    .replace(googleIconBlock, "")
    .replace(lazyCatLabelBefore, lazyCatLabelAfter),
);
console.log("Patched login OAuth button label and removed Google icon for LazyCat OIDC");

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
