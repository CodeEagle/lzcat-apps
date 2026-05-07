from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.codex_discovery_reviewer import (
    DiscoveryReviewerConfig,
    build_codex_command,
    build_codex_prompt,
    fetch_license_info,
    fetch_repo_signals,
    format_license_block,
    format_repo_signals_block,
    run_codex,
    safe_task_name,
    write_task_bundle,
)


class CodexDiscoveryReviewerTest(unittest.TestCase):
    def make_repo_root(self) -> Path:
        return Path(tempfile.mkdtemp(prefix="codex-discovery-reviewer-test-"))

    def test_build_codex_prompt_contains_decision_contract(self) -> None:
        repo_root = self.make_repo_root()
        queue_path = repo_root / "registry" / "auto-migration" / "queue.json"
        item = {
            "id": "github:owner/demo",
            "source": "owner/demo",
            "slug": "demo",
            "state": "discovery_review",
            "candidate": {"status": "needs_review", "status_reason": "Name matches existing app weakly"},
        }

        prompt = build_codex_prompt(repo_root, queue_path, item, developer_url="https://lazycat.cloud/appstore/more/developers/178")

        self.assertIn("owner/demo", prompt)
        self.assertIn("migrate", prompt)
        self.assertIn("skip", prompt)
        self.assertIn("needs_human", prompt)
        self.assertIn("waiting_for_human", prompt)
        self.assertIn("discovery_review", prompt)
        self.assertIn("developer", prompt)

    def test_build_codex_prompt_includes_store_search_hit_contract(self) -> None:
        repo_root = self.make_repo_root()
        queue_path = repo_root / "registry" / "auto-migration" / "queue.json"
        item = {
            "id": "local-agent:paperclipai/paperclip",
            "source": "paperclipai/paperclip",
            "slug": "paperclip",
            "state": "discovery_review",
            "candidate": {
                "status": "needs_review",
                "lazycat_hits": [
                    {
                        "raw_label": "Paperclip AI",
                        "detail_url": "https://lazycat.cloud/appstore/paperclip",
                        "reason": "name match",
                    }
                ],
                "ai_store_review": {"status": "pending", "source": "lazycat_store_search"},
            },
        }

        prompt = build_codex_prompt(repo_root, queue_path, item)

        self.assertIn("LazyCat app-store search hits", prompt)
        self.assertIn("Paperclip AI", prompt)
        self.assertIn("https://lazycat.cloud/appstore/paperclip", prompt)
        self.assertIn("choose `needs_human`; do not guess", prompt)
        self.assertIn("choose `skip` and cite the hit", prompt)

    def test_build_codex_command_invokes_claude_cli_unattended(self) -> None:
        repo_root = self.make_repo_root()
        config = DiscoveryReviewerConfig(
            repo_root=repo_root,
            queue_path=repo_root / "queue.json",
            task_dir=repo_root / "tasks" / "demo",
        )

        command = build_codex_command(config)

        self.assertEqual(command[0], "claude")
        self.assertIn("--print", command)
        self.assertIn("--dangerously-skip-permissions", command)
        self.assertIn("--add-dir", command)
        self.assertIn(str(repo_root), command)
        self.assertIn("--model", command)
        self.assertIn("claude-sonnet-4-6", command)
        # No interactive sandbox / approval flags now that we're on claude.
        self.assertNotIn("--ask-for-approval", command)
        self.assertNotIn("--sandbox", command)

    def test_write_task_bundle_writes_prompt_and_metadata(self) -> None:
        repo_root = self.make_repo_root()
        item = {"id": "github:owner/demo", "source": "owner/demo", "slug": "demo", "state": "discovery_review"}
        config = DiscoveryReviewerConfig(
            repo_root=repo_root,
            queue_path=repo_root / "queue.json",
            task_dir=repo_root / "tasks" / "demo",
        )

        bundle = write_task_bundle(config, item, prompt="Review this", command=["codex", "exec"], now="2026-04-26T00:00:00Z")

        self.assertEqual((config.task_dir / "prompt.md").read_text(encoding="utf-8"), "Review this")
        metadata = json.loads((config.task_dir / "task.json").read_text(encoding="utf-8"))
        self.assertEqual(metadata["queue_path"], str(config.queue_path))
        self.assertEqual(metadata["item"]["id"], "github:owner/demo")
        self.assertEqual(bundle["prompt_path"], str(config.task_dir / "prompt.md"))

    def test_safe_task_name_keeps_identifier_readable(self) -> None:
        self.assertEqual(safe_task_name("github:owner/demo"), "github-owner-demo")

    def test_run_codex_writes_stdout_and_stderr_logs(self) -> None:
        repo_root = self.make_repo_root()
        config = DiscoveryReviewerConfig(
            repo_root=repo_root,
            queue_path=repo_root / "queue.json",
            task_dir=repo_root / "tasks" / "demo",
            model="claude-sonnet-4-6",
        )
        config.task_dir.mkdir(parents=True)
        command = build_codex_command(config)

        class Result:
            def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
                self.returncode = returncode
                self.stdout = stdout
                self.stderr = stderr

        calls: list[list[str]] = []

        def fake_run(command_arg: list[str], **kwargs: object) -> Result:
            calls.append(command_arg)
            return Result(0, stdout="claude decision: migrate", stderr="warn: low-confidence input")

        with patch("scripts.codex_discovery_reviewer.subprocess.run", side_effect=fake_run):
            returncode = run_codex(config, "prompt", command)

        self.assertEqual(returncode, 0)
        # No fallback / retry path on claude — exactly one invocation.
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][calls[0].index("--model") + 1], "claude-sonnet-4-6")
        self.assertIn(
            "claude decision: migrate",
            (config.task_dir / "claude.stdout.log").read_text(encoding="utf-8"),
        )
        self.assertIn(
            "warn: low-confidence",
            (config.task_dir / "claude.stderr.log").read_text(encoding="utf-8"),
        )
        self.assertFalse((config.task_dir / "model-fallback.json").exists())


