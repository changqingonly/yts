from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import (
    AudioPlaybackRendition,
    LocalImportOwner,
    MetaSong,
    MusicPlaylist,
    MusicPlaylistItem,
)
from ..errors import AppError
from .audio_renditions import PLAYBACK_PROFILE

MAX_PLAYLIST_ITEMS = 2000
VALID_SCOPES = {"cloud", "local"}


@dataclass(frozen=True)
class PlaylistItemInput:
    content_hash: str
    title_alias: str
    artist_alias: str | None
    device_id: str


async def ensure_default_playlist(
    session: AsyncSession, *, user_uuid: str, scope: str
) -> MusicPlaylist:
    _validate_scope(scope)
    playlist = (
        await session.execute(
            select(MusicPlaylist).where(
                MusicPlaylist.user_uuid == user_uuid,
                MusicPlaylist.scope == scope,
                MusicPlaylist.is_default.is_(True),
                MusicPlaylist.deleted_at_ms.is_(None),
            )
        )
    ).scalar_one_or_none()
    if playlist is not None:
        return playlist
    now_ms = _now_ms()
    playlist = MusicPlaylist(
        id=_new_id("playlist"),
        user_uuid=user_uuid,
        name="默认歌单",
        scope=scope,
        is_default=True,
        item_count=0,
        created_at_ms=now_ms,
        updated_at_ms=now_ms,
        deleted_at_ms=None,
        op_clock=1,
    )
    session.add(playlist)
    await session.flush()
    return playlist


async def list_playlists(
    session: AsyncSession, *, user_uuid: str, scope: str | None
) -> list[MusicPlaylist]:
    if scope is not None:
        _validate_scope(scope)
    query = select(MusicPlaylist).where(
        MusicPlaylist.user_uuid == user_uuid,
        MusicPlaylist.deleted_at_ms.is_(None),
    )
    if scope is not None:
        query = query.where(MusicPlaylist.scope == scope)
    result = await session.execute(
        query.order_by(desc(MusicPlaylist.is_default), desc(MusicPlaylist.updated_at_ms))
    )
    return list(result.scalars().all())


async def create_playlist(
    session: AsyncSession, *, user_uuid: str, scope: str, name: str
) -> MusicPlaylist:
    _validate_scope(scope)
    if not name.strip():
        raise AppError.bad_request(
            "playlist_name_required", "playlist name must not be empty", "name"
        )
    now_ms = _now_ms()
    playlist = MusicPlaylist(
        id=_new_id("playlist"),
        user_uuid=user_uuid,
        name=name.strip(),
        scope=scope,
        is_default=False,
        item_count=0,
        created_at_ms=now_ms,
        updated_at_ms=now_ms,
        deleted_at_ms=None,
        op_clock=1,
    )
    session.add(playlist)
    await session.flush()
    return playlist


async def list_playlist_items(
    session: AsyncSession, *, user_uuid: str, playlist_id: str
) -> tuple[MusicPlaylist, list[MusicPlaylistItem]]:
    playlist = await _owned_playlist(session, user_uuid=user_uuid, playlist_id=playlist_id)
    return playlist, await _active_items(session, playlist_id=playlist.id)


async def list_deleted_playlist_items(
    session: AsyncSession, *, user_uuid: str, playlist_id: str
) -> tuple[MusicPlaylist, list[MusicPlaylistItem]]:
    playlist = await _owned_playlist(session, user_uuid=user_uuid, playlist_id=playlist_id)
    return playlist, await _deleted_items(session, playlist_id=playlist.id)


