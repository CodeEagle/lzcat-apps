# ResumeAI

LazyCat migration of [Doomish77/ResumeAI](https://github.com/Doomish77/ResumeAI).

ResumeAI is a Next.js web application that helps job seekers build ATS-friendly resumes with AI-powered content suggestions (Google Gemini), real-time editing, and customizable templates. Resume data is stored in MongoDB.

## Access

After installation the app is available at `https://resumeai.<your-box-domain>/`.

The root path `/` is publicly accessible. Routes `/dashboard` and `/my-resume/:id/edit` require a Clerk login.

## Prerequisites — required before the app is usable

### 1. Clerk Account (Authentication)

This app uses [Clerk](https://clerk.com) for user authentication.

1. Create a Clerk account and a new application at [clerk.com](https://clerk.com).
2. In the Clerk dashboard → **API Keys**, copy the **Publishable Key** and **Secret Key**.
3. Under **Domains / Allowed redirect URIs**, add `https://resumeai.<your-box-domain>`.
4. Provide the keys when prompted during LazyCat installation.

### 2. Google Gemini API Key (AI Suggestions)

1. Visit [Google AI Studio](https://aistudio.google.com) and create an API key.
2. Provide the key when prompted during LazyCat installation.

## First Launch

1. Navigate to `https://resumeai.<your-box-domain>/sign-up`.
2. Create an account with the same email/password you entered as deploy parameters — this allows LazyCat's passwordless login to auto-fill your credentials on subsequent visits.
3. Begin building resumes from the dashboard.

## Environment Variables

| Variable | Source | Notes |
|---|---|---|
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | Deploy param | Clerk public key; read by server components at runtime |
| `CLERK_SECRET_KEY` | Deploy param | Clerk server-side secret |
| `GEMINI_API_KEY` | Deploy param | Google Gemini API key |
| `MONGODB_URL` | Hardcoded | Points to co-located MongoDB sidecar |
| `BASE_URL` | Edit manually | Set to `https://resumeai.<your-box>` after install for OAuth callbacks |
| `NEXT_PUBLIC_CLERK_SIGN_IN_URL` | Hardcoded | `/sign-in` |
| `NEXT_PUBLIC_CLERK_SIGN_UP_URL` | Hardcoded | `/sign-up` |

## Data Paths

| Service | Container path | Host path |
|---|---|---|
| MongoDB data | `/data/db` | `/lzcapp/var/db/resumeai/mongo` |

## Build Strategy

`upstream_with_target_template` — upstream source (Doomish77/ResumeAI) is cloned, `Dockerfile.template` from this directory is applied, and a standalone Next.js image is built.

## Upstream

- Repo: https://github.com/Doomish77/ResumeAI
- License: MIT
