from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import mutagen
from mutagen.flac import FLAC
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4
from mutagen.oggvorbis import OggVorbis
from mutagen.wave import WAVE

from ..errors import AppError

EXTRACTOR_NAME = "mutagen"
EXTRACTOR_VERSION = getattr(mutagen, "version_string", "unknown")


@dataclass(frozen=True)
class AudioFormat:
    file_format: str
    container_mime: str
    codec_name: str


AUDIO_FORMATS: dict[type, AudioFormat] = {
    WAVE: AudioFormat("wav", "audio/wav", "pcm_s16le"),
    MP3: AudioFormat("mp3", "audio/mpeg", "mp3"),
    FLAC: AudioFormat("flac", "audio/flac", "flac"),
    OggVorbis: AudioFormat("ogg", "audio/ogg", "vorbis"),
    MP4: AudioFormat("m4a", "audio/mp4", "aac"),
}


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
    audio_format = AUDIO_FORMATS.get(type(audio))
    if audio_format is None:
        raise AppError.bad_request(
            "unsupported_audio_format",
            f"unsupported audio container: {type(audio).__name__}",
            "file",
        )
    return AudioMetadata(
        file_format=audio_format.file_format,
        duration_ms=max(1, round(float(length) * 1000)),
        sample_rate_hz=_optional_int(getattr(audio.info, "sample_rate", None)),
        bit_rate_bps=_optional_int(getattr(audio.info, "bitrate", None)),
        channels=_optional_int(getattr(audio.info, "channels", None)),
        codec_name=_codec_name(audio.info, audio_format),
        codec_profile=getattr(audio.info, "codec_profile", None),
        container_format=audio_format.container_mime,
        extracted_at_ms=time.time_ns() // 1_000_000,
        extractor_name=EXTRACTOR_NAME,
        extractor_version=EXTRACTOR_VERSION,
    )


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return int(value)


def _codec_name(info: object, audio_format: AudioFormat) -> str:
    codec = getattr(info, "codec", None)
    if codec:
        return str(codec)
    return audio_format.codec_name
