# engram — AI Memory Visualizer

Upstream: [jsierra87/engram](https://github.com/jsierra87/engram)  
License: MIT

## What this app packages

The upstream `jsierra87/engram` is primarily a **stdio-only MCP (Model Context Protocol) server** (`engram-protocol` v0.1.0) designed to be used from within AI development tools like Claude Desktop or Claude Code. The MCP server communicates via stdin/stdout and manages AI conversation memory as local markdown files (`STATE.md`, `ENGRAM-LOG.md`, `ENGRAM.md`, `DECISIONS.md`, etc.).

**The MCP server cannot be containerized as a LazyCat web app** — it requires stdio access from an AI client and has no HTTP transport.

This package instead containerizes the upstream's **`VISUALIZER.html`** — a self-contained 117KB browser-based visualization tool that lets users drag-and-drop their engram memory markdown files to explore:

- Session timelines with mode tags
- Decision log with alternatives and rationale
- Workstreams and open items
- Agent registry
- Searchable conversation log

The visualizer is entirely client-side (no server dependency) and is served via nginx.

## Ports

| Service | Port | Protocol |
|---------|------|----------|
| engram  | 80   | HTTP (nginx static) |

## Data paths

None — the visualizer is stateless. Users load their local markdown files via drag-and-drop in the browser. No persistent storage is needed.

## Environment variables

None required.

## Login

No login required. The visualizer is a static read-only tool.

## Known limitations

- This package does NOT include the engram MCP server. The memory management functionality requires the `engram-protocol` npm package installed and configured inside an MCP-compatible AI tool.
- Users must independently manage their engram markdown files using the upstream CLI or MCP server integration.

## Build strategy

`upstream_with_target_template` — clones upstream and builds a minimal nginx container from `Dockerfile.template`, copying `VISUALIZER.html` as the index page.

## Version tracking

No GitHub releases exist. Tracks upstream via `commit_sha`.