class FetchLicenseInfoTest(unittest.TestCase):
    def _fake_response(self, payload: dict) -> object:
        class _Resp:
            def __init__(self, data: bytes) -> None:
                self._data = data
            def read(self) -> bytes:  # noqa: D401
                return self._data
            def __enter__(self) -> object:
                return self
            def __exit__(self, *exc: object) -> bool:
                return False
        return _Resp(json.dumps(payload).encode("utf-8"))

    def test_returns_spdx_and_snippet_on_200(self) -> None:
        import base64
        item = {"candidate": {"full_name": "owner/demo"}}
        body = "Permission is hereby granted, free of charge"
        payload = {
            "license": {"spdx_id": "MIT", "name": "MIT License", "key": "mit"},
            "encoding": "base64",
            "content": base64.b64encode(body.encode()).decode(),
        }
        with patch("scripts.codex_discovery_reviewer.urllib.request.urlopen",
                   return_value=self._fake_response(payload)):
            info = fetch_license_info(item)
        self.assertEqual(info["fetch_status"], "ok")
        self.assertEqual(info["spdx"], "MIT")
        self.assertEqual(info["name"], "MIT License")
        self.assertIn("Permission is hereby granted", info["snippet"])

    def test_returns_not_found_on_404(self) -> None:
        import urllib.error
        item = {"candidate": {"full_name": "owner/demo"}}
        err = urllib.error.HTTPError(
            "https://api.github.com/repos/owner/demo/license", 404, "Not Found", {}, None,
        )
        with patch("scripts.codex_discovery_reviewer.urllib.request.urlopen", side_effect=err):
            info = fetch_license_info(item)
        self.assertEqual(info["fetch_status"], "not_found")
        self.assertEqual(info["spdx"], "")
        self.assertEqual(info["snippet"], "")

    def test_returns_error_on_other_http_codes(self) -> None:
        import urllib.error
        item = {"candidate": {"full_name": "owner/demo"}}
        err = urllib.error.HTTPError(
            "https://api.github.com/repos/owner/demo/license", 502, "Bad Gateway", {}, None,
        )
        with patch("scripts.codex_discovery_reviewer.urllib.request.urlopen", side_effect=err):
            info = fetch_license_info(item)
        self.assertEqual(info["fetch_status"], "error")
        self.assertIn("502", info["error"])

    def test_returns_error_on_network_failure(self) -> None:
        import urllib.error
        item = {"candidate": {"full_name": "owner/demo"}}
        with patch("scripts.codex_discovery_reviewer.urllib.request.urlopen",
                   side_effect=urllib.error.URLError("nodename nor servname")):
            info = fetch_license_info(item)
        self.assertEqual(info["fetch_status"], "error")
        self.assertIn("network", info["error"])

    def test_skips_when_no_owner_repo_on_item(self) -> None:
        info = fetch_license_info({"candidate": {}})
        self.assertEqual(info["fetch_status"], "skip")

    def test_falls_back_to_item_source_when_candidate_missing_full_name(self) -> None:
        item = {"source": "owner/demo", "candidate": {}}
        payload = {"license": {"spdx_id": "Apache-2.0", "name": "Apache 2.0"}, "content": "", "encoding": ""}
        with patch("scripts.codex_discovery_reviewer.urllib.request.urlopen",
                   return_value=self._fake_response(payload)) as urlopen_mock:
            info = fetch_license_info(item)
        self.assertEqual(info["fetch_status"], "ok")
        self.assertEqual(info["spdx"], "Apache-2.0")
        # URL constructed from item.source even though full_name is missing
        called_req = urlopen_mock.call_args[0][0]
        self.assertIn("repos/owner/demo/license", called_req.full_url)

    def test_uses_gh_pat_for_auth(self) -> None:
        import os
        item = {"candidate": {"full_name": "owner/demo"}}
        payload = {"license": None, "content": "", "encoding": ""}
        captured: dict[str, str] = {}

        def fake_urlopen(req, **_):  # noqa: ANN001
            captured.update(dict(req.headers))
            return self._fake_response(payload)

        with patch.dict(os.environ, {"GH_PAT": "ghp_test"}, clear=False):
            with patch("scripts.codex_discovery_reviewer.urllib.request.urlopen", side_effect=fake_urlopen):
                fetch_license_info(item)
        self.assertEqual(captured.get("Authorization"), "Bearer ghp_test")

    def test_handles_repo_without_license(self) -> None:
        # GitHub returns 200 with license:null when SPDX detection failed
        item = {"candidate": {"full_name": "owner/demo"}}
        payload = {"license": None, "content": "", "encoding": ""}
        with patch("scripts.codex_discovery_reviewer.urllib.request.urlopen",
                   return_value=self._fake_response(payload)):
            info = fetch_license_info(item)
        self.assertEqual(info["fetch_status"], "ok")
        self.assertEqual(info["spdx"], "")


