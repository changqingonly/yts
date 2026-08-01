from __future__ import annotations

import subprocess
from collections import defaultdict

import imageio_ffmpeg

QUANTIZATION_STEP = 16
EXTREME_DARK_MAX = 12
EXTREME_LIGHT_MIN = 243


def extract_theme_color(png: bytes) -> str:
    decoded = subprocess.run(
        [
            imageio_ffmpeg.get_ffmpeg_exe(),
            "-v",
            "error",
            "-i",
            "pipe:0",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgba",
            "pipe:1",
        ],
        input=png,
        capture_output=True,
        check=False,
    )
    if decoded.returncode != 0:
        message = decoded.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(f"cover image decode failed: {message}")
    buckets: dict[tuple[int, int, int], list[int]] = defaultdict(lambda: [0, 0, 0, 0])
    pixels = decoded.stdout
    for index in range(0, len(pixels), 4):
        red, green, blue, alpha = pixels[index : index + 4]
        if alpha == 0:
            continue
        if max(red, green, blue) <= EXTREME_DARK_MAX:
            continue
        if min(red, green, blue) >= EXTREME_LIGHT_MIN:
            continue
        key = (
            red // QUANTIZATION_STEP,
            green // QUANTIZATION_STEP,
            blue // QUANTIZATION_STEP,
        )
        bucket = buckets[key]
        bucket[0] += 1
        bucket[1] += red
        bucket[2] += green
        bucket[3] += blue
    if not buckets:
        raise ValueError("cover image contains no usable pixels for theme extraction")
    _, dominant = max(buckets.items(), key=lambda item: (item[1][0], item[0]))
    count, red_sum, green_sum, blue_sum = dominant
    red = round(red_sum / count / 4) * 4
    green = round(green_sum / count / 4) * 4
    blue = round(blue_sum / count / 4) * 4
    return f"#{red:02X}{green:02X}{blue:02X}"
