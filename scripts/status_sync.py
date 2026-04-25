from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

try:
    from .project_config import load_project_config
    from .web_probe import fetch_page
except ImportError:  # pragma: no cover - script execution path
    from project_config import load_project_config
    from web_probe import fetch_page


DETAIL_RE = re.compile(
    r"\[(?P<label>[^\]]+)\]\(https?://lazycat\.cloud/appstore/detail/(?P<package>[^)#?]+)[^)]*\)"
)


def parse_developer_apps(content: str) -> dict[str, str]:
    apps: dict[str, str] = {}
    for match in DETAIL_RE.finditer(content):
        apps.setdefault(match.group("package").strip(), match.group("label").strip())
    return apps


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

    output_path = write_status(repo_root, parse_developer_apps(result.content))
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
