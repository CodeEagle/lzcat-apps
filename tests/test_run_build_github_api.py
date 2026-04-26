from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import run_build


class RunBuildGithubApiTest(unittest.TestCase):
    def test_gh_api_json_falls_back_to_http_when_gh_missing(self) -> None:
        payload = {"tag_name": "v1.2.3"}

        response = mock.MagicMock()
        response.read.return_value = json.dumps(payload).encode("utf-8")
        response.__enter__.return_value = response
        response.__exit__.return_value = False

        with mock.patch.object(run_build, "sh", side_effect=FileNotFoundError("gh")):
            with mock.patch("urllib.request.urlopen", return_value=response) as urlopen_mock:
                data = run_build.gh_api_json("repos/example/demo/releases/latest")

        self.assertEqual(data, payload)
        request = urlopen_mock.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.github.com/repos/example/demo/releases/latest")
        self.assertEqual(request.headers["Accept"], "application/vnd.github+json")

    def test_gh_api_json_adds_authorization_header_for_http_fallback(self) -> None:
        payload = {"tag_name": "v1.2.3"}

        response = mock.MagicMock()
        response.read.return_value = json.dumps(payload).encode("utf-8")
        response.__enter__.return_value = response
        response.__exit__.return_value = False

        with mock.patch.object(run_build, "sh", side_effect=RuntimeError("gh failed")):
            with mock.patch.dict(os.environ, {"GH_TOKEN": "secret-token"}, clear=False):
                with mock.patch("urllib.request.urlopen", return_value=response) as urlopen_mock:
                    run_build.gh_api_json("repos/example/demo/releases/latest")

        request = urlopen_mock.call_args.args[0]
        self.assertEqual(request.headers["Authorization"], "Bearer secret-token")

    def test_publish_release_asset_falls_back_to_http_when_gh_missing(self) -> None:
        asset = Path(tempfile.mkdtemp(prefix="run-build-release-")) / "demo.lpk"
        asset.write_bytes(b"demo")

        created_release = {
            "id": 42,
            "html_url": "https://github.com/example/artifacts/releases/tag/v1.2.3",
            "upload_url": "https://uploads.github.com/repos/example/artifacts/releases/42/assets{?name,label}",
        }

        with mock.patch.object(run_build, "sh", side_effect=FileNotFoundError("gh")):
            with mock.patch.object(
                run_build,
                "github_api_request",
                side_effect=[
                    (None, {}),
                    (created_release, {}),
                    ({"state": "uploaded"}, {}),
                ],
            ) as api_mock:
                url = run_build.publish_release_asset(
                    "example/artifacts",
                    "v1.2.3",
                    "Demo",
                    "notes",
                    [asset],
                    {},
                )

        self.assertEqual(url, created_release["html_url"])
        create_call = api_mock.call_args_list[1]
        self.assertEqual(create_call.kwargs["method"], "POST")
        upload_call = api_mock.call_args_list[2]
        self.assertIn("uploads.github.com", upload_call.args[0])

    def test_upload_release_asset_retries_after_deleting_duplicate_name(self) -> None:
        asset = Path(tempfile.mkdtemp(prefix="run-build-upload-")) / "build-report.json"
        asset.write_text("{}", encoding="utf-8")
        release = {
            "id": 42,
            "upload_url": "https://uploads.github.com/repos/example/artifacts/releases/42/assets{?name,label}",
        }

        with mock.patch.object(run_build, "sh", side_effect=FileNotFoundError("gh")):
            with mock.patch.object(
                run_build,
                "github_api_request",
                side_effect=[
                    RuntimeError("GitHub API POST https://uploads.github.com failed: HTTP 422"),
                    ([{"id": 9, "name": "build-report.json"}], {}),
                    (None, {}),
                    ({"state": "uploaded"}, {}),
                ],
            ) as api_mock:
                run_build.upload_release_asset(
                    "example/artifacts",
                    "v1.2.3",
                    asset,
                    {},
                    release=release,
                )

        delete_call = api_mock.call_args_list[2]
        self.assertEqual(delete_call.kwargs["method"], "DELETE")


if __name__ == "__main__":
    unittest.main()
