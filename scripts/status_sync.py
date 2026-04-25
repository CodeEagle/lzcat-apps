from __future__ import annotations

import argparse
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

try:
    from .project_config import load_project_config
    from .web_probe import fetch_page
except ImportError:  # pragma: no cover - script execution path
    from project_config import load_project_config
    from web_probe import fetch_page


DETAIL_RE = re.compile(
    r"\[(?P<label>[^\]]+)\]\(https?://lazycat\.cloud/appstore/detail/(?P<package>[^)#?]+)[^)]*\)"
)
DEVELOPER_ID_RE = re.compile(r"/developers/(?P<id>\d+)(?:[/?#]|$)")
APPSTORE_API_BASE = "https://appstore.api.lazycat.cloud/api/v3"


def parse_developer_apps(content: str) -> dict[str, str]:
    apps: dict[str, str] = {}
    for match in DETAIL_RE.finditer(content):
        apps.setdefault(match.group("package").strip(), match.group("label").strip())
    return apps


def parse_developer_apps_api(payload: dict[str, Any]) -> dict[str, str]:
    items = payload.get("items")
    if not isinstance(items, list):
        items = payload.get("apps")
    if not isinstance(items, list):
        return {}

    apps: dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        package = str(item.get("package", "")).strip()
        if not package:
            continue
        information = item.get("information")
        label = ""
        if isinstance(information, dict):
            label = str(information.get("name", "")).strip()
        apps.setdefault(package, label or package)
    return apps


def developer_apps_api_url(developer_page_url: str) -> str:
    match = DEVELOPER_ID_RE.search(developer_page_url)
    if not match:
        raise ValueError(f"Cannot find developer id in URL: {developer_page_url}")
    developer_id = urllib.parse.quote(match.group("id"))
    return f"{APPSTORE_API_BASE}/user/developer/{developer_id}/apps?size=100&page=0"


def fetch_json(url: str, timeout_seconds: int = 30) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "lzcat-apps-status-sync/1.0 (+https://github.com/CodeEagle/lzcat-apps)"},
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def fetch_developer_apps_api(developer_page_url: str) -> dict[str, str]:
    return parse_developer_apps_api(fetch_json(developer_apps_api_url(developer_page_url)))


def write_status(repo_root: Path, apps: dict[str, str]) -> Path:
    output_dir = repo_root / "registry" / "status"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "developer-apps.json"
    output_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "source": "developer_apps_page",
                "apps": apps,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync LazyCat developer app status.")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    config = load_project_config(repo_root)
    if not config.lazycat.status_sync_enabled or not config.lazycat.developer_apps_url:
        print("status sync disabled")
        return 0

    result = fetch_page(config.lazycat.developer_apps_url, dump="links")
    if result.errors:
        print("\n".join(result.errors))
        return 1

    apps = parse_developer_apps(result.content)
    if not apps:
        apps = fetch_developer_apps_api(config.lazycat.developer_apps_url)

    output_path = write_status(repo_root, apps)
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
