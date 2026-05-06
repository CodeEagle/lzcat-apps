from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = REPO_ROOT / "apps" / "codex-web" / "Dockerfile"


def test_oauth_relay_follows_codex_success_redirect() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")

    assert "await fetchLocalOAuthCallback(target);" in dockerfile
    assert 'return await fetch(candidate, { redirect: "follow" });' in dockerfile
    assert 'await fetch(target, { redirect: "manual" });' not in dockerfile


def test_oauth_relay_normalizes_loopback_callback_host() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")

    assert "function normalizeLoopbackCallbackUrl(callbackUrl: URL): URL" in dockerfile
    assert "async function fetchLocalOAuthCallback(callbackUrl: URL): Promise<Response>" in dockerfile
    assert 'normalized.hostname = "127.0.0.1";' in dockerfile
    assert "const candidates = [normalizeLoopbackCallbackUrl(callbackUrl), callbackUrl];" in dockerfile
    assert 'normalized === "localhost"' in dockerfile
