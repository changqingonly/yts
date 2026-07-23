from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from yts_core.config import get_settings

from ..db.models import LocalImportBlob, LocalImportOwner, MetaSong, MusicPlaylistItem
from ..errors import AppError
from .audio_metadata import extract_audio_metadata

VALID_SOURCES = {"remote_song", "local_file", "external_url"}
SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class PlaylistUpload:
    id: str
    playlist_id: str
    source: str
    source_ref: str
    title: str | None
    artist: str | None
    duration_ms: int | None
    cover_url: str | None
    position: float
    added_at_ms: int
    updated_at_ms: int
    deleted_at_ms: int | None
    client_op_clock: int
    device_id: str
    content_hash: str | None
    size_bytes: int | None
    mime: str | None


@dataclass(frozen=True)
class LocalImportFile:
    path: Path
    mime: str


async def sync_playlist(
    session: AsyncSession,
    *,
    user_uuid: str,
    since_clock: int,
    limit: int,
    uploads: list[PlaylistUpload],
) -> dict:
    if since_clock < 0:
        raise AppError.bad_request("invalid_since", "since must be >= 0", "since")
    upload_results: list[dict] = []
    for upload in uploads:
        result = await _apply_upload(session, user_uuid, upload)
        upload_results.append(result)
    changes = await _list_changes(
        session, user_uuid=user_uuid, since_clock=since_clock, limit=limit
    )
    server_clock = max([item.op_clock for item in changes], default=since_clock)
    return {
        "server_clock": server_clock,
        "changes": [_playlist_item_response(item) for item in changes],
        "upload_results": upload_results,
    }


async def store_song_upload(
    session: AsyncSession,
    *,
    user_uuid: str,
    filename: str,
    mime: str,
    content: bytes,
) -> dict:
    if not content:
        raise AppError.bad_request("empty_file", "song upload file must not be empty", "file")
    digest = hashlib.sha256(content).hexdigest()
    storage_dir = Path(get_settings().local_import_storage_dir)
    storage_dir.mkdir(parents=True, exist_ok=True)
    target = storage_dir / digest
    deduplicated = target.exists()
    if not deduplicated:
        target.write_bytes(content)

    blob = await session.get(LocalImportBlob, digest)
    if blob is None:
        blob = LocalImportBlob(
            hash=digest,
            size_bytes=len(content),
            mime=mime or "application/octet-stream",
            path=str(target),
        )
        session.add(blob)

    await _ensure_owner_row(session, user_uuid=user_uuid, content_hash=digest)
    meta_song = await session.get(MetaSong, digest)
    if meta_song is None:
        metadata = extract_audio_metadata(target, mime=mime, filename=filename)
        now_ms = time.time_ns() // 1_000_000
        meta_song = MetaSong(
            content_hash=digest,
            size_bytes=len(content),
            mime=mime or "application/octet-stream",
            file_format=metadata.file_format,
            duration_ms=metadata.duration_ms,
            sample_rate_hz=metadata.sample_rate_hz,
            bit_rate_bps=metadata.bit_rate_bps,
            channels=metadata.channels,
            codec_name=metadata.codec_name,
            codec_profile=metadata.codec_profile,
            container_format=metadata.container_format,
            extracted_at_ms=metadata.extracted_at_ms,
            extractor_name=metadata.extractor_name,
            extractor_version=metadata.extractor_version,
            created_at_ms=now_ms,
            updated_at_ms=now_ms,
        )
        session.add(meta_song)
    await session.flush()
    return {
        "content_hash": digest,
        "filename": filename,
        "size_bytes": len(content),
        "mime": mime or "application/octet-stream",
        "deduplicated": deduplicated,
        "meta_song": _meta_song_response(meta_song),
    }


async def local_import_file_for_user(
    session: AsyncSession,
    *,
    user_uuid: str,
    content_hash: str,
) -> LocalImportFile:
    _validate_hash(content_hash, "hash")
    await _ensure_local_import_owner(session, user_uuid=user_uuid, content_hash=content_hash)
    blob = await session.get(LocalImportBlob, content_hash)
    if blob is None:
        raise AppError.not_found("local_import_missing", "local import blob not found")
    path = Path(blob.path)
    if not path.exists():
        raise AppError.not_found("local_import_file_missing", "local import file not found")
    return LocalImportFile(path=path, mime=blob.mime)


async def _ensure_owner_row(session: AsyncSession, *, user_uuid: str, content_hash: str) -> None:
    existing_owner = (
        await session.execute(
            select(LocalImportOwner).where(
                LocalImportOwner.hash == content_hash,
                LocalImportOwner.user_uuid == user_uuid,
            )
        )
    ).scalar_one_or_none()
    if existing_owner is None:
        session.add(LocalImportOwner(id=_new_i64_id(), hash=content_hash, user_uuid=user_uuid))


