import struct
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _rgba_rows(path: Path) -> tuple[int, int, list[bytes]]:
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    offset = 8
    compressed = bytearray()
    while offset < len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        kind = data[offset + 4 : offset + 8]
        payload = data[offset + 8 : offset + 8 + length]
        offset += 12 + length
        if kind == b"IHDR":
            width, height, depth, color_type = struct.unpack(">IIBB", payload[:10])
            assert (depth, color_type) == (8, 6)
        elif kind == b"IDAT":
            compressed.extend(payload)
        elif kind == b"IEND":
            break

    raw = zlib.decompress(compressed)
    stride = width * 4
    rows: list[bytes] = []
    previous = bytearray(stride)
    cursor = 0
    for _ in range(height):
        filter_type = raw[cursor]
        source = raw[cursor + 1 : cursor + 1 + stride]
        cursor += stride + 1
        row = bytearray(stride)
        for index, value in enumerate(source):
            left = row[index - 4] if index >= 4 else 0
            up = previous[index]
            upper_left = previous[index - 4] if index >= 4 else 0
            if filter_type == 0:
                row[index] = value
            elif filter_type == 1:
                row[index] = (value + left) & 0xFF
            elif filter_type == 2:
                row[index] = (value + up) & 0xFF
            elif filter_type == 3:
                row[index] = (value + ((left + up) // 2)) & 0xFF
            elif filter_type == 4:
                estimate = left + up - upper_left
                nearest = min((left, up, upper_left), key=lambda item: abs(estimate - item))
                row[index] = (value + nearest) & 0xFF
            else:
                raise AssertionError(f"unsupported PNG filter {filter_type}")
        rows.append(bytes(row))
        previous = row
    return width, height, rows


def test_macos_app_icon_keeps_platform_safe_area():
    width, height, rows = _rgba_rows(ROOT / "desktop/src-tauri/icons/icon.png")
    opaque = [
        (x, y)
        for y, row in enumerate(rows)
        for x in range(width)
        if row[x * 4 + 3] > 8
    ]
    min_x = min(x for x, _ in opaque)
    max_x = max(x for x, _ in opaque)
    min_y = min(y for _, y in opaque)
    max_y = max(y for _, y in opaque)

    assert max_x - min_x + 1 <= round(width * 0.84)
    assert max_y - min_y + 1 <= round(height * 0.84)
