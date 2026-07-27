from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from yts_server.audio_backfill import backfill_audio_renditions
from yts_server.db.models import Base, LocalImportBlob

FIXTURES = Path(__file__).parent / "fixtures" / "audio"


@pytest.mark.asyncio
async def test_audio_backfill_processes_missing_renditions_and_is_idempotent(tmp_path: Path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'backfill.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as session:
        for fixture_name in ("sample.flac", "sample.ogg"):
            content = (FIXTURES / fixture_name).read_bytes()
            content_hash = hashlib.sha256(content).hexdigest()
            original_path = tmp_path / content_hash
            original_path.write_bytes(content)
            session.add(
                LocalImportBlob(
                    hash=content_hash,
                    size_bytes=len(content),
                    mime="application/octet-stream",
                    path=str(original_path),
                )
            )
        await session.commit()

    first = await backfill_audio_renditions(
        sessionmaker,
        ffmpeg_executable="/opt/homebrew/bin/ffmpeg",
        output_dir=tmp_path / "renditions",
    )
    second = await backfill_audio_renditions(
        sessionmaker,
        ffmpeg_executable="/opt/homebrew/bin/ffmpeg",
        output_dir=tmp_path / "renditions",
    )

    assert first == {"total": 2, "created": 2, "skipped": 0, "ready": 2, "failed": 0}
    assert second == {"total": 2, "created": 0, "skipped": 2, "ready": 2, "failed": 0}
    await engine.dispose()
