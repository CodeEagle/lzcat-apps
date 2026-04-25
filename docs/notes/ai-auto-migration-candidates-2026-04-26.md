# AI Auto Migration Candidate Filter - 2026-04-26

Source snapshot: `registry/candidates/latest.json`

## Summary

- Total candidates: 20
- Already migrated: 10
- Excluded: 3
- Needs review: 2
- Portable before manual filter: 5

The first automated pilot target is `rcarmo/piclaw`. It has a clear Docker-based deployment path, a web port (`8080`), and explicit persistent paths (`/config`, `/workspace`). The validate-only migration flow completed through preflight and stopped at the expected build gate.

## Portable Candidate Review

| Candidate | Initial Status | Decision | Reason |
| --- | --- | --- | --- |
| `rcarmo/piclaw` | `portable` | selected | Clear Docker/compose topology, web UI, low external dependency risk. Validate-only flow passed after archive extraction was hardened. |
| `helixml/helix` | `portable` | hold | Agent fleet with GPU/desktop-style runtime assumptions; needs AIPod/compute boundary review before LazyCat packaging. |
| `shuaiplus/nodewarden` | `portable` | reject for first wave | Cloudflare Workers-oriented Bitwarden-compatible server; not a normal container service target. |
| `superradcompany/microsandbox` | `portable` | hold | Sandbox/runtime product likely needs privileged isolation, kernel/runtime assumptions, and security review. |
| `sachinsenal0x64/hifi` | `portable` | hold | Music integration with external service credentials and self-hosting still marked as pending in public project metadata; defer until deployment path is clearer. |

## Pilot Result

Command:

```bash
python3 scripts/auto_migrate.py --from-candidates --build-mode validate-only
```

Outcome:

- `apps/piclaw/` generated
- `registry/repos/piclaw.json` generated
- `registry/repos/index.json` updated
- `.github/workflows/trigger-build.yml` target list updated
- `.migration-state.json` records steps `1` through `8`
- Preflight passed
- Build/install/Browser Use acceptance are still pending

## Follow-Up Before Building Piclaw

- Confirm whether upstream image or local Dockerfile should be preferred long-term.
- Review generated binds and whether `/lzcapp/var/data/piclaw/pibox/...` should be flattened.
- Confirm startup user and ownership for `/config` and `/workspace`.
- Run a real build, install on box, and complete Codex Browser Use acceptance before generating Piclaw copywriting.
