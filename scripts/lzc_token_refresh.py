#!/usr/bin/env python3
"""Resolve a usable LazyCat CLI token, logging in if needed.

Order of precedence:
  1. `LZC_CLI_TOKEN` env var. If set and `--skip-validate` was passed (CI hot
     path), trust it; otherwise verify against /api/user/current first.
  2. `~/.config/lazycat/box-config.json` (`{"token": "..."}`) — the on-disk
     cache `lzc-cli` itself reads.
  3. Form-login `POST https://account.lazycat.cloud/api/login/signin` with
     `LZC_USR` / `LZC_PWD` env vars when present. The new token is written to
     the box-config file so subsequent `lzc-cli` calls in the same workflow
     find it without rerunning login, and exported to `$GITHUB_ENV` so later
     steps in the job inherit it.

Exit codes:
  0  resolved a valid token (printed to stdout, also exported)
  1  no token + no credentials -> nothing to do
  2  credentials present but login failed
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ACCOUNT_SERVER = "https://account.lazycat.cloud"
SIGNIN_PATH = "/api/login/signin"
CURRENT_USER_PATH = "/api/user/current"
DEFAULT_BOX_CONFIG = Path.home() / ".config" / "lazycat" / "box-config.json"
USER_AGENT = "lzcat-apps-token-refresh/1.0"


class TokenRefreshError(RuntimeError):
    pass


def load_box_config(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    try:
        payload = json.loads(text or "{}")
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def save_box_config(path: Path, config: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


def _post_signin(username: str, password: str, *, server: str = ACCOUNT_SERVER) -> str:
    payload = urllib.parse.urlencode({"username": username, "password": password}).encode("utf-8")
    req = urllib.request.Request(
        server.rstrip("/") + SIGNIN_PATH,
        data=payload,
        method="POST",
        headers={
            "User-Agent": USER_AGENT,
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else str(exc)
        raise TokenRefreshError(f"signin HTTP {exc.code}: {body[:300]}") from exc
    except urllib.error.URLError as exc:
        raise TokenRefreshError(f"signin network error: {exc.reason}") from exc

    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise TokenRefreshError(f"signin returned non-JSON body: {body[:200]}") from exc

    if not isinstance(data, dict) or not data.get("success"):
        raise TokenRefreshError(f"signin rejected: {data!r}")
    token = (((data.get("data") or {}) if isinstance(data.get("data"), dict) else {}).get("token") or "").strip()
    if not token:
        raise TokenRefreshError(f"signin succeeded but no token in payload: {data!r}")
    return token


def _validate_token(token: str, *, server: str = ACCOUNT_SERVER) -> bool:
    if not token:
        return False
    req = urllib.request.Request(
        server.rstrip("/") + CURRENT_USER_PATH,
        method="GET",
        headers={
            "User-Agent": USER_AGENT,
            "X-User-Token": token,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError:
        return False
    except urllib.error.URLError:
        return False
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return False
    return bool(isinstance(data, dict) and data.get("success"))


def resolve_token(
    *,
    env: dict[str, str],
    box_config_path: Path,
    skip_validate: bool,
    server: str = ACCOUNT_SERVER,
) -> tuple[str, str]:
    """Return (token, source). Raises TokenRefreshError on credentialed failure."""
    env_token = (env.get("LZC_CLI_TOKEN") or "").strip()
    if env_token:
        if skip_validate or _validate_token(env_token, server=server):
            return env_token, "env:LZC_CLI_TOKEN"

    file_config = load_box_config(box_config_path)
    file_token = (file_config.get("token") or "").strip() if isinstance(file_config, dict) else ""
    if file_token:
        if skip_validate or _validate_token(file_token, server=server):
            return file_token, f"file:{box_config_path}"

    username = (env.get("LZC_USR") or "").strip()
    password = (env.get("LZC_PWD") or "").strip()
    if not (username and password):
        raise TokenRefreshError(
            "no usable LZC_CLI_TOKEN and LZC_USR/LZC_PWD not set — cannot refresh"
        )

    token = _post_signin(username, password, server=server)
    config = file_config if isinstance(file_config, dict) else {}
    config["token"] = token
    save_box_config(box_config_path, config)
    return token, f"signin:{username}"


def export_for_github_actions(token: str) -> bool:
    """Append `LZC_CLI_TOKEN=<token>` to $GITHUB_ENV so subsequent steps see it."""
    target = os.environ.get("GITHUB_ENV", "").strip()
    if not target:
        return False
    with open(target, "a", encoding="utf-8") as fh:
        fh.write(f"LZC_CLI_TOKEN={token}\n")
    return True


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument(
        "--skip-validate",
        action="store_true",
        help="Trust LZC_CLI_TOKEN / box-config without calling /api/user/current first",
    )
    p.add_argument(
        "--box-config",
        default=str(DEFAULT_BOX_CONFIG),
        help="Path to lzc-cli box-config.json (default: ~/.config/lazycat/box-config.json)",
    )
    p.add_argument(
        "--server",
        default=ACCOUNT_SERVER,
        help="Override LazyCat account server base URL (testing)",
    )
    p.add_argument(
        "--print-token",
        action="store_true",
        help="Print the token to stdout (default: only print the resolution source)",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    try:
        token, source = resolve_token(
            env=dict(os.environ),
            box_config_path=Path(args.box_config),
            skip_validate=args.skip_validate,
            server=args.server,
        )
    except TokenRefreshError as exc:
        print(f"lzc_token_refresh: {exc}", file=sys.stderr)
        # No creds available is a soft failure (workflow may not need lzc-cli for this run).
        no_creds = "LZC_USR/LZC_PWD not set" in str(exc) or "no usable" in str(exc)
        return 1 if no_creds else 2

    exported = export_for_github_actions(token)
    if args.print_token:
        print(token)
    print(
        f"lzc_token_refresh: resolved via {source}; "
        f"GITHUB_ENV {'updated' if exported else 'not set, env-export skipped'}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
