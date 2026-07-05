from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..domains import music as music_domain
from .dependencies import CurrentUser, DbSession

router = APIRouter(prefix="/music", tags=["music"])


class PlaylistUploadRequest(BaseModel):
    id: str
    playlist_id: str = ""
    source: str
    source_ref: str
    title: str | None = None
    artist: str | None = None
    duration_ms: int | None = None
    cover_url: str | None = None
    position: float
    added_at_ms: int
    updated_at_ms: int
    deleted_at_ms: int | None = None
    client_op_clock: int
    device_id: str
    content_hash: str | None = None
    size_bytes: int | None = None
    mime: str | None = None


class PlaylistSyncRequest(BaseModel):
    uploads: list[PlaylistUploadRequest] = []


@router.post("/playlist/sync")
async def sync_playlist(
    req: PlaylistSyncRequest,
    user: CurrentUser,
    session: DbSession,
    since: int = 0,
    limit: int = 500,
) -> dict:
    response = await music_domain.sync_playlist(
        session,
        user_uuid=user.user_uuid,
        since_clock=since,
        limit=max(1, min(limit, 2000)),
        uploads=[
            music_domain.PlaylistUpload(
                id=item.id,
                playlist_id=item.playlist_id,
                source=item.source,
                source_ref=item.source_ref,
                title=item.title,
                artist=item.artist,
                duration_ms=item.duration_ms,
                cover_url=item.cover_url,
                position=item.position,
                added_at_ms=item.added_at_ms,
                updated_at_ms=item.updated_at_ms,
                deleted_at_ms=item.deleted_at_ms,
                client_op_clock=item.client_op_clock,
                device_id=item.device_id,
                content_hash=item.content_hash,
                size_bytes=item.size_bytes,
                mime=item.mime,
            )
            for item in req.uploads
        ],
    )
    await session.commit()
    return response


@router.post("/upload")
async def upload_song(
    user: CurrentUser,
    session: DbSession,
    file: Annotated[UploadFile, File()],
) -> dict:
    content = await file.read()
    response = await music_domain.store_song_upload(
        session,
        user_uuid=user.user_uuid,
        filename=file.filename or "audio.bin",
        mime=file.content_type or "application/octet-stream",
        content=content,
    )
    await session.commit()
    return response


@router.post("/local_import/upload")
async def upload_local_import(
    user: CurrentUser,
    session: DbSession,
    file: Annotated[UploadFile, File()],
) -> dict:
    content = await file.read()
    response = await music_domain.store_local_import(
        session,
        user_uuid=user.user_uuid,
        filename=file.filename or "audio.bin",
        mime=file.content_type or "application/octet-stream",
        content=content,
    )
    await session.commit()
    return response


@router.get("/file/{content_hash}")
async def serve_song_file(
    content_hash: str,
    user: CurrentUser,
    session: DbSession,
) -> FileResponse:
    path = await music_domain.local_import_path_for_user(
        session,
        user_uuid=user.user_uuid,
        content_hash=content_hash,
    )
    return FileResponse(path)


@router.get("/local_import/file/{content_hash}")
async def serve_local_import(
    content_hash: str,
    user: CurrentUser,
    session: DbSession,
) -> FileResponse:
    path = await music_domain.local_import_path_for_user(
        session,
        user_uuid=user.user_uuid,
        content_hash=content_hash,
    )
    return FileResponse(path)