async def _apply_upload(session: AsyncSession, user_uuid: str, upload: PlaylistUpload) -> dict:
    _validate_upload(upload)
    if upload.source == "local_file":
        content_hash = upload.content_hash or upload.source_ref
        _validate_hash(content_hash, "content_hash")
        await _ensure_local_import_owner(session, user_uuid=user_uuid, content_hash=content_hash)
    current = await session.get(MusicPlaylistItem, upload.id)
    if current is not None and current.user_uuid != user_uuid:
        raise AppError.forbidden("playlist item owner mismatch")
    if current is not None and upload.client_op_clock < current.op_clock:
        return {"status": "rejected"}
    next_clock = max(upload.client_op_clock, (current.op_clock + 1) if current else 1)
    content_hash = upload.content_hash or (
        upload.source_ref if upload.source == "local_file" else None
    )
    if current is None:
        current = MusicPlaylistItem(
            id=upload.id,
            user_uuid=user_uuid,
            playlist_id=upload.playlist_id,
            source=upload.source,
            source_ref=upload.source_ref,
            title=upload.title,
            artist=upload.artist,
            duration_ms=upload.duration_ms,
            cover_url=upload.cover_url,
            position=upload.position,
            added_at_ms=upload.added_at_ms,
            updated_at_ms=upload.updated_at_ms,
            deleted_at_ms=upload.deleted_at_ms,
            op_clock=next_clock,
            device_id=upload.device_id,
            content_hash=content_hash,
            size_bytes=upload.size_bytes,
            mime=upload.mime,
        )
        session.add(current)
    else:
        current.playlist_id = upload.playlist_id
        current.source = upload.source
        current.source_ref = upload.source_ref
        current.title = upload.title
        current.artist = upload.artist
        current.duration_ms = upload.duration_ms
        current.cover_url = upload.cover_url
        current.position = upload.position
        current.added_at_ms = upload.added_at_ms
        current.updated_at_ms = upload.updated_at_ms
        current.deleted_at_ms = upload.deleted_at_ms
        current.op_clock = next_clock
        current.device_id = upload.device_id
        current.content_hash = content_hash
        current.size_bytes = upload.size_bytes
        current.mime = upload.mime
    await session.flush()
    return {"status": "accepted", "op_clock": next_clock}


async def _list_changes(
    session: AsyncSession, *, user_uuid: str, since_clock: int, limit: int
) -> list[MusicPlaylistItem]:
    result = await session.execute(
        select(MusicPlaylistItem)
        .where(MusicPlaylistItem.user_uuid == user_uuid, MusicPlaylistItem.op_clock > since_clock)
        .order_by(MusicPlaylistItem.op_clock.asc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def _ensure_local_import_owner(
    session: AsyncSession, *, user_uuid: str, content_hash: str
) -> None:
    owner = (
        await session.execute(
            select(LocalImportOwner).where(
                LocalImportOwner.hash == content_hash,
                LocalImportOwner.user_uuid == user_uuid,
            )
        )
    ).scalar_one_or_none()
    if owner is None:
        raise AppError.bad_request(
            "local_import_owner_required",
            "local import hash must be uploaded by current user before playlist sync",
            "content_hash",
        )


def _validate_upload(upload: PlaylistUpload) -> None:
    _validate_required(upload.id, "id")
    _validate_required(upload.source_ref, "source_ref")
    _validate_required(upload.device_id, "device_id")
    if upload.source not in VALID_SOURCES:
        raise AppError.bad_request(
            "invalid_source",
            "source must be one of: remote_song, local_file, external_url",
            "source",
        )
    if upload.client_op_clock < 0:
        raise AppError.bad_request(
            "invalid_client_op_clock", "client_op_clock must be >= 0", "client_op_clock"
        )
    if upload.source != "local_file" and upload.content_hash:
        _validate_hash(upload.content_hash, "content_hash")


def _validate_hash(value: str | None, field: str) -> None:
    if not value or not SHA256_HEX_RE.fullmatch(value):
        raise AppError.bad_request(
            "invalid_content_hash", "content_hash must be 64-char lowercase sha256", field
        )


def _validate_required(value: str, field: str) -> None:
    if not value.strip():
        raise AppError.bad_request(f"{field}_required", f"{field} must not be empty", field)


def _playlist_item_response(item: MusicPlaylistItem) -> dict:
    return {
        "id": item.id,
        "playlist_id": item.playlist_id,
        "source": item.source,
        "source_ref": item.source_ref,
        "title": item.title,
        "artist": item.artist,
        "duration_ms": item.duration_ms,
        "cover_url": item.cover_url,
        "position": item.position,
        "added_at_ms": item.added_at_ms,
        "updated_at_ms": item.updated_at_ms,
        "deleted_at_ms": item.deleted_at_ms,
        "op_clock": item.op_clock,
        "device_id": item.device_id,
        "content_hash": item.content_hash,
        "size_bytes": item.size_bytes,
        "mime": item.mime,
    }


def _meta_song_response(song: MetaSong) -> dict:
    return {
        "content_hash": song.content_hash,
        "size_bytes": song.size_bytes,
        "mime": song.mime,
        "file_format": song.file_format,
        "duration_ms": song.duration_ms,
        "sample_rate_hz": song.sample_rate_hz,
        "bit_rate_bps": song.bit_rate_bps,
        "channels": song.channels,
        "codec_name": song.codec_name,
        "codec_profile": song.codec_profile,
        "container_format": song.container_format,
        "extracted_at_ms": song.extracted_at_ms,
        "extractor_name": song.extractor_name,
        "extractor_version": song.extractor_version,
        "created_at_ms": song.created_at_ms,
        "updated_at_ms": song.updated_at_ms,
    }


def _new_i64_id() -> int:
    return time.time_ns()