class FormatLicenseBlockTest(unittest.TestCase):
    def test_ok_renders_spdx_name_and_snippet(self) -> None:
        block = format_license_block({
            "fetch_status": "ok", "spdx": "MIT", "name": "MIT License",
            "snippet": "Permission is hereby granted",
        })
        self.assertIn("MIT", block)
        self.assertIn("MIT License", block)
        self.assertIn("Permission is hereby granted", block)
        self.assertIn("```", block)

    def test_ok_with_no_snippet_omits_code_block(self) -> None:
        block = format_license_block({"fetch_status": "ok", "spdx": "MIT", "name": "MIT License"})
        self.assertIn("MIT", block)
        self.assertNotIn("```", block)

    def test_not_found_directs_to_unlicensed_branch(self) -> None:
        block = format_license_block({"fetch_status": "not_found"})
        self.assertIn("No LICENSE file", block)
        self.assertIn("needs_human", block)

    def test_error_directs_to_needs_human_fallback(self) -> None:
        block = format_license_block({"fetch_status": "error", "error": "HTTP 502"})
        self.assertIn("502", block)
        self.assertIn("needs_human", block)

    def test_skip_directs_to_needs_human_when_no_other_signals(self) -> None:
        block = format_license_block({"fetch_status": "skip", "error": "no upstream owner/repo"})
        self.assertIn("skipped", block)
        self.assertIn("needs_human", block)


