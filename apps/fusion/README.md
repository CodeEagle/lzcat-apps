# Fusion

Fusion is a multi-node AI coding agent orchestrator and web task board.

## Upstream

- Repository: https://github.com/Runfusion/Fusion
- Homepage: https://runfusion.ai
- License: MIT
- Version strategy: GitHub release/tag, current baseline `0.9.1`

## LazyCat Packaging

- Build strategy: `upstream_with_target_template`
- Service: `fusion`
- Port: `4040`
- Subdomain: `fusion`
- Persistent project root: `/project`
- Persistent home: `/home/node`

The package builds from the upstream repository but replaces the upstream Dockerfile with `Dockerfile.template`. The template fixes the production package filter, keeps the compiled dashboard/CLI artifacts, and starts Fusion from `/project` so the project `.fusion` database and `.worktrees` stay on LazyCat persistent storage.

Fusion dashboard bearer-token auth is disabled with `--no-auth`; access is expected to be protected by LazyCat's app entry. Provider and GitHub credentials can be passed through deployment parameters or configured later in Fusion's settings.

## Data

- `/project`: user project workspace, `.fusion` project database, task files, and `.worktrees`
- `/home/node`: global Fusion settings, provider auth files, SSH config, cache, and local runtime state

## Runtime Notes

Fusion needs a git repository inside `/project` for full worktree automation. The dashboard can still open without a repository and guide the user through first-run project setup.
