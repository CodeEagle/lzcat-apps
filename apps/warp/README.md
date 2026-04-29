# Warp for LazyCat

This is an unofficial LazyCat migration of [Warp](https://github.com/warpdotdev/warp), exposed through noVNC because upstream Warp is a native Linux desktop terminal rather than an HTTP web service.

## Runtime

- Entry: open the LazyCat app URL and use the noVNC desktop session.
- Service port: `8080` for noVNC.
- Packaged upstream binary: `warp-terminal` Debian package `0.2026.04.27.15.32.stable.02`.
- Display stack: `Xvfb` + `fluxbox` + `x11vnc` + `noVNC`.

## Data

The package persists the full Warp home and a workspace directory:

- `/home/warp` <= `/lzcapp/var/data/warp/home`
- `/workspace` <= `/lzcapp/var/data/warp/workspace`

This keeps Warp config, cache, state, `.warp`, `.ssh`, shell files, and project files across restarts.

## Known Constraints

- This is a desktop compatibility wrapper, not a native web UI.
- Warp's Linux requirements include glibc and OpenGL ES 3.0+ or Vulkan. The image forces Mesa software rendering for LazyCat compatibility, so graphics performance may be lower than a native desktop.
- Warp cloud/AI features still depend on upstream Warp services and the user's own authentication.
- Public store publication should avoid implying official Warp endorsement unless explicit trademark permission is obtained.

## License

Warp's README says `warpui_core` and `warpui` are MIT licensed, while the rest of the repository is AGPL v3. This package includes `LICENSE-AGPL` and `LICENSE-MIT`; any modified source distributed with this LazyCat package must remain available under the applicable upstream licenses.
