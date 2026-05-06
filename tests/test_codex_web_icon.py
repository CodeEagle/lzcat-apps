from __future__ import annotations

import struct
import zlib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ICON = REPO_ROOT / "apps" / "codex-web" / "icon.png"


def _paeth(left: int, up: int, upper_left: int) -> int:
    estimate = left + up - upper_left
    left_distance = abs(estimate - left)
    up_distance = abs(estimate - up)
    upper_left_distance = abs(estimate - upper_left)
    if left_distance <= up_distance and left_distance <= upper_left_distance:
        return left
    if up_distance <= upper_left_distance:
        return up
    return upper_left


def _decode_rgba(data: bytes, width: int, height: int) -> bytes:
    offset = 8
    idat = bytearray()
    bit_depth = color_type = None

    while offset < len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        chunk_type = data[offset + 4 : offset + 8]
        chunk = data[offset + 8 : offset + 8 + length]
        offset += length + 12

        if chunk_type == b"IHDR":
            bit_depth = chunk[8]
            color_type = chunk[9]
        elif chunk_type == b"IDAT":
            idat.extend(chunk)
        elif chunk_type == b"IEND":
            break

    assert bit_depth == 8
    assert color_type == 6

    stride = width * 4
    raw = zlib.decompress(bytes(idat))
    rows = bytearray()
    previous = bytearray(stride)
    pos = 0

    for _ in range(height):
        filter_type = raw[pos]
        pos += 1
        row = bytearray(raw[pos : pos + stride])
        pos += stride

        for index, value in enumerate(row):
            left = row[index - 4] if index >= 4 else 0
            up = previous[index]
            upper_left = previous[index - 4] if index >= 4 else 0
            if filter_type == 1:
                row[index] = (value + left) & 0xFF
            elif filter_type == 2:
                row[index] = (value + up) & 0xFF
            elif filter_type == 3:
                row[index] = (value + ((left + up) // 2)) & 0xFF
            elif filter_type == 4:
                row[index] = (value + _paeth(left, up, upper_left)) & 0xFF
            else:
                assert filter_type == 0

        rows.extend(row)
        previous = row

    return bytes(rows)


def test_codex_web_icon_is_real_png() -> None:
    data = ICON.read_bytes()
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    width, height = struct.unpack(">II", data[16:24])

    assert (width, height) == (512, 512)
    assert 1024 < len(data) < 200 * 1024

    pixels = _decode_rgba(data, width, height)
    visible_colored_pixels = 0
    codex_blue_pixels = 0
    for red, green, blue, alpha in zip(
        pixels[0::4],
        pixels[1::4],
        pixels[2::4],
        pixels[3::4],
    ):
        if alpha > 200 and (red < 245 or green < 245 or blue < 245):
            visible_colored_pixels += 1
        if alpha > 200 and blue > 180 and blue > red + 20 and blue > green:
            codex_blue_pixels += 1

    assert visible_colored_pixels > 50_000
    assert codex_blue_pixels > 10_000