class BuildCodexPromptLicenseInjectionTest(unittest.TestCase):
    def test_prompt_carries_injected_license_block(self) -> None:
        repo_root = Path(tempfile.mkdtemp(prefix="codex-prompt-license-"))
        queue_path = repo_root / "registry" / "auto-migration" / "queue.json"
        item = {
            "id": "github:owner/demo",
            "slug": "demo",
            "candidate": {"full_name": "owner/demo"},
        }
        info = {
            "fetch_status": "ok", "spdx": "CC-BY-NC-4.0",
            "name": "Creative Commons NC", "snippet": "for non-commercial use only",
        }
        prompt = build_codex_prompt(repo_root, queue_path, item, license_info=info)
        # license block spliced verbatim into Step 0
        self.assertIn("CC-BY-NC-4.0", prompt)
        self.assertIn("for non-commercial use only", prompt)
        # Step 0 instructions still present
        self.assertIn("Step 0", prompt)
        self.assertIn("non_commercial_license", prompt)

    def test_prompt_passes_explicit_license_info_without_network(self) -> None:
        # When license_info is passed explicitly, fetch_license_info MUST
        # not be called (defensive against accidental live fetches in tests).
        repo_root = Path(tempfile.mkdtemp(prefix="codex-prompt-no-net-"))
        queue_path = repo_root / "queue.json"
        item = {"id": "x", "slug": "x", "candidate": {"full_name": "owner/demo"}}
        with patch("scripts.codex_discovery_reviewer.fetch_license_info") as l_mock, \
             patch("scripts.codex_discovery_reviewer.fetch_repo_signals") as s_mock:
            build_codex_prompt(
                repo_root, queue_path, item,
                license_info={"fetch_status": "skip"},
                repo_signals={"fetch_status": "skip"},
            )
            self.assertFalse(l_mock.called)
            self.assertFalse(s_mock.called)


class FetchRepoSignalsTest(unittest.TestCase):
    def _fake_response(self, payload: object) -> object:
        class _Resp:
            def __init__(self, data: bytes) -> None:
                self._data = data
            def read(self) -> bytes:
                return self._data
            def __enter__(self) -> object:
                return self
            def __exit__(self, *exc: object) -> bool:
                return False
        return _Resp(json.dumps(payload).encode("utf-8"))

    def _b64(self, text: str) -> str:
        import base64
        return base64.b64encode(text.encode()).decode()

    def test_returns_skip_when_no_owner_repo(self) -> None:
        info = fetch_repo_signals({"candidate": {}})
        self.assertEqual(info["fetch_status"], "skip")

    def test_returns_not_found_when_repo_missing(self) -> None:
        import urllib.error
        item = {"candidate": {"full_name": "owner/gone"}}
        err = urllib.error.HTTPError("u", 404, "Not Found", {}, None)
        with patch("scripts.codex_discovery_reviewer.urllib.request.urlopen", side_effect=err):
            info = fetch_repo_signals(item)
        self.assertEqual(info["fetch_status"], "not_found")

    def test_collects_root_tree_readme_dockerfile_and_package_json(self) -> None:
        item = {"candidate": {"full_name": "owner/demo"}}
        # Use endswith for URL matching — /contents/ would otherwise be a
        # prefix of /contents/Dockerfile and the wrong response would win.
        responses_by_suffix: dict[str, object] = {
            "/repos/owner/demo/contents/": [
                {"name": "Dockerfile", "type": "file", "size": 200},
                {"name": "package.json", "type": "file", "size": 800},
                {"name": "src", "type": "dir"},
                {"name": "README.md", "type": "file", "size": 4096},
            ],
            "/repos/owner/demo/readme": {
                "encoding": "base64",
                "content": self._b64("# Demo\n\nA self-hosted web app for X."),
            },
            "/repos/owner/demo/contents/Dockerfile": {
                "encoding": "base64",
                "content": self._b64("FROM node:20\nWORKDIR /app\nCOPY . .\nCMD ['node', 'server.js']\n"),
            },
            "/repos/owner/demo/contents/package.json": {
                "encoding": "base64",
                "content": self._b64(json.dumps({
                    "name": "demo",
                    "scripts": {"start": "node server.js", "build": "vite build"},
                    "dependencies": {"express": "^4", "react": "^18"},
                    "devDependencies": {"vite": "^5"},
                })),
            },
        }

        def fake_urlopen(req, **_):  # noqa: ANN001
            for suffix, payload in responses_by_suffix.items():
                if req.full_url.endswith(suffix):
                    return self._fake_response(payload)
            # any other URL → 404
            import urllib.error as e
            raise e.HTTPError(req.full_url, 404, "Not Found", {}, None)

        with patch("scripts.codex_discovery_reviewer.urllib.request.urlopen", side_effect=fake_urlopen):
            info = fetch_repo_signals(item)

        self.assertEqual(info["fetch_status"], "ok")
        self.assertEqual(info["full_name"], "owner/demo")
        names = {f["name"] for f in info["files"]}
        self.assertEqual(names, {"Dockerfile", "package.json", "src", "README.md"})
        self.assertIn("FROM node:20", info["dockerfile"])
        self.assertIn("# Demo", info["readme"])
        pkg = info["package_json"]
        self.assertIsInstance(pkg, dict)
        self.assertIn("express", pkg["dependencies_top"])
        self.assertIn("react", pkg["dependencies_top"])
        self.assertIn("vite", pkg["devDependencies_top"])
        self.assertTrue(pkg["has_start"])
        self.assertIn("react", pkg["framework_hits"])
        self.assertIn("express", pkg["framework_hits"])

    def test_does_not_fetch_signal_files_missing_from_tree(self) -> None:
        # Tree only has README — should not try to fetch Dockerfile etc.
        item = {"candidate": {"full_name": "owner/demo"}}
        responses_by_suffix: dict[str, object] = {
            "/repos/owner/demo/contents/": [
                {"name": "README.md", "type": "file", "size": 200},
            ],
            "/repos/owner/demo/readme": {
                "encoding": "base64",
                "content": self._b64("# Just a doc"),
            },
        }
        called_urls: list[str] = []

        def fake_urlopen(req, **_):  # noqa: ANN001
            called_urls.append(req.full_url)
            for suffix, payload in responses_by_suffix.items():
                if req.full_url.endswith(suffix):
                    return self._fake_response(payload)
            import urllib.error as e
            raise e.HTTPError(req.full_url, 404, "Not Found", {}, None)

        with patch("scripts.codex_discovery_reviewer.urllib.request.urlopen", side_effect=fake_urlopen):
            info = fetch_repo_signals(item)

        self.assertEqual(info["fetch_status"], "ok")
        self.assertEqual(info["dockerfile"], "")
        self.assertEqual(info["package_json"], None)
        # exactly 2 calls: tree + readme
        self.assertEqual(len(called_urls), 2)


