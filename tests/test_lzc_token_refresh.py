from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.lzc_token_refresh import (
    TokenRefreshError,
    export_for_github_actions,
    load_box_config,
    resolve_token,
    save_box_config,
)


class _FakeResponse:
    def __init__(self, body: bytes, status: int = 200) -> None:
        self._body = body
        self.status = status

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc) -> None:
        return None

    def read(self) -> bytes:
        return self._body


class ResolveTokenTest(unittest.TestCase):
    def test_returns_env_token_when_validate_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            box = Path(tmp) / "box-config.json"
            token, source = resolve_token(
                env={"LZC_CLI_TOKEN": "env-tok"},
                box_config_path=box,
                skip_validate=True,
            )
            self.assertEqual(token, "env-tok")
            self.assertEqual(source, "env:LZC_CLI_TOKEN")

    def test_validates_env_token_against_current_user(self) -> None:
        responses = {
            "GET /api/user/current": _FakeResponse(b'{"success": true}'),
        }

        def fake_urlopen(req, timeout=None):
            key = f"{req.get_method()} {req.full_url.split(req.host)[-1]}"
            return responses[key.replace('https://account.lazycat.cloud', '')]

        with tempfile.TemporaryDirectory() as tmp, patch(
            "scripts.lzc_token_refresh.urllib.request.urlopen", side_effect=fake_urlopen
        ):
            token, source = resolve_token(
                env={"LZC_CLI_TOKEN": "env-tok"},
                box_config_path=Path(tmp) / "box-config.json",
                skip_validate=False,
            )
        self.assertEqual(token, "env-tok")
        self.assertEqual(source, "env:LZC_CLI_TOKEN")

    def test_falls_back_to_box_config_when_env_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            box = Path(tmp) / "box-config.json"
            box.parent.mkdir(parents=True, exist_ok=True)
            box.write_text(json.dumps({"token": "file-tok", "boxname": "demo"}))
            token, source = resolve_token(
                env={},
                box_config_path=box,
                skip_validate=True,
            )
            self.assertEqual(token, "file-tok")
            self.assertTrue(source.startswith("file:"))

    def test_signin_when_no_existing_token_and_creds_present(self) -> None:
        signin_body = json.dumps({"success": True, "data": {"token": "fresh-tok"}}).encode()

        def fake_urlopen(req, timeout=None):
            self.assertEqual(req.get_method(), "POST")
            self.assertTrue(req.full_url.endswith("/api/login/signin"))
            self.assertIn(b"username=alice", req.data)
            self.assertIn(b"password=hunter2", req.data)
            return _FakeResponse(signin_body)

        with tempfile.TemporaryDirectory() as tmp, patch(
            "scripts.lzc_token_refresh.urllib.request.urlopen", side_effect=fake_urlopen
        ):
            box = Path(tmp) / "box-config.json"
            token, source = resolve_token(
                env={"LZC_USR": "alice", "LZC_PWD": "hunter2"},
                box_config_path=box,
                skip_validate=True,
            )
            self.assertEqual(token, "fresh-tok")
            self.assertEqual(source, "signin:alice")
            saved = json.loads(box.read_text())
            self.assertEqual(saved["token"], "fresh-tok")

    def test_signin_preserves_existing_box_config_keys(self) -> None:
        # File has a stale token + other keys. Validation rejects the token
        # (success: false), so signin runs and the saved config keeps the
        # non-token keys intact.
        validate_body = json.dumps({"success": False}).encode()
        signin_body = json.dumps({"success": True, "data": {"token": "fresh-tok"}}).encode()

        def fake_urlopen(req, timeout=None):
            if "user/current" in req.full_url:
                return _FakeResponse(validate_body)
            return _FakeResponse(signin_body)

        with tempfile.TemporaryDirectory() as tmp, patch(
            "scripts.lzc_token_refresh.urllib.request.urlopen", side_effect=fake_urlopen
        ):
            box = Path(tmp) / "box-config.json"
            box.parent.mkdir(parents=True, exist_ok=True)
            box.write_text(json.dumps({"token": "stale", "boxname": "demo", "extra": 1}))
            token, _ = resolve_token(
                env={"LZC_USR": "alice", "LZC_PWD": "hunter2"},
                box_config_path=box,
                skip_validate=False,
            )
            self.assertEqual(token, "fresh-tok")
            saved = json.loads(box.read_text())
            self.assertEqual(saved["boxname"], "demo")
            self.assertEqual(saved["extra"], 1)
            self.assertEqual(saved["token"], "fresh-tok")

    def test_raises_when_no_token_no_creds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(TokenRefreshError) as ctx:
                resolve_token(
                    env={},
                    box_config_path=Path(tmp) / "box-config.json",
                    skip_validate=True,
                )
            self.assertIn("no usable LZC_CLI_TOKEN", str(ctx.exception))

    def test_raises_when_signin_payload_indicates_failure(self) -> None:
        signin_body = json.dumps({"success": False, "message": "bad password"}).encode()
        with tempfile.TemporaryDirectory() as tmp, patch(
            "scripts.lzc_token_refresh.urllib.request.urlopen",
            return_value=_FakeResponse(signin_body),
        ):
            with self.assertRaises(TokenRefreshError) as ctx:
                resolve_token(
                    env={"LZC_USR": "alice", "LZC_PWD": "wrong"},
                    box_config_path=Path(tmp) / "box-config.json",
                    skip_validate=True,
                )
            self.assertIn("signin rejected", str(ctx.exception))

    def test_falls_through_to_signin_when_env_token_invalid(self) -> None:
        # /api/user/current returns success: false -> token rejected; signin runs
        validate_body = json.dumps({"success": False}).encode()
        signin_body = json.dumps({"success": True, "data": {"token": "fresh-tok"}}).encode()

        def fake_urlopen(req, timeout=None):
            if "user/current" in req.full_url:
                return _FakeResponse(validate_body)
            return _FakeResponse(signin_body)

        with tempfile.TemporaryDirectory() as tmp, patch(
            "scripts.lzc_token_refresh.urllib.request.urlopen", side_effect=fake_urlopen
        ):
            token, source = resolve_token(
                env={"LZC_CLI_TOKEN": "stale", "LZC_USR": "alice", "LZC_PWD": "hunter2"},
                box_config_path=Path(tmp) / "box-config.json",
                skip_validate=False,
            )
        self.assertEqual(token, "fresh-tok")
        self.assertEqual(source, "signin:alice")


class GithubActionsExportTest(unittest.TestCase):
    def test_writes_to_github_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "github_env"
            target.touch()
            with patch.dict(os.environ, {"GITHUB_ENV": str(target)}, clear=False):
                ok = export_for_github_actions("hello")
            self.assertTrue(ok)
            self.assertEqual(target.read_text(), "LZC_CLI_TOKEN=hello\n")

    def test_returns_false_when_github_env_unset(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(export_for_github_actions("hello"))


class BoxConfigIOTest(unittest.TestCase):
    def test_load_returns_empty_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(load_box_config(Path(tmp) / "missing.json"), {})

    def test_load_returns_empty_on_invalid_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "bad.json"
            p.write_text("not json")
            self.assertEqual(load_box_config(p), {})

    def test_save_creates_parent_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "deep" / "config" / "box-config.json"
            save_box_config(p, {"token": "abc"})
            self.assertEqual(json.loads(p.read_text())["token"], "abc")


if __name__ == "__main__":
    unittest.main()
