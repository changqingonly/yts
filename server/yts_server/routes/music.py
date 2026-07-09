from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..domains import music as music_domain
from ..domains import playlists as playlists_domain
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


class PlaylistDefaultRequest(BaseModel):
    scope: str = "cloud"


class PlaylistCreateRequest(BaseModel):
    name: str
    scope: str = "cloud"


class PlaylistItemAppendRequestItem(BaseModel):
    content_hash: str
    title_alias: str
    artist_alias: str | None = None
    device_id: str


class PlaylistItemAppendRequest(BaseModel):
    items: list[PlaylistItemAppendRequestItem]


class PlaylistReorderRequest(BaseModel):
    ordered_item_ids: list[str]


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


@router.post("/playlists/default")
async def default_playlist(
    req: PlaylistDefaultRequest, user: CurrentUser, session: DbSession
) -> dict:
    playlist = await playlists_domain.ensure_default_playlist(
        session, user_uuid=user.user_uuid, scope=req.scope
    )
    await session.commit()
    response = playlists_domain.playlist_response(playlist)
    return {"playlist": response, **response}


@router.get("/playlists")
async def playlists(user: CurrentUser, session: DbSession, scope: str | None = None) -> dict:
    rows = await playlists_domain.list_playlists(session, user_uuid=user.user_uuid, scope=scope)
    return {"playlists": [playlists_domain.playlist_response(item) for item in rows]}


@router.post("/playlists")
async def create_playlist(
    req: PlaylistCreateRequest, user: CurrentUser, session: DbSession
) -> dict:
    playlist = await playlists_domain.create_playlist(
        session, user_uuid=user.user_uuid, scope=req.scope, name=req.name
    )
    await session.commit()
    return playlists_domain.playlist_response(playlist)


@router.get("/playlists/{playlist_id}/items")
async def playlist_items(playlist_id: str, user: CurrentUser, session: DbSession) -> dict:
    playlist, items = await playlists_domain.list_playlist_items(
        session, user_uuid=user.user_uuid, playlist_id=playlist_id
    )
    return await playlists_domain.playlist_items_response(session, playlist=playlist, items=items)


@router.get("/playlists/{playlist_id}/items/deleted")
async def deleted_playlist_items(playlist_id: str, user: CurrentUser, session: DbSession) -> dict:
    playlist, items = await playlists_domain.list_deleted_playlist_items(
        session, user_uuid=user.user_uuid, playlist_id=playlist_id
    )
    return await playlists_domain.playlist_items_response(session, playlist=playlist, items=items)


@router.post("/playlists/{playlist_id}/items")
async def append_playlist_items(
    playlist_id: str,
    req: PlaylistItemAppendRequest,
    user: CurrentUser,
    session: DbSession,
) -> dict:
    playlist, items = await playlists_domain.append_playlist_items(
        session,
        user_uuid=user.user_uuid,
        playlist_id=playlist_id,
        items=[
            playlists_domain.PlaylistItemInput(
                content_hash=item.content_hash,
                title_alias=item.title_alias,
                artist_alias=item.artist_alias,
                device_id=item.device_id,
            )
            for item in req.items
        ],
    )
    await session.commit()
    return await playlists_domain.playlist_items_response(session, playlist=playlist, items=items)


@router.delete("/playlists/{playlist_id}/items/{item_id}")
async def delete_playlist_item(
    playlist_id: str,
    item_id: str,
    user: CurrentUser,
    session: DbSession,
) -> dict:
    playlist, item, active_items = await playlists_domain.delete_playlist_item(
        session,
        user_uuid=user.user_uuid,
        playlist_id=playlist_id,
        item_id=item_id,
    )
    await session.commit()
    item_response = await playlists_domain.playlist_items_response(
        session, playlist=playlist, items=[item]
    )
    active_response = await playlists_domain.playlist_items_response(
        session, playlist=playlist, items=active_items
    )
    return {
        "playlist": active_response["playlist"],
        "item": item_response["items"][0],
        "items": active_response["items"],
    }


@router.post("/playlists/{playlist_id}/items/{item_id}/restore")
async def restore_playlist_item(
    playlist_id: str,
    item_id: str,
    user: CurrentUser,
    session: DbSession,
) -> dict:
    playlist, item, active_items = await playlists_domain.restore_playlist_item(
        session,
        user_uuid=user.user_uuid,
        playlist_id=playlist_id,
        item_id=item_id,
    )
    await session.commit()
    item_response = await playlists_domain.playlist_items_response(
        session, playlist=playlist, items=[item]
    )
    active_response = await playlists_domain.playlist_items_response(
        session, playlist=playlist, items=active_items
    )
    return {
        "playlist": active_response["playlist"],
        "item": item_response["items"][0],
        "items": active_response["items"],
    }


@router.post("/playlists/{playlist_id}/items/reorder")
async def reorder_playlist_items(
    playlist_id: str,
    req: PlaylistReorderRequest,
    user: CurrentUser,
    session: DbSession,
) -> dict:
    playlist, items = await playlists_domain.reorder_playlist_items(
        session,
        user_uuid=user.user_uuid,
        playlist_id=playlist_id,
        ordered_item_ids=req.ordered_item_ids,
    )
    await session.commit()
    return await playlists_domain.playlist_items_response(session, playlist=playlist, items=items)


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
