#!/usr/bin/env python3

import json
import os
from pathlib import Path


def main() -> None:
    manifest_path = Path("lzc-manifest.yml")
    meta_path = Path(".lazycat-build.json")

    build_version = os.environ["BUILD_VERSION"]
    source_version = os.environ["SOURCE_VERSION"]
    airi_image = os.environ["AIRI_IMAGE"]
    postgres_image = os.environ.get("POSTGRES_IMAGE", "")

    text = manifest_path.read_text()
    lines = []
    in_airi = False
    in_postgres = False
    airi_updated = False
    postgres_updated = False

    for line in text.splitlines():
        if line.startswith("version: "):
            lines.append(f"version: {build_version}")
            continue

        if line.startswith("  airi:"):
            in_airi = True
            in_postgres = False
            lines.append(line)
            continue

        if line.startswith("  postgres:"):
            in_airi = False
            in_postgres = True
            lines.append(line)
            continue

        if in_airi and line.strip().startswith("image: "):
            lines.append(f"    image: {airi_image}")
            airi_updated = True
            continue

        if in_postgres and postgres_image and line.strip().startswith("image: "):
            lines.append(f"    image: {postgres_image}")
            postgres_updated = True
            continue

        lines.append(line)

    if not airi_updated:
        raise SystemExit("failed to update airi image in lzc-manifest.yml")

    if postgres_image and not postgres_updated:
        raise SystemExit("failed to update postgres image in lzc-manifest.yml")

    manifest_path.write_text("\n".join(lines) + "\n")

    build_meta = {
        "upstream_repo": "moeru-ai/airi",
        "source_version": source_version,
        "build_version": build_version,
        "image": airi_image,
        "postgres_image": postgres_image,
        "notes": "Upstream official GHCR release only includes apps/stage-web. This migration builds a combined web+server image for LazyCat.",
    }
    meta_path.write_text(json.dumps(build_meta, indent=2) + "\n")


if __name__ == "__main__":
    main()