async def append_playlist_items(
    session: AsyncSession,
    *,
    user_uuid: str,
    playlist_id: str,
    items: list[PlaylistItemInput],
) -> tuple[MusicPlaylist, list[MusicPlaylistItem]]:
    if not items:
        raise AppError.bad_request("playlist_items_required", "items must not be empty", "items")
    playlist = await _owned_playlist(session, user_uuid=user_uuid, playlist_id=playlist_id)
    active_count = await _active_item_count(session, playlist_id=playlist.id)
    if active_count + len(items) > MAX_PLAYLIST_ITEMS:
        raise AppError.bad_request(
            "playlist_item_limit_exceeded",
            "playlist item limit is 2000",
            "items",
        )
    for item in items:
        await _require_meta_song_and_owner(
            session, user_uuid=user_uuid, content_hash=item.content_hash
        )

    start_position = await _current_max_position(session, playlist_id=playlist.id)
    now_ms = _now_ms()
    created: list[MusicPlaylistItem] = []
    for index, item in enumerate(items, start=1):
        row = MusicPlaylistItem(
            id=_new_id("playlist_item"),
            user_uuid=user_uuid,
            playlist_id=playlist.id,
            content_hash=item.content_hash,
            title_alias=item.title_alias,
            artist_alias=item.artist_alias,
            position=start_position + index,
            added_at_ms=now_ms,
            updated_at_ms=now_ms,
            deleted_at_ms=None,
            op_clock=playlist.op_clock + index,
            device_id=item.device_id,
            source="local_file",
            source_ref=item.content_hash,
            title=None,
            artist=None,
            duration_ms=None,
            cover_url=None,
            size_bytes=None,
            mime=None,
        )
        session.add(row)
        created.append(row)
    playlist.item_count = active_count + len(created)
    playlist.updated_at_ms = now_ms
    playlist.op_clock += len(created)
    await session.flush()
    return playlist, created


async def reorder_playlist_items(
    session: AsyncSession,
    *,
    user_uuid: str,
    playlist_id: str,
    ordered_item_ids: list[str],
) -> tuple[MusicPlaylist, list[MusicPlaylistItem]]:
    playlist = await _owned_playlist(session, user_uuid=user_uuid, playlist_id=playlist_id)
    items = await _active_items(session, playlist_id=playlist.id)
    existing_ids = [item.id for item in items]
    if len(ordered_item_ids) != len(existing_ids) or set(ordered_item_ids) != set(existing_ids):
        raise AppError.bad_request(
            "invalid_reorder_items",
            "ordered_item_ids must contain every active playlist item exactly once",
            "ordered_item_ids",
        )
    by_id = {item.id: item for item in items}
    now_ms = _now_ms()
    ordered: list[MusicPlaylistItem] = []
    for position, item_id in enumerate(ordered_item_ids, start=1):
        item = by_id[item_id]
        item.position = position
        item.updated_at_ms = now_ms
        item.op_clock = playlist.op_clock + position
        ordered.append(item)
    playlist.updated_at_ms = now_ms
    playlist.op_clock += len(ordered)
    await session.flush()
    return playlist, ordered


async def delete_playlist_item(
    session: AsyncSession,
    *,
    user_uuid: str,
    playlist_id: str,
    item_id: str,
) -> tuple[MusicPlaylist, MusicPlaylistItem, list[MusicPlaylistItem]]:
    playlist = await _owned_playlist(session, user_uuid=user_uuid, playlist_id=playlist_id)
    item = await _owned_playlist_item(
        session, user_uuid=user_uuid, playlist_id=playlist.id, item_id=item_id
    )
    if item.deleted_at_ms is not None:
        raise AppError.bad_request(
            "playlist_item_already_deleted", "playlist item is already deleted"
        )
    now_ms = _now_ms()
    item.deleted_at_ms = now_ms
    item.updated_at_ms = now_ms
    item.op_clock = playlist.op_clock + 1
    active_items = await _active_items(session, playlist_id=playlist.id)
    for position, active_item in enumerate(active_items, start=1):
        if active_item.position == position:
            continue
        active_item.position = position
        active_item.updated_at_ms = now_ms
        active_item.op_clock = playlist.op_clock + 1 + position
    playlist.item_count = len(active_items)
    playlist.updated_at_ms = now_ms
    playlist.op_clock += 1 + len(active_items)
    await session.flush()
    return playlist, item, active_items


