from __future__ import annotations

import hashlib
from pathlib import Path

import mutagen
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from yts_server.db.models import AudioPlaybackRendition, Base, LocalImportBlob
from yts_server.domains.audio_metadata import extract_audio_metadata
from yts_server.domains.audio_renditions import (
    PLAYBACK_MIME,
    PLAYBACK_PROFILE,
    build_ffmpeg_command,
    enqueue_missing_renditions,
    ensure_pending_rendition,
    process_rendition,
)

FIXTURES = Path(__file__).parent / "fixtures" / "audio"


@pytest.mark.parametrize(
    ("fixture_name", "file_format", "container_mime", "codec_fragment"),
    [
        ("sample.wav", "wav", "audio/wav", "pcm"),
        ("sample.mp3", "mp3", "audio/mpeg", "mp3"),
        ("sample.flac", "flac", "audio/flac", "flac"),
        ("sample.ogg", "ogg", "audio/ogg", "vorbis"),
    ],
)
def test_audio_metadata_uses_bytes_instead_of_claimed_name_and_mime(
    fixture_name: str,
    file_format: str,
    container_mime: str,
    codec_fragment: str,
) -> None:
    metadata = extract_audio_metadata(
        FIXTURES / fixture_name,
        mime="application/octet-stream",
        filename="misleading.bin",
    )

    assert metadata.file_format == file_format
    assert metadata.container_format == container_mime
    assert codec_fragment in metadata.codec_name.lower()


def test_ffmpeg_command_is_the_versioned_aac_lc_m4a_profile(tmp_path: Path) -> None:
    command = build_ffmpeg_command(
        ffmpeg_executable="/packaged/ffmpeg",
        source_path=FIXTURES / "sample.ogg",
        output_path=tmp_path / "output.m4a",
    )

    assert PLAYBACK_PROFILE == "aac_lc_m4a_160k_v1"
    assert PLAYBACK_MIME == "audio/mp4"
    assert command == [
        "/packaged/ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(FIXTURES / "sample.ogg"),
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
        str(tmp_path / "output.m4a"),
    ]


async def rendition_sessionmaker(tmp_path: Path) -> async_sessionmaker:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'renditions.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False)


async def add_original(sessionmaker: async_sessionmaker, source: Path, target: Path) -> str:
    content = source.read_bytes()
    content_hash = hashlib.sha256(content).hexdigest()
    target.write_bytes(content)
    async with sessionmaker() as session:
        session.add(
            LocalImportBlob(
                hash=content_hash,
                size_bytes=len(content),
                mime="audio/ogg",
                path=str(target),
            )
        )
        await session.commit()
    return content_hash


@pytest.mark.asyncio
async def test_enqueue_missing_renditions_backfills_historical_blobs_idempotently(
    tmp_path: Path,
) -> None:
    sessionmaker = await rendition_sessionmaker(tmp_path)
    first_hash = await add_original(
        sessionmaker,
        FIXTURES / "sample.flac",
        tmp_path / "historical.flac",
    )
    second_hash = await add_original(
        sessionmaker,
        FIXTURES / "sample.ogg",
        tmp_path / "historical.ogg",
    )
    async with sessionmaker() as session:
        await ensure_pending_rendition(session, first_hash)
        await session.commit()

    assert await enqueue_missing_renditions(sessionmaker) == 1
    assert await enqueue_missing_renditions(sessionmaker) == 0

    async with sessionmaker() as session:
        first = await session.get(
            AudioPlaybackRendition, f"{first_hash}:{PLAYBACK_PROFILE}"
        )
        second = await session.get(
            AudioPlaybackRendition, f"{second_hash}:{PLAYBACK_PROFILE}"
        )
        assert first is not None
        assert second is not None
        assert first.status == "pending"
        assert second.status == "pending"


@pytest.mark.asyncio
async def test_pending_rendition_is_unique_and_real_ffmpeg_publishes_m4a(tmp_path: Path) -> None:
    sessionmaker = await rendition_sessionmaker(tmp_path)
    content_hash = await add_original(
        sessionmaker,
        FIXTURES / "sample.ogg",
        tmp_path / "original.ogg",
    )
    async with sessionmaker() as session:
        first = await ensure_pending_rendition(session, content_hash)
        second = await ensure_pending_rendition(session, content_hash)
        await session.commit()
        assert second.id == first.id

    processed = await process_rendition(
        sessionmaker,
        content_hash,
        ffmpeg_executable="/opt/homebrew/bin/ffmpeg",
        output_dir=tmp_path / "outputs",
    )

    assert processed is True
    async with sessionmaker() as session:
        rendition = await session.get(
            AudioPlaybackRendition,
            f"{content_hash}:{PLAYBACK_PROFILE}",
        )
        assert rendition is not None
        assert rendition.status == "ready"
        assert rendition.output_mime == "audio/mp4"
        assert rendition.output_hash == hashlib.sha256(
            Path(rendition.output_path).read_bytes()
        ).hexdigest()
        output = mutagen.File(rendition.output_path)
        assert output is not None
        assert output.info.channels == 2
        assert output.mime[0] == "audio/mp4"


@pytest.mark.asyncio
async def test_missing_ffmpeg_marks_rendition_failed_without_fallback(tmp_path: Path) -> None:
    sessionmaker = await rendition_sessionmaker(tmp_path)
    content_hash = await add_original(
        sessionmaker,
        FIXTURES / "sample.flac",
        tmp_path / "original.flac",
    )
    async with sessionmaker() as session:
        await ensure_pending_rendition(session, content_hash)
        await session.commit()

    processed = await process_rendition(
        sessionmaker,
        content_hash,
        ffmpeg_executable=str(tmp_path / "missing-ffmpeg"),
        output_dir=tmp_path / "outputs",
    )

    assert processed is True
    async with sessionmaker() as session:
        rendition = await session.get(
            AudioPlaybackRendition,
            f"{content_hash}:{PLAYBACK_PROFILE}",
        )
        assert rendition is not None
        assert rendition.status == "failed"
        assert rendition.error_code == "ffmpeg_missing"
        assert "missing-ffmpeg" in rendition.error_message
        assert rendition.output_path is None


@pytest.mark.asyncio
async def test_unwritable_artifact_directory_marks_rendition_failed(tmp_path: Path) -> None:
    sessionmaker = await rendition_sessionmaker(tmp_path)
    content_hash = await add_original(
        sessionmaker,
        FIXTURES / "sample.wav",
        tmp_path / "original.wav",
    )
    async with sessionmaker() as session:
        await ensure_pending_rendition(session, content_hash)
        await session.commit()
    invalid_output_dir = tmp_path / "not-a-directory"
    invalid_output_dir.write_text("file blocks mkdir", encoding="utf-8")

    processed = await process_rendition(
        sessionmaker,
        content_hash,
        ffmpeg_executable="/opt/homebrew/bin/ffmpeg",
        output_dir=invalid_output_dir,
    )

    assert processed is True
    async with sessionmaker() as session:
        rendition = await session.get(
            AudioPlaybackRendition,
            f"{content_hash}:{PLAYBACK_PROFILE}",
        )
        assert rendition is not None
        assert rendition.status == "failed"
        assert rendition.error_code == "artifact_io_failed"
        assert "not-a-directory" in rendition.error_message
