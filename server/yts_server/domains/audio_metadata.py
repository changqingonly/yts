from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import mutagen

from ..errors import AppError

EXTRACTOR_NAME = "mutagen"
EXTRACTOR_VERSION = getattr(mutagen, "version_string", "unknown")


@dataclass(frozen=True)
class AudioMetadata:
    file_format: str
    duration_ms: int
    sample_rate_hz: int | None
    bit_rate_bps: int | None
    channels: int | None
    codec_name: str
    codec_profile: str | None
    container_format: str | None
    extracted_at_ms: int
    extractor_name: str
    extractor_version: str


def extract_audio_metadata(path: Path, *, mime: str, filename: str) -> AudioMetadata:
    audio = mutagen.File(path)
    if audio is None or audio.info is None:
        raise AppError.bad_request(
            "unsupported_audio_file",
            f"unsupported audio file: {filename}",
            "file",
        )
    length = getattr(audio.info, "length", None)
    if length is None or length <= 0:
        raise AppError.bad_request(
            "metadata_extract_failed",
            f"audio duration is missing: {filename}",
            "file",
        )
    file_format = _format_from_mime_or_name(mime, filename)
    return AudioMetadata(
        file_format=file_format,
        duration_ms=max(1, round(float(length) * 1000)),
        sample_rate_hz=_optional_int(getattr(audio.info, "sample_rate", None)),
        bit_rate_bps=_optional_int(getattr(audio.info, "bitrate", None)),
        channels=_optional_int(getattr(audio.info, "channels", None)),
        codec_name=_codec_name(audio.info, file_format),
        codec_profile=getattr(audio.info, "codec_profile", None),
        container_format=audio.mime[0] if getattr(audio, "mime", None) else mime or None,
        extracted_at_ms=time.time_ns() // 1_000_000,
        extractor_name=EXTRACTOR_NAME,
        extractor_version=EXTRACTOR_VERSION,
    )


def _format_from_mime_or_name(mime: str, filename: str) -> str:
    suffix = Path(filename).suffix.lower().removeprefix(".")
    if suffix:
        return suffix
    if "/" in mime:
        return mime.rsplit("/", 1)[1].lower()
    raise AppError.bad_request("unsupported_audio_file", "audio file format is missing", "file")


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return int(value)


def _codec_name(info: object, file_format: str) -> str:
    codec = getattr(info, "codec", None)
    if codec:
        return str(codec)
    if file_format == "wav":
        return "pcm_s16le"
    return type(info).__name__
