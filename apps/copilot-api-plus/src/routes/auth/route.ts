import consola from "consola"
import { Hono } from "hono"

import { state } from "~/lib/state"
import {
  readGithubToken,
  setupCopilotToken,
  writeGithubToken,
} from "~/lib/token"
import { cacheModels } from "~/lib/utils"
import { getDeviceCode } from "~/services/github/get-device-code"
import { getGitHubUser } from "~/services/github/get-user"
import { pollAccessToken } from "~/services/github/poll-access-token"

export const authRoutes = new Hono()

interface PendingAuth {
  user_code: string
  verification_uri: string
  device_code: string
  interval: number
  expires_in: number
}

let pendingAuth: PendingAuth | null = null
let authPolling = false
let authLastError: string | null = null

// GET /auth/status
authRoutes.get("/status", async (c) => {
  if (state.githubToken) {
    try {
      const user = await getGitHubUser()
      return c.json({ authenticated: true, login: user.login })
    } catch {
      // token present but may be invalid
    }
  }
  return c.json({
    authenticated: false,
    pending: authPolling,
    user_code: pendingAuth?.user_code ?? null,
    verification_uri: pendingAuth?.verification_uri ?? null,
    error: authLastError,
  })
})

// POST /auth/start — get device code and start background polling
authRoutes.post("/start", async (c) => {
  if (authPolling && pendingAuth) {
    return c.json({
      message: "Auth already in progress",
      user_code: pendingAuth.user_code,
      verification_uri: pendingAuth.verification_uri,
    })
  }

  try {
    const response = await getDeviceCode()
    pendingAuth = response
    authPolling = true
    authLastError = null

    // Poll in background — do not await
    void pollAccessToken(response)
      .then(async (token) => {
        await writeGithubToken(token)
        state.githubToken = token
        consola.info("GitHub authentication completed via web flow")
        try {
          await setupCopilotToken()
          await cacheModels()
          consola.info("Copilot token and models initialised")
        } catch (e) {
          consola.warn("Post-auth setup failed:", e)
        }
      })
      .catch((e: unknown) => {
        authLastError = String(e)
        consola.warn("Web auth polling failed:", e)
      })
      .finally(() => {
        authPolling = false
        pendingAuth = null
      })

    return c.json({
      user_code: response.user_code,
      verification_uri: response.verification_uri,
      expires_in: response.expires_in,
      message: `Open ${response.verification_uri} and enter code: ${response.user_code}`,
    })
  } catch (error) {
    consola.error("Failed to start device auth:", error)
    return c.json({ error: "Failed to start auth flow" }, 500)
  }
})

// POST /auth/logout — clear stored token
authRoutes.post("/logout", async (c) => {
  const { clearGithubToken } = await import("~/lib/token")
  await clearGithubToken()
  return c.json({ message: "Logged out" })
})

// GET /auth/token-file — check whether a token file exists (for debugging)
authRoutes.get("/token-file", async (c) => {
  try {
    const token = await readGithubToken()
    return c.json({ exists: Boolean(token) })
  } catch {
    return c.json({ exists: false })
  }
})
