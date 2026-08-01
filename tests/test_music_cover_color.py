from __future__ import annotations

import struct
import zlib

import pytest
from yts_server.domains.cover_color import extract_theme_color


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )


def rgba_png(rows: list[list[tuple[int, int, int, int]]]) -> bytes:
    height = len(rows)
    width = len(rows[0])
    raw = b"".join(b"\x00" + bytes(channel for pixel in row for channel in pixel) for row in rows)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", zlib.compress(raw))
        + _png_chunk(b"IEND", b"")
    )


def test_extract_theme_color_returns_dominant_quantized_color() -> None:
    png = rgba_png(
        [
            [(35, 145, 205, 255), (38, 148, 207, 255), (235, 72, 82, 255)],
            [(32, 142, 202, 255), (36, 146, 206, 255), (235, 72, 82, 255)],
        ]
    )

    assert extract_theme_color(png) == "#2494D0"


def test_extract_theme_color_ignores_transparent_black_and_white_pixels() -> None:
    png = rgba_png(
        [[(0, 0, 0, 255), (255, 255, 255, 255), (20, 200, 120, 0), (82, 170, 106, 255)]]
    )

    assert extract_theme_color(png) == "#50A868"


def test_extract_theme_color_fails_when_no_usable_pixels_exist() -> None:
    png = rgba_png([[(0, 0, 0, 255), (255, 255, 255, 255), (40, 80, 120, 0)]])

    with pytest.raises(ValueError, match="no usable pixels"):
        extract_theme_color(png)
