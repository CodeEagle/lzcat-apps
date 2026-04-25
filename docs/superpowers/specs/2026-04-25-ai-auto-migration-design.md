# AI Auto Migration Design

## Goal

Build an AI-assisted LazyCat migration pipeline inside `lzcat-apps` that can discover candidate repositories, gather upstream deployment evidence, run the existing `full_migrate.py` build flow, install packages on a LazyCat device, and require Codex Browser Use functional acceptance before copywriting or publishing.

## Decisions

- `CodeEagle/lzcat-apps` remains the single implementation repo.
- LocalAgent's candidate discovery logic is reused instead of rewriting discovery from scratch.
- Obscura is used for upstream web scraping and LazyCat store/developer-page status collection.
- Codex Browser Use is the release gate for real app functionality. HTTP checks alone are not accepted as functional validation.
- The developer page in `project-config.json` is the canonical source for "apps already published by this developer":
  `https://lazycat.cloud/appstore/more/developers/178`.
- `auto_migrate.py --from-candidates` consumes `registry/candidates/latest.json` and starts the next `portable` candidate by default.
- Publishing remains gated by human confirmation because it submits data to a third-party store.

## Architecture

```text
project-config.json
  -> status_sync.py fetches developer app page
  -> publication_status.py joins developer page results with local apps and registry state
  -> scout_core.py finds and filters candidate repositories, skipping published or already-registered apps
  -> web_probe.py wraps Obscura for upstream docs and store pages
  -> full_migrate.py generates app package assets
  -> run_build.py / local_build.sh builds and installs .lpk
  -> functional_checker.py records install/runtime status and browser acceptance plan
  -> Codex Browser Use opens the real LazyCat app URL and records .browser-acceptance.json
  -> auto_migrate.py advances only when each gate passes
```

## Functional Acceptance Contract

Every app must produce `apps/<slug>/.browser-acceptance.json` before publication:

```json
{
  "schema_version": 1,
  "slug": "markitdown",
  "status": "pass",
  "accepted_at": "2026-04-25T00:00:00Z",
  "entry_url": "https://markitdown.example.heiyu.space",
  "browser_use": {
    "dom_rendered": true,
    "console_errors": [],
    "network_failures": [],
    "screenshots": []
  },
  "checks": [
    {
      "name": "open_home",
      "status": "pass",
      "evidence": "Home page rendered with primary controls visible."
    }
  ],
  "blocking_issues": []
}
```

Publication requires:

- `.browser-acceptance.json.status == "pass"`
- `.functional-check.json.status in {"pass", "browser_pass"}`
- `.publish-state.json` is absent or older than the current package version
- `dist/<slug>.lpk` exists and matches the SHA recorded by the last build
- `lzc-cli app status <package>` is not failed

## Failure Loop

If Browser Use finds a functional problem, the agent records it as a structured blocker:

```json
{
  "category": "routing",
  "summary": "Root page renders but /api returns 404 through LazyCat route.",
  "evidence": ["browser console", "network failure", "container log"],
  "suggested_fix_area": "lzc-manifest.yml application.upstreams",
  "status": "open"
}
```

The next run of `auto_migrate.py --resume <slug>` keeps the app in `functional_failed` until the fix is rebuilt, reinstalled, and reaccepted through Browser Use.

## Scope Boundaries

- This design does not build a web console.
- This design does not add Postgres, Redis, or a custom queue.
- This design does not automate the final store publish click without explicit confirmation.
- This design does not make GitHub Actions run Browser Use. Browser Use runs in the local Codex session after installation.