class FormatRepoSignalsBlockTest(unittest.TestCase):
    def test_renders_tree_dockerfile_pkg_and_readme(self) -> None:
        signals = {
            "fetch_status": "ok",
            "files": [
                {"name": "Dockerfile", "type": "file", "size": 100},
                {"name": "package.json", "type": "file", "size": 200},
                {"name": "src", "type": "dir"},
            ],
            "dockerfile": "FROM node:20\nCMD ['node']",
            "compose": "",
            "package_json": {
                "scripts": {"start": "node server.js"},
                "dependencies_top": ["express", "react"],
                "devDependencies_top": [],
                "has_start": True,
                "framework_hits": ["express", "react"],
            },
            "pyproject": "", "setup_py": "", "requirements": "",
            "go_mod": "", "cargo_toml": "",
            "readme": "# Demo\n\nA web service.",
            "errors": [],
        }
        block = format_repo_signals_block(signals)
        self.assertIn("Root file tree", block)
        self.assertIn("Dockerfile", block)
        self.assertIn("FROM node:20", block)
        self.assertIn("package.json", block)
        self.assertIn("express, react", block)
        self.assertIn("has_start_script: True", block)
        self.assertIn("# Demo", block)

    def test_renders_skip_status(self) -> None:
        block = format_repo_signals_block({"fetch_status": "skip", "error": "no upstream"})
        self.assertIn("skipped", block)

    def test_renders_not_found(self) -> None:
        block = format_repo_signals_block({"fetch_status": "not_found"})
        self.assertIn("404", block)
        self.assertIn("skip", block)


class BuildCodexPromptRepoSignalsInjectionTest(unittest.TestCase):
    def test_prompt_injects_repo_signals_block(self) -> None:
        repo_root = Path(tempfile.mkdtemp(prefix="codex-prompt-rs-"))
        queue_path = repo_root / "queue.json"
        item = {"id": "x", "slug": "x", "candidate": {"full_name": "owner/demo"}}
        prompt = build_codex_prompt(
            repo_root, queue_path, item,
            license_info={"fetch_status": "skip"},
            repo_signals={
                "fetch_status": "ok",
                "files": [{"name": "Dockerfile", "type": "file", "size": 100}],
                "dockerfile": "FROM node:20",
                "compose": "", "package_json": None,
                "pyproject": "", "setup_py": "", "requirements": "",
                "go_mod": "", "cargo_toml": "",
                "readme": "# something", "errors": [],
            },
        )
        self.assertIn("FROM node:20", prompt)
        self.assertIn("source-code signals", prompt)
        # naked-framework guidance updated to reference the signals
        self.assertIn("naked framework", prompt)


if __name__ == "__main__":
    unittest.main()
