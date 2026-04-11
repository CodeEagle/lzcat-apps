import consola from "consola"
import { Hono } from "hono"

import { accountManager } from "~/lib/account-manager"
import { state } from "~/lib/state"
import { rootCause } from "~/lib/utils"
import { getCopilotUsage } from "~/services/github/get-copilot-usage"

export const usageRoute = new Hono()

usageRoute.get("/", async (c) => {
  // Return a 200 with an unauthenticated indicator when no token is present,
  // so the dashboard shows "not authenticated" instead of "connection failed".
  const hasToken =
    state.githubToken ||
    (state.multiAccountEnabled && accountManager.hasAccounts())
  if (!hasToken) {
    return c.json({
      authenticated: false,
      premium_remaining: 0,
      premium_total: 0,
      chat_remaining: 0,
      chat_total: 0,
    })
  }

  try {
    if (state.multiAccountEnabled && accountManager.hasAccounts()) {
      const account = accountManager.getActiveAccount()
      if (account) {
        const usage = await getCopilotUsage(account.githubToken)
        return c.json(usage)
      }
    }
    const usage = await getCopilotUsage()
    return c.json(usage)
  } catch (error) {
    consola.warn(`Error fetching usage: ${rootCause(error)}`)
    consola.debug("Error fetching usage:", error)
    return c.json({ error: "Failed to fetch Copilot usage" }, 500)
  }
})