async def restore_playlist_item(
    session: AsyncSession,
    *,
    user_uuid: str,
    playlist_id: str,
    item_id: str,
) -> tuple[MusicPlaylist, MusicPlaylistItem, list[MusicPlaylistItem]]:
    playlist = await _owned_playlist(session, user_uuid=user_uuid, playlist_id=playlist_id)
    item = await _owned_playlist_item(
        session, user_uuid=user_uuid, playlist_id=playlist.id, item_id=item_id
    )
    if item.deleted_at_ms is None:
        raise AppError.bad_request("playlist_item_not_deleted", "playlist item is not deleted")
    active_count = await _active_item_count(session, playlist_id=playlist.id)
    if active_count + 1 > MAX_PLAYLIST_ITEMS:
        raise AppError.bad_request(
            "playlist_item_limit_exceeded",
            "playlist item limit is 2000",
            "item_id",
        )
    now_ms = _now_ms()
    item.deleted_at_ms = None
    item.position = await _current_max_position(session, playlist_id=playlist.id) + 1
    item.updated_at_ms = now_ms
    item.op_clock = playlist.op_clock + 1
    playlist.item_count = active_count + 1
    playlist.updated_at_ms = now_ms
    playlist.op_clock += 1
    await session.flush()
    restored_items = await _active_items(session, playlist_id=playlist.id)
    return playlist, item, restored_items


def playlist_response(playlist: MusicPlaylist) -> dict:
    return {
        "id": playlist.id,
        "user_uuid": playlist.user_uuid,
        "name": playlist.name,
        "scope": playlist.scope,
        "is_default": playlist.is_default,
        "item_count": playlist.item_count,
        "created_at_ms": playlist.created_at_ms,
        "updated_at_ms": playlist.updated_at_ms,
        "deleted_at_ms": playlist.deleted_at_ms,
        "op_clock": playlist.op_clock,
    }


async def playlist_items_response(
    session: AsyncSession, *, playlist: MusicPlaylist, items: list[MusicPlaylistItem]
) -> dict:
    meta_songs = await _meta_songs_by_hash(
        session, content_hashes=[item.content_hash for item in items if item.content_hash]
    )
    renditions = await _renditions_by_hash(
        session, content_hashes=[item.content_hash for item in items if item.content_hash]
    )
    return {
        "playlist": playlist_response(playlist),
        "items": [_playlist_item_response(item, meta_songs, renditions) for item in items],
    }


async def _owned_playlist(
    session: AsyncSession, *, user_uuid: str, playlist_id: str
) -> MusicPlaylist:
    playlist = await session.get(MusicPlaylist, playlist_id)
    if playlist is None or playlist.deleted_at_ms is not None:
        raise AppError.not_found("playlist_not_found", "playlist not found")
    if playlist.user_uuid != user_uuid:
        raise AppError.forbidden("playlist owner mismatch")
    return playlist


async def _owned_playlist_item(
    session: AsyncSession, *, user_uuid: str, playlist_id: str, item_id: str
) -> MusicPlaylistItem:
    item = await session.get(MusicPlaylistItem, item_id)
    if item is None or item.playlist_id != playlist_id:
        raise AppError.not_found("playlist_item_not_found", "playlist item not found")
    if item.user_uuid != user_uuid:
        raise AppError.forbidden("playlist item owner mismatch")
    return item


async def _active_items(session: AsyncSession, *, playlist_id: str) -> list[MusicPlaylistItem]:
    result = await session.execute(
        select(MusicPlaylistItem)
        .where(
            MusicPlaylistItem.playlist_id == playlist_id,
            MusicPlaylistItem.deleted_at_ms.is_(None),
        )
        .order_by(MusicPlaylistItem.position.asc(), MusicPlaylistItem.added_at_ms.asc())
    )
    return list(result.scalars().all())


async def _deleted_items(session: AsyncSession, *, playlist_id: str) -> list[MusicPlaylistItem]:
    result = await session.execute(
        select(MusicPlaylistItem)
        .where(
            MusicPlaylistItem.playlist_id == playlist_id,
            MusicPlaylistItem.deleted_at_ms.is_not(None),
        )
        .order_by(
            MusicPlaylistItem.deleted_at_ms.desc(), MusicPlaylistItem.updated_at_ms.desc()
        )
    )
    return list(result.scalars().all())


