from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = REPO_ROOT / "apps" / "codex-web" / "Dockerfile"


def test_oauth_relay_follows_codex_success_redirect() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")

    assert 'await fetch(target, { redirect: "follow" });' in dockerfile
    assert 'await fetch(target, { redirect: "manual" });' not in dockerfile
