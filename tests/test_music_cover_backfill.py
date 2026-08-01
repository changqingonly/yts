from __future__ import annotations

import asyncio
import os
import sqlite3
import struct
import zlib
from collections.abc import Iterator
from pathlib import Path

import pytest
from conftest import reset_cached_db_engine
from fastapi.testclient import TestClient
from yts_server.db.session import get_sessionmaker
from yts_server.domains.music_cover_backfill import backfill_music_cover_theme_colors
from yts_server.main import create_app


@pytest.fixture(autouse=True)
def isolated_local_profile(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    monkeypatch.setenv("YTS_PROFILE", "local")
    monkeypatch.setenv("YTS_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'yts.db'}")
    monkeypatch.setenv("YTS_AUTH_JWT_SECRET", "test-secret-that-is-long-enough-for-hs256-tests")
    reset_cached_db_engine()
    yield
    reset_cached_db_engine()


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )


def solid_png(color: tuple[int, int, int, int]) -> bytes:
    ihdr = struct.pack(">IIBBBBB", 2, 1, 8, 6, 0, 0, 0)
    raw = b"\x00" + bytes(color + color)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", zlib.compress(raw))
        + _png_chunk(b"IEND", b"")
    )


def insert_ready_job(db_path: str, *, job_id: str, output_path: Path) -> None:
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO music_cover_job "
            "(id, user_uuid, content_hash, generation_epoch, status, priority, trigger_source, "
            "prompt, output_path, output_hash, theme_color, attempt_count, created_at_ms, "
            "updated_at_ms) VALUES (?, 'user', ?, 1, 'ready', 10, 'system', 'prompt', ?, ?, "
            "NULL, 1, 1, 1)",
            (job_id, job_id.ljust(64, "0")[:64], str(output_path), job_id.ljust(64, "f")[:64]),
        )


def test_backfill_persists_missing_theme_once(tmp_path: Path) -> None:
    with TestClient(create_app()):
        db_path = os.environ["YTS_DATABASE_URL"].removeprefix("sqlite+aiosqlite:///")
        cover_path = tmp_path / "cover.png"
        cover_path.write_bytes(solid_png((36, 148, 208, 255)))
        insert_ready_job(db_path, job_id="cover-valid", output_path=cover_path)

        first = asyncio.run(backfill_music_cover_theme_colors(get_sessionmaker()))
        second = asyncio.run(backfill_music_cover_theme_colors(get_sessionmaker()))

        with sqlite3.connect(db_path) as connection:
            row = connection.execute(
                "SELECT status, theme_color FROM music_cover_job WHERE id = 'cover-valid'"
            ).fetchone()
    assert first == 1
    assert second == 0
    assert row == ("ready", "#2494D0")


def test_backfill_marks_invalid_cover_failed(tmp_path: Path) -> None:
    with TestClient(create_app()):
        db_path = os.environ["YTS_DATABASE_URL"].removeprefix("sqlite+aiosqlite:///")
        cover_path = tmp_path / "broken.png"
        cover_path.write_bytes(b"not a png")
        insert_ready_job(db_path, job_id="cover-broken", output_path=cover_path)

        updated = asyncio.run(backfill_music_cover_theme_colors(get_sessionmaker()))

        with sqlite3.connect(db_path) as connection:
            row = connection.execute(
                "SELECT status, error_code, error_message FROM music_cover_job "
                "WHERE id = 'cover-broken'"
            ).fetchone()
    assert updated == 0
    assert row[0] == "failed"
    assert row[1] == "ValueError"
    assert "decode failed" in row[2]
