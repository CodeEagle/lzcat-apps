from __future__ import annotations

import json
import os
import subprocess
from dataclasses import asdict, dataclass
from typing import Literal


DumpKind = Literal["html", "text", "links"]


@dataclass(frozen=True)
class WebProbeResult:
    url: str
    dump: str
    content: str
    errors: list[str]

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2) + "\n"


def build_obscura_fetch_command(url: str, *, dump: DumpKind = "text") -> list[str]:
    return [
        os.environ.get("OBSCURA_BIN", "obscura"),
        "fetch",
        url,
        "--dump",
        dump,
        "--wait-until",
        "networkidle0",
        "--quiet",
    ]


def fetch_page(url: str, *, dump: DumpKind = "text", timeout_seconds: int = 90) -> WebProbeResult:
    command = build_obscura_fetch_command(url, dump=dump)
    try:
        result = subprocess.run(
            command,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except FileNotFoundError:
        return WebProbeResult(
            url=url,
            dump=dump,
            content="",
            errors=["obscura binary not found in PATH"],
        )
    except subprocess.TimeoutExpired:
        return WebProbeResult(
            url=url,
            dump=dump,
            content="",
            errors=[f"obscura fetch timed out after {timeout_seconds}s"],
        )

    errors: list[str] = []
    if result.returncode != 0:
        errors.append((result.stderr or result.stdout or f"exit={result.returncode}").strip())

    return WebProbeResult(
        url=url,
        dump=dump,
        content=result.stdout.strip(),
        errors=errors,
    )
