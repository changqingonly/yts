from __future__ import annotations

import asyncio
import hashlib
import os
import time
import uuid
from importlib import resources
from pathlib import Path

import mutagen
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from yts_core.config import get_settings

from ..db.models import AudioPlaybackRendition, LocalImportBlob

PLAYBACK_PROFILE = "aac_lc_m4a_160k_v1"
PLAYBACK_MIME = "audio/mp4"
PENDING = "pending"
PROCESSING = "processing"
READY = "ready"
FAILED = "failed"
MAX_ERROR_MESSAGE_LENGTH = 4000


class RenditionProcessingError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def rendition_id(content_hash: str) -> str:
    return f"{content_hash}:{PLAYBACK_PROFILE}"


async def ensure_pending_rendition(
    session: AsyncSession, content_hash: str
) -> AudioPlaybackRendition:
    identifier = rendition_id(content_hash)
    rendition = await session.get(AudioPlaybackRendition, identifier)
    if rendition is not None:
        return rendition
    now_ms = _now_ms()
    rendition = AudioPlaybackRendition(
        id=identifier,
        original_content_hash=content_hash,
        profile=PLAYBACK_PROFILE,
        status=PENDING,
        output_hash=None,
        output_path=None,
        output_mime=None,
        size_bytes=None,
        error_code=None,
        error_message=None,
        attempt_count=0,
        created_at_ms=now_ms,
        updated_at_ms=now_ms,
    )
    session.add(rendition)
    await session.flush()
    return rendition


async def enqueue_missing_renditions(sessionmaker: async_sessionmaker) -> int:
    async with sessionmaker() as session:
        content_hashes = list(
            (
                await session.execute(
                    select(LocalImportBlob.hash).order_by(LocalImportBlob.hash.asc())
                )
            ).scalars()
        )
        existing_hashes = set(
            (
                await session.execute(
                    select(AudioPlaybackRendition.original_content_hash).where(
                        AudioPlaybackRendition.profile == PLAYBACK_PROFILE
                    )
                )
            ).scalars()
        )
        missing_hashes = [
            content_hash for content_hash in content_hashes if content_hash not in existing_hashes
        ]
        for content_hash in missing_hashes:
            await ensure_pending_rendition(session, content_hash)
        await session.commit()
        return len(missing_hashes)


def build_ffmpeg_command(
    *, ffmpeg_executable: str, source_path: Path, output_path: Path
) -> list[str]:
    return [
        ffmpeg_executable,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source_path),
        "-vn",
        "-c:a",
        "aac",
        "-profile:a",
        "aac_low",
        "-b:a",
        "160k",
        "-ac",
        "2",
        "-movflags",
        "+faststart",
        str(output_path),
    ]


async def process_rendition(
    sessionmaker: async_sessionmaker,
    content_hash: str,
    *,
    ffmpeg_executable: str | None = None,
    output_dir: Path | None = None,
) -> bool:
    if not await _claim_pending_rendition(sessionmaker, content_hash):
        return False
    executable = ffmpeg_executable
    if executable is None:
        try:
            executable = _packaged_ffmpeg_executable()
        except (ImportError, RuntimeError) as error:
            await _mark_failed(sessionmaker, content_hash, "ffmpeg_missing", str(error))
            return True
    destination_dir = output_dir or Path(get_settings().playback_rendition_storage_dir)
    temporary_path: Path | None = None
    try:
        destination_dir.mkdir(parents=True, exist_ok=True)
        temporary_path = destination_dir / f".{content_hash}.{uuid.uuid4().hex}.m4a"
        source_path = await _original_path(sessionmaker, content_hash)
        command = build_ffmpeg_command(
            ffmpeg_executable=executable,
            source_path=source_path,
            output_path=temporary_path,
        )
        await _run_ffmpeg(command)
        _validate_output(temporary_path)
        output_bytes = temporary_path.read_bytes()
        output_hash = hashlib.sha256(output_bytes).hexdigest()
        final_path = destination_dir / output_hash
        os.replace(temporary_path, final_path)
        await _mark_ready(
            sessionmaker,
            content_hash,
            output_hash=output_hash,
            output_path=final_path,
            size_bytes=len(output_bytes),
        )
    except RenditionProcessingError as error:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        await _mark_failed(sessionmaker, content_hash, error.code, str(error))
    except OSError as error:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        await _mark_failed(sessionmaker, content_hash, "artifact_io_failed", str(error))
    return True


async def process_next_pending_rendition(
    sessionmaker: async_sessionmaker,
    *,
    ffmpeg_executable: str | None = None,
    output_dir: Path | None = None,
) -> bool:
    async with sessionmaker() as session:
        content_hash = (
            await session.execute(
                select(AudioPlaybackRendition.original_content_hash)
                .where(AudioPlaybackRendition.status == PENDING)
                .order_by(AudioPlaybackRendition.created_at_ms.asc())
                .limit(1)
            )
        ).scalar_one_or_none()
    if content_hash is None:
        return False
    return await process_rendition(
        sessionmaker,
        content_hash,
        ffmpeg_executable=ffmpeg_executable,
        output_dir=output_dir,
    )


