# Codex Browser Use Acceptance

Browser acceptance is required before publishing a LazyCat app. HTTP health checks are not enough; the app must render and the primary workflow must work in Codex Browser Use.

1. Generate the acceptance plan:

```bash
python3 scripts/functional_checker.py <slug> --box-domain <box-domain>
```

The first run is expected to exit non-zero until a Browser Use result is recorded.

2. Open `apps/<slug>/.browser-acceptance-plan.json` and use Codex Browser Use to open the `entry_url`.

3. Verify real app content renders, not a LazyCat platform error page, blank page, redirect loop, or server error.

4. Check Browser Use console logs and failed network requests for blocking frontend or backend problems.

5. Exercise the obvious first workflow from the app README or visible UI.

6. If the app fails, record a failed result:

```bash
python3 scripts/record_browser_acceptance.py <slug> \
  --status fail \
  --entry-url "https://<subdomain>.<box-domain>" \
  --blocking-issue "Root page renders but API calls return 404"
```

7. If the app passes, record a passing result:

```bash
python3 scripts/record_browser_acceptance.py <slug> \
  --status pass \
  --entry-url "https://<subdomain>.<box-domain>" \
  --evidence "Home page and primary workflow rendered successfully in Codex Browser Use."
```

8. Re-run the functional checker:

```bash
python3 scripts/functional_checker.py <slug> --box-domain <box-domain>
```

Publishing is allowed only when the functional checker exits with code `0`.
