from __future__ import annotations

import struct
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ICON = REPO_ROOT / "apps" / "codex-web" / "icon.png"


def test_codex_web_icon_is_real_png() -> None:
    data = ICON.read_bytes()
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    width, height = struct.unpack(">II", data[16:24])

    assert (width, height) == (512, 512)
    assert 1024 < len(data) < 200 * 1024