async def run_rendition_worker(
    *, stop_event: asyncio.Event, wake_event: asyncio.Event
) -> None:
    from ..db.session import get_sessionmaker

    sessionmaker = get_sessionmaker()
    while True:
        await wake_event.wait()
        wake_event.clear()
        if stop_event.is_set():
            return
        while await process_next_pending_rendition(sessionmaker):
            if stop_event.is_set():
                return


async def _claim_pending_rendition(
    sessionmaker: async_sessionmaker, content_hash: str
) -> bool:
    async with sessionmaker() as session:
        result = await session.execute(
            update(AudioPlaybackRendition)
            .where(
                AudioPlaybackRendition.id == rendition_id(content_hash),
                AudioPlaybackRendition.status == PENDING,
            )
            .values(
                status=PROCESSING,
                attempt_count=AudioPlaybackRendition.attempt_count + 1,
                updated_at_ms=_now_ms(),
            )
        )
        await session.commit()
        return result.rowcount == 1


async def _original_path(sessionmaker: async_sessionmaker, content_hash: str) -> Path:
    async with sessionmaker() as session:
        blob = await session.get(LocalImportBlob, content_hash)
    if blob is None:
        raise RenditionProcessingError(
            "original_missing", f"original asset row not found: {content_hash}"
        )
    path = Path(blob.path)
    if not path.is_file():
        raise RenditionProcessingError("original_file_missing", f"original file not found: {path}")
    return path


async def _run_ffmpeg(command: list[str]) -> None:
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as error:
        raise RenditionProcessingError("ffmpeg_missing", str(error)) from error
    _, stderr = await process.communicate()
    if process.returncode != 0:
        diagnosis = stderr.decode("utf-8", errors="replace")[-MAX_ERROR_MESSAGE_LENGTH:]
        raise RenditionProcessingError(
            "ffmpeg_failed", f"ffmpeg exited with {process.returncode}: {diagnosis}"
        )


def _validate_output(path: Path) -> None:
    if not path.is_file() or path.stat().st_size == 0:
        raise RenditionProcessingError("output_invalid", "ffmpeg produced no audio file")
    try:
        audio = mutagen.File(path)
    except mutagen.MutagenError as error:
        raise RenditionProcessingError(
            "output_invalid", f"rendition metadata is unreadable: {error}"
        ) from error
    if audio is None or audio.info is None:
        raise RenditionProcessingError("output_invalid", "rendition metadata is unreadable")
    mime_types = getattr(audio, "mime", [])
    if "audio/mp4" not in mime_types:
        raise RenditionProcessingError(
            "output_invalid", f"rendition container is not MP4: {mime_types}"
        )
    if getattr(audio.info, "channels", None) != 2:
        raise RenditionProcessingError("output_invalid", "rendition must contain two channels")
    if getattr(audio.info, "length", 0) <= 0:
        raise RenditionProcessingError("output_invalid", "rendition duration must be positive")


async def _mark_ready(
    sessionmaker: async_sessionmaker,
    content_hash: str,
    *,
    output_hash: str,
    output_path: Path,
    size_bytes: int,
) -> None:
    async with sessionmaker() as session:
        rendition = await session.get(AudioPlaybackRendition, rendition_id(content_hash))
        if rendition is None or rendition.status != PROCESSING:
            raise RuntimeError("processing rendition row disappeared before publication")
        rendition.status = READY
        rendition.output_hash = output_hash
        rendition.output_path = str(output_path)
        rendition.output_mime = PLAYBACK_MIME
        rendition.size_bytes = size_bytes
        rendition.error_code = None
        rendition.error_message = None
        rendition.updated_at_ms = _now_ms()
        await session.commit()


async def _mark_failed(
    sessionmaker: async_sessionmaker, content_hash: str, code: str, message: str
) -> None:
    async with sessionmaker() as session:
        rendition = await session.get(AudioPlaybackRendition, rendition_id(content_hash))
        if rendition is None or rendition.status != PROCESSING:
            raise RuntimeError("processing rendition row disappeared before failure recording")
        rendition.status = FAILED
        rendition.output_hash = None
        rendition.output_path = None
        rendition.output_mime = None
        rendition.size_bytes = None
        rendition.error_code = code
        rendition.error_message = message[-MAX_ERROR_MESSAGE_LENGTH:]
        rendition.updated_at_ms = _now_ms()
        await session.commit()


def _packaged_ffmpeg_executable() -> str:
    from imageio_ffmpeg._definitions import FNAME_PER_PLATFORM, get_platform

    executable = Path(
        str(
            resources.files("imageio_ffmpeg.binaries")
            / FNAME_PER_PLATFORM[get_platform()]
        )
    )
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise RuntimeError(f"packaged ffmpeg executable not found: {executable}")
    return str(executable)


def _now_ms() -> int:
    return time.time_ns() // 1_000_000
