from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.web_probe import WebProbeResult, build_obscura_fetch_command, fetch_page


class WebProbeTest(unittest.TestCase):
    def test_build_obscura_fetch_command_uses_text_dump_and_network_idle(self) -> None:
        command = build_obscura_fetch_command("https://example.com/docs", dump="text")
        self.assertEqual(
            command,
            [
                "obscura",
                "fetch",
                "https://example.com/docs",
                "--dump",
                "text",
                "--wait-until",
                "networkidle0",
                "--quiet",
            ],
        )

    @patch.dict("scripts.web_probe.os.environ", {"OBSCURA_BIN": "/tmp/obscura"})
    def test_build_obscura_fetch_command_uses_env_binary(self) -> None:
        command = build_obscura_fetch_command("https://example.com/docs", dump="links")

        self.assertEqual(command[0], "/tmp/obscura")

    @patch("scripts.web_probe.subprocess.run")
    def test_fetch_page_returns_structured_result(self, run_mock) -> None:
        run_mock.return_value.returncode = 0
        run_mock.return_value.stdout = "Example page"
        run_mock.return_value.stderr = ""

        result = fetch_page("https://example.com/docs", dump="text")

        self.assertEqual(result.url, "https://example.com/docs")
        self.assertEqual(result.dump, "text")
        self.assertEqual(result.content, "Example page")
        self.assertEqual(result.errors, [])

    def test_result_json_roundtrip(self) -> None:
        result = WebProbeResult(
            url="https://example.com",
            dump="links",
            content="[Example](https://example.com)",
            errors=[],
        )

        payload = json.loads(result.to_json())

        self.assertEqual(payload["url"], "https://example.com")
        self.assertEqual(payload["dump"], "links")


if __name__ == "__main__":
    unittest.main()