async def _active_item_count(session: AsyncSession, *, playlist_id: str) -> int:
    count = (
        await session.execute(
            select(func.count(MusicPlaylistItem.id)).where(
                MusicPlaylistItem.playlist_id == playlist_id,
                MusicPlaylistItem.deleted_at_ms.is_(None),
            )
        )
    ).scalar_one()
    return int(count)


async def _current_max_position(session: AsyncSession, *, playlist_id: str) -> int:
    value = (
        await session.execute(
            select(func.max(MusicPlaylistItem.position)).where(
                MusicPlaylistItem.playlist_id == playlist_id,
                MusicPlaylistItem.deleted_at_ms.is_(None),
            )
        )
    ).scalar_one()
    if value is None:
        return 0
    return int(value)


async def _require_meta_song_and_owner(
    session: AsyncSession, *, user_uuid: str, content_hash: str
) -> None:
    meta_song = await session.get(MetaSong, content_hash)
    if meta_song is None:
        raise AppError.bad_request(
            "meta_song_required",
            "content_hash must reference an existing meta_song",
            "content_hash",
        )
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
            "song_owner_required",
            "current user must upload song before adding it to playlist",
            "content_hash",
        )


async def _meta_songs_by_hash(
    session: AsyncSession, *, content_hashes: list[str]
) -> dict[str, MetaSong]:
    if not content_hashes:
        return {}
    result = await session.execute(
        select(MetaSong).where(MetaSong.content_hash.in_(set(content_hashes)))
    )
    return {song.content_hash: song for song in result.scalars().all()}


async def _renditions_by_hash(
    session: AsyncSession, *, content_hashes: list[str]
) -> dict[str, AudioPlaybackRendition]:
    if not content_hashes:
        return {}
    result = await session.execute(
        select(AudioPlaybackRendition).where(
            AudioPlaybackRendition.original_content_hash.in_(set(content_hashes)),
            AudioPlaybackRendition.profile == PLAYBACK_PROFILE,
        )
    )
    return {rendition.original_content_hash: rendition for rendition in result.scalars().all()}


def _playlist_item_response(
    item: MusicPlaylistItem,
    meta_songs: dict[str, MetaSong],
    renditions: dict[str, AudioPlaybackRendition],
) -> dict:
    if item.content_hash is None:
        raise AppError.bad_request(
            "meta_song_required",
            "playlist item must reference meta_song",
            "content_hash",
        )
    meta_song = meta_songs.get(item.content_hash)
    if meta_song is None:
        raise AppError.bad_request(
            "meta_song_required",
            "content_hash must reference an existing meta_song",
            "content_hash",
        )
    rendition = renditions.get(item.content_hash)
    if rendition is None:
        raise AppError.not_found(
            "playback_rendition_missing",
            "playlist item playback rendition does not exist",
        )
    return {
        "id": item.id,
        "user_uuid": item.user_uuid,
        "playlist_id": item.playlist_id,
        "content_hash": item.content_hash,
        "title_alias": item.title_alias,
        "artist_alias": item.artist_alias,
        "position": item.position,
        "added_at_ms": item.added_at_ms,
        "updated_at_ms": item.updated_at_ms,
        "deleted_at_ms": item.deleted_at_ms,
        "op_clock": item.op_clock,
        "device_id": item.device_id,
        "meta_song": _meta_song_response(meta_song),
        "playback_status": rendition.status,
        "rendition_profile": rendition.profile,
        "playback_error_code": rendition.error_code,
        "playback_error_message": rendition.error_message,
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


def _validate_scope(scope: str) -> None:
    if scope not in VALID_SCOPES:
        raise AppError.bad_request(
            "invalid_playlist_scope", "scope must be cloud or local", "scope"
        )


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _now_ms() -> int:
    return time.time_ns() // 1_000_000
