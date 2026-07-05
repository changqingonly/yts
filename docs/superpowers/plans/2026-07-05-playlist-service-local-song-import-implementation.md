# Playlist Service Local Song Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the server-side playlist service, public `meta_song` model, and music import drawer so local song uploads become ordered playlist items with objective audio metadata.

**Architecture:** The backend is split into two domains: `music.py` owns file upload, content hashing, owner records, `meta_song`, and file serving; `playlists.py` owns user playlists, playlist item aliases, ordering, and the 2000 item limit. The frontend uses new music service APIs through the playlist Pinia store; `MusicPage.vue` stays focused on player composition and delegates import state to `MusicImportDrawer.vue`.

**Tech Stack:** FastAPI, SQLAlchemy async, SQLite/PostgreSQL-compatible models, Pydantic request models, Pinia, Vue 3, Vite, pytest, static frontend source tests.

---

## File Structure

**Backend**

- Modify `server/pyproject.toml`: add `mutagen>=1.47` for Python audio metadata extraction.
- Modify `server/yts_server/db/models.py`: add `MetaSong`; extend `MusicPlaylist`; reshape `MusicPlaylistItem` into an alias of `MetaSong`; keep `LocalImportBlob`/`LocalImportOwner` as storage and ownership tables.
- Create `server/yts_server/domains/audio_metadata.py`: parse audio metadata from a stored file and return a strict value object.
- Modify `server/yts_server/domains/music.py`: replace local import upload with `store_song_upload`; create or reuse `MetaSong`; expose file path lookup by `content_hash`.
- Create `server/yts_server/domains/playlists.py`: default playlist, list/create playlist, append items with continuous position, reorder items, and enforce owner and 2000 limit.
- Modify `server/yts_server/routes/music.py`: add `/music/upload`, `/music/file/{content_hash}`, playlist list/default/create/items/reorder endpoints; keep `/music/local_import/file/{content_hash}` as an explicit compatibility alias to the same file-serving service.
- Modify `tests/test_music_routes.py`: replace sync-based tests with upload/meta-song/playlist tests.

**Frontend**

- Modify `desktop/frontend/src/services/music.js`: replace sync/upload helpers with playlist and upload helpers.
- Modify `desktop/frontend/src/stores/playlist.js`: manage playlists, current playlist, joined playlist items, and import append behavior.
- Create `desktop/frontend/src/components/MusicImportDrawer.vue`: import drawer UI and per-file state machine.
- Modify `desktop/frontend/src/pages/MusicPage.vue`: open import drawer from the right-side import icon; map playlist items to player tracks through `content_hash`.
- Modify `tests/test_frontend_creator_os_layout.py`: assert import drawer wiring, target warning, playlist capacity copy, and source API helpers.

---

## Task 1: Backend Models And Audio Metadata Extraction

**Files:**
- Modify: `server/pyproject.toml`
- Modify: `server/yts_server/db/models.py`
- Create: `server/yts_server/domains/audio_metadata.py`
- Test: `tests/test_music_routes.py`

- [ ] **Step 1: Write failing metadata upload test**

Add this helper and test to `tests/test_music_routes.py`:

```python
import io
import wave


def wav_bytes(duration_seconds: float = 0.25, sample_rate: int = 8000) -> bytes:
    buffer = io.BytesIO()
    frame_count = int(duration_seconds * sample_rate)
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"\x00\x00" * frame_count)
    return buffer.getvalue()


def test_upload_song_extracts_meta_song_and_reuses_content_hash() -> None:
    audio_bytes = wav_bytes()
    expected_hash = hashlib.sha256(audio_bytes).hexdigest()

    with TestClient(create_app()) as client:
        token = register_via_test_crypto(client, "meta@example.com", "Password123")[
            "access_token"
        ]
        headers = {"Authorization": f"Bearer {token}"}

        first = client.post(
            "/api/music/upload",
            headers=headers,
            files={"file": ("rain.wav", audio_bytes, "audio/wav")},
        )
        assert first.status_code == 200, first.text
        body = first.json()
        assert body["content_hash"] == expected_hash
        assert body["filename"] == "rain.wav"
        assert body["size_bytes"] == len(audio_bytes)
        assert body["deduplicated"] is False
        assert body["meta_song"]["content_hash"] == expected_hash
        assert body["meta_song"]["file_format"] == "wav"
        assert body["meta_song"]["duration_ms"] in range(200, 350)
        assert body["meta_song"]["sample_rate_hz"] == 8000
        assert body["meta_song"]["channels"] == 1
        assert body["meta_song"]["codec_name"] == "pcm_s16le"

        second = client.post(
            "/api/music/upload",
            headers=headers,
            files={"file": ("rain-copy.wav", audio_bytes, "audio/wav")},
        )
        assert second.status_code == 200, second.text
        assert second.json()["content_hash"] == expected_hash
        assert second.json()["deduplicated"] is True
        assert second.json()["meta_song"] == body["meta_song"]
```

- [ ] **Step 2: Run the focused failing test**

Run:

```bash
.venv/bin/python -m pytest tests/test_music_routes.py::test_upload_song_extracts_meta_song_and_reuses_content_hash -q
```

Expected: fail with `404 Not Found` for `/api/music/upload` or missing `meta_song`.

- [ ] **Step 3: Add audio dependency**

Modify `server/pyproject.toml` dependencies:

```toml
"mutagen>=1.47",
```

Place it with the other runtime server dependencies.

- [ ] **Step 4: Add `MetaSong` and reshape playlist models**

Modify `server/yts_server/db/models.py`:

```python
class MetaSong(Base):
    __tablename__ = "meta_song"

    content_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    mime: Mapped[str] = mapped_column(String(128))
    file_format: Mapped[str] = mapped_column(String(32))
    duration_ms: Mapped[int] = mapped_column(Integer)
    sample_rate_hz: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bit_rate_bps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    channels: Mapped[int | None] = mapped_column(Integer, nullable=True)
    codec_name: Mapped[str] = mapped_column(String(128))
    codec_profile: Mapped[str | None] = mapped_column(String(128), nullable=True)
    container_format: Mapped[str | None] = mapped_column(String(128), nullable=True)
    extracted_at_ms: Mapped[int] = mapped_column(BigInteger)
    extractor_name: Mapped[str] = mapped_column(String(64))
    extractor_version: Mapped[str] = mapped_column(String(64))
    created_at_ms: Mapped[int] = mapped_column(BigInteger)
    updated_at_ms: Mapped[int] = mapped_column(BigInteger)
```

Extend `MusicPlaylist` with `scope`, `is_default`, `item_count`, `created_at_ms`, `deleted_at_ms`, and `op_clock`. Update `MusicPlaylistItem` so it has `content_hash`, `title_alias`, `artist_alias`, integer `position`, `added_at_ms`, `updated_at_ms`, `deleted_at_ms`, `op_clock`, and `device_id`. Keep existing `source`, `source_ref`, `title`, `artist`, `duration_ms`, `cover_url`, `size_bytes`, and `mime` columns as nullable legacy columns so the old `/playlist/sync` route can compile during migration; new playlist service code must not read or write those legacy columns.

- [ ] **Step 5: Create strict audio metadata extractor**

Create `server/yts_server/domains/audio_metadata.py`:

```python
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
```

- [ ] **Step 6: Run the focused test again**

Run:

```bash
.venv/bin/python -m pytest tests/test_music_routes.py::test_upload_song_extracts_meta_song_and_reuses_content_hash -q
```

Expected: still fail because `/api/music/upload` is not implemented.

- [ ] **Step 7: Commit model and extractor groundwork**

```bash
git add server/pyproject.toml server/yts_server/db/models.py server/yts_server/domains/audio_metadata.py tests/test_music_routes.py
git commit -m "feat: add meta song audio metadata model"
```

---

## Task 2: Song Upload Domain And Upload API

**Files:**
- Modify: `server/yts_server/domains/music.py`
- Modify: `server/yts_server/routes/music.py`
- Test: `tests/test_music_routes.py`

- [ ] **Step 1: Implement `store_song_upload` test expectations**

Keep the Task 1 test as the failing route contract. Add this second test:

```python
def test_upload_song_rejects_empty_file() -> None:
    with TestClient(create_app()) as client:
        token = register_via_test_crypto(client, "empty-song@example.com", "Password123")[
            "access_token"
        ]
        response = client.post(
            "/api/music/upload",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("empty.wav", b"", "audio/wav")},
        )
        assert response.status_code == 400
        assert response.json()["code"] == "empty_file"
```

- [ ] **Step 2: Run upload route tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_music_routes.py::test_upload_song_extracts_meta_song_and_reuses_content_hash tests/test_music_routes.py::test_upload_song_rejects_empty_file -q
```

Expected: fail because the route is not implemented.

- [ ] **Step 3: Implement upload domain**

In `server/yts_server/domains/music.py`, add `store_song_upload` and `serve_song_file_path` while reusing existing hash validation and owner checks:

```python
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
```

Add `_ensure_owner_row` so repeated uploads by the same user do not create duplicate owner rows:

```python
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
```

- [ ] **Step 4: Add upload route**

In `server/yts_server/routes/music.py`, add:

```python
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
```

Add:

```python
@router.get("/file/{content_hash}")
async def serve_song_file(content_hash: str, user: CurrentUser, session: DbSession) -> FileResponse:
    path = await music_domain.local_import_path_for_user(
        session,
        user_uuid=user.user_uuid,
        content_hash=content_hash,
    )
    return FileResponse(path)
```

Keep `/local_import/file/{content_hash}` and route it through the same domain call so existing player URLs fail only when the user lacks owner access or the file is missing.

- [ ] **Step 5: Run upload tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_music_routes.py::test_upload_song_extracts_meta_song_and_reuses_content_hash tests/test_music_routes.py::test_upload_song_rejects_empty_file -q
```

Expected: pass.

- [ ] **Step 6: Commit upload API**

```bash
git add server/yts_server/domains/music.py server/yts_server/routes/music.py tests/test_music_routes.py
git commit -m "feat: add song upload meta extraction api"
```

---

## Task 3: Playlist Domain Service

**Files:**
- Create: `server/yts_server/domains/playlists.py`
- Modify: `server/yts_server/routes/music.py`
- Test: `tests/test_music_routes.py`

- [ ] **Step 1: Write playlist behavior tests**

Add tests to `tests/test_music_routes.py`:

```python
def test_default_playlist_append_allows_duplicate_content_hash_and_assigns_positions() -> None:
    audio_bytes = wav_bytes()
    expected_hash = hashlib.sha256(audio_bytes).hexdigest()

    with TestClient(create_app()) as client:
        token = register_via_test_crypto(client, "playlist@example.com", "Password123")[
            "access_token"
        ]
        headers = {"Authorization": f"Bearer {token}"}
        upload = client.post(
            "/api/music/upload",
            headers=headers,
            files={"file": ("rain.wav", audio_bytes, "audio/wav")},
        )
        assert upload.status_code == 200, upload.text

        default_playlist = client.post(
            "/api/music/playlists/default",
            headers=headers,
            json={"scope": "cloud"},
        )
        assert default_playlist.status_code == 200, default_playlist.text
        playlist_id = default_playlist.json()["id"]

        appended = client.post(
            f"/api/music/playlists/{playlist_id}/items",
            headers=headers,
            json={
                "items": [
                    {
                        "content_hash": expected_hash,
                        "title_alias": "雨声 A",
                        "artist_alias": "",
                        "device_id": "device-a",
                    },
                    {
                        "content_hash": expected_hash,
                        "title_alias": "雨声 B",
                        "artist_alias": "me",
                        "device_id": "device-a",
                    },
                ]
            },
        )
        assert appended.status_code == 200, appended.text
        items = appended.json()["items"]
        assert [item["position"] for item in items] == [1, 2]
        assert items[0]["content_hash"] == expected_hash
        assert items[1]["content_hash"] == expected_hash
        assert items[0]["title_alias"] == "雨声 A"
        assert items[0]["meta_song"]["content_hash"] == expected_hash

        listed = client.get(f"/api/music/playlists/{playlist_id}/items", headers=headers)
        assert listed.status_code == 200, listed.text
        assert [item["position"] for item in listed.json()["items"]] == [1, 2]
        assert listed.json()["playlist"]["item_count"] == 2
```

Add the reorder test:

```python
def test_reorder_playlist_items_rewrites_continuous_positions() -> None:
    audio_bytes = wav_bytes()
    with TestClient(create_app()) as client:
        token = register_via_test_crypto(client, "reorder@example.com", "Password123")[
            "access_token"
        ]
        headers = {"Authorization": f"Bearer {token}"}
        content_hash = client.post(
            "/api/music/upload",
            headers=headers,
            files={"file": ("rain.wav", audio_bytes, "audio/wav")},
        ).json()["content_hash"]
        playlist_id = client.post(
            "/api/music/playlists/default",
            headers=headers,
            json={"scope": "cloud"},
        ).json()["id"]
        appended = client.post(
            f"/api/music/playlists/{playlist_id}/items",
            headers=headers,
            json={
                "items": [
                    {"content_hash": content_hash, "title_alias": "一", "artist_alias": "", "device_id": "d"},
                    {"content_hash": content_hash, "title_alias": "二", "artist_alias": "", "device_id": "d"},
                    {"content_hash": content_hash, "title_alias": "三", "artist_alias": "", "device_id": "d"},
                ]
            },
        ).json()["items"]
        ordered_ids = [appended[2]["id"], appended[0]["id"], appended[1]["id"]]

        reordered = client.post(
            f"/api/music/playlists/{playlist_id}/items/reorder",
            headers=headers,
            json={"ordered_item_ids": ordered_ids},
        )
        assert reordered.status_code == 200, reordered.text
        assert [(item["id"], item["position"]) for item in reordered.json()["items"]] == [
            (ordered_ids[0], 1),
            (ordered_ids[1], 2),
            (ordered_ids[2], 3),
        ]
```

- [ ] **Step 2: Run playlist tests to verify failure**

Run:

```bash
.venv/bin/python -m pytest tests/test_music_routes.py::test_default_playlist_append_allows_duplicate_content_hash_and_assigns_positions tests/test_music_routes.py::test_reorder_playlist_items_rewrites_continuous_positions -q
```

Expected: fail because playlist endpoints are missing.

- [ ] **Step 3: Implement playlist domain**

Create `server/yts_server/domains/playlists.py` with:

```python
MAX_PLAYLIST_ITEMS = 2000
VALID_SCOPES = {"cloud", "local"}


@dataclass(frozen=True)
class PlaylistItemInput:
    content_hash: str
    title_alias: str
    artist_alias: str | None
    device_id: str
```

Implement these functions with the listed signatures and return values:

- `ensure_default_playlist(session: AsyncSession, *, user_uuid: str, scope: str) -> MusicPlaylist`: validate `scope`, query the active default playlist for `(user_uuid, scope)`, create `默认歌单` when missing, flush, and return it.
- `list_playlists(session: AsyncSession, *, user_uuid: str, scope: str | None) -> list[MusicPlaylist]`: validate `scope` when present, exclude rows with `deleted_at_ms`, order by `is_default desc, updated_at_ms desc`, and return the list.
- `create_playlist(session: AsyncSession, *, user_uuid: str, scope: str, name: str) -> MusicPlaylist`: reject blank `name`, create a non-default playlist, flush, and return it.
- `list_playlist_items(session: AsyncSession, *, user_uuid: str, playlist_id: str) -> tuple[MusicPlaylist, list[MusicPlaylistItem]]`: load the owned active playlist, load active items ordered by `position asc`, and return both.
- `append_playlist_items(session: AsyncSession, *, user_uuid: str, playlist_id: str, items: list[PlaylistItemInput]) -> tuple[MusicPlaylist, list[MusicPlaylistItem]]`: reject an empty `items` list, enforce `MAX_PLAYLIST_ITEMS`, validate `MetaSong` and `LocalImportOwner` for each item, allocate continuous positions after the current max position, update playlist `item_count`, flush, and return the created rows.
- `reorder_playlist_items(session: AsyncSession, *, user_uuid: str, playlist_id: str, ordered_item_ids: list[str]) -> tuple[MusicPlaylist, list[MusicPlaylistItem]]`: require `ordered_item_ids` to match all active item IDs exactly, rewrite positions from 1 to N in one transaction, update playlist `updated_at_ms`, flush, and return rows in the new order.

Use explicit failures:

```python
raise AppError.bad_request("playlist_item_limit_exceeded", "playlist item limit is 2000", "items")
raise AppError.bad_request("meta_song_required", "content_hash must reference an existing meta_song", "content_hash")
raise AppError.bad_request("song_owner_required", "current user must upload song before adding it to playlist", "content_hash")
raise AppError.bad_request("invalid_reorder_items", "ordered_item_ids must contain every active playlist item exactly once", "ordered_item_ids")
```

- [ ] **Step 4: Implement playlist routes**

In `server/yts_server/routes/music.py`, add Pydantic models:

```python
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
```

Add endpoints:

```python
@router.post("/playlists/default")
async def default_playlist(req: PlaylistDefaultRequest, user: CurrentUser, session: DbSession) -> dict:
    playlist = await playlists_domain.ensure_default_playlist(
        session, user_uuid=user.user_uuid, scope=req.scope
    )
    await session.commit()
    return {"playlist": playlists_domain.playlist_response(playlist), **playlists_domain.playlist_response(playlist)}


@router.get("/playlists")
async def playlists(user: CurrentUser, session: DbSession, scope: str | None = None) -> dict:
    rows = await playlists_domain.list_playlists(session, user_uuid=user.user_uuid, scope=scope)
    return {"playlists": [playlists_domain.playlist_response(item) for item in rows]}


@router.post("/playlists")
async def create_playlist(req: PlaylistCreateRequest, user: CurrentUser, session: DbSession) -> dict:
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
```

Each route commits after successful domain calls and returns joined `meta_song` data through response helpers in `playlists.py`.

- [ ] **Step 5: Run playlist tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_music_routes.py::test_default_playlist_append_allows_duplicate_content_hash_and_assigns_positions tests/test_music_routes.py::test_reorder_playlist_items_rewrites_continuous_positions -q
```

Expected: pass.

- [ ] **Step 6: Commit playlist service**

```bash
git add server/yts_server/domains/playlists.py server/yts_server/routes/music.py tests/test_music_routes.py
git commit -m "feat: add ordered playlist service"
```

---

## Task 4: Playlist Limit And Permission Tests

**Files:**
- Modify: `server/yts_server/domains/playlists.py`
- Modify: `tests/test_music_routes.py`

- [ ] **Step 1: Add limit and ownership tests**

Add:

```python
def test_playlist_append_rejects_when_item_limit_exceeded() -> None:
    audio_bytes = wav_bytes()
    with TestClient(create_app()) as client:
        token = register_via_test_crypto(client, "limit@example.com", "Password123")[
            "access_token"
        ]
        headers = {"Authorization": f"Bearer {token}"}
        content_hash = client.post(
            "/api/music/upload",
            headers=headers,
            files={"file": ("rain.wav", audio_bytes, "audio/wav")},
        ).json()["content_hash"]
        playlist_id = client.post(
            "/api/music/playlists/default",
            headers=headers,
            json={"scope": "cloud"},
        ).json()["id"]
        payload = {
            "items": [
                {
                    "content_hash": content_hash,
                    "title_alias": f"song-{index}",
                    "artist_alias": "",
                    "device_id": "device-a",
                }
                for index in range(2001)
            ]
        }

        response = client.post(f"/api/music/playlists/{playlist_id}/items", headers=headers, json=payload)
        assert response.status_code == 400
        assert response.json()["code"] == "playlist_item_limit_exceeded"
```

Add:

```python
def test_playlist_append_requires_current_user_song_owner() -> None:
    audio_bytes = wav_bytes()
    with TestClient(create_app()) as client:
        owner_token = register_via_test_crypto(client, "owner@example.com", "Password123")[
            "access_token"
        ]
        owner_headers = {"Authorization": f"Bearer {owner_token}"}
        content_hash = client.post(
            "/api/music/upload",
            headers=owner_headers,
            files={"file": ("rain.wav", audio_bytes, "audio/wav")},
        ).json()["content_hash"]

        other_token = register_via_test_crypto(client, "other@example.com", "Password123")[
            "access_token"
        ]
        other_headers = {"Authorization": f"Bearer {other_token}"}
        playlist_id = client.post(
            "/api/music/playlists/default",
            headers=other_headers,
            json={"scope": "cloud"},
        ).json()["id"]
        response = client.post(
            f"/api/music/playlists/{playlist_id}/items",
            headers=other_headers,
            json={
                "items": [
                    {
                        "content_hash": content_hash,
                        "title_alias": "borrowed",
                        "artist_alias": "",
                        "device_id": "device-b",
                    }
                ]
            },
        )
        assert response.status_code == 400
        assert response.json()["code"] == "song_owner_required"
```

- [ ] **Step 2: Run new tests to verify failures**

Run:

```bash
.venv/bin/python -m pytest tests/test_music_routes.py::test_playlist_append_rejects_when_item_limit_exceeded tests/test_music_routes.py::test_playlist_append_requires_current_user_song_owner -q
```

Expected: fail until exact validation is present.

- [ ] **Step 3: Add validation in `append_playlist_items`**

In `server/yts_server/domains/playlists.py`, before creating rows:

```python
active_count = await _active_item_count(session, playlist_id=playlist_id)
if active_count + len(items) > MAX_PLAYLIST_ITEMS:
    raise AppError.bad_request(
        "playlist_item_limit_exceeded",
        "playlist item limit is 2000",
        "items",
    )
```

For every `content_hash`, query `MetaSong` and `LocalImportOwner`; raise `meta_song_required` or `song_owner_required` with no silent skip.

- [ ] **Step 4: Run full backend music tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_music_routes.py -q
```

Expected: pass.

- [ ] **Step 5: Commit validations**

```bash
git add server/yts_server/domains/playlists.py tests/test_music_routes.py
git commit -m "test: enforce playlist item limit and song ownership"
```

---

## Task 5: Frontend Music Services And Playlist Store

**Files:**
- Modify: `desktop/frontend/src/services/music.js`
- Modify: `desktop/frontend/src/stores/playlist.js`
- Test: `tests/test_frontend_creator_os_layout.py`

- [ ] **Step 1: Add static frontend API contract test**

In `tests/test_frontend_creator_os_layout.py`, add:

```python
def test_music_service_uses_playlist_and_song_upload_contracts() -> None:
    service = read_source("services/music.js")
    store = read_source("stores/playlist.js")

    for token in [
        "uploadSong",
        'uploadForm("/api/music/upload"',
        "listPlaylists",
        'requestJson(`/api/music/playlists',
        "ensureDefaultPlaylist",
        'requestJson(\"/api/music/playlists/default\"',
        "appendPlaylistItems",
        'requestJson(`/api/music/playlists/${playlistId}/items`',
        "reorderPlaylistItems",
        'requestJson(`/api/music/playlists/${playlistId}/items/reorder`',
    ]:
        assert token in service

    for token in [
        "playlists: []",
        "currentPlaylistId",
        "playlistItems",
        "ensureDefault",
        "loadItems",
        "appendItems",
        "item_count",
        "meta_song",
    ]:
        assert token in store
```

- [ ] **Step 2: Run the static test to verify failure**

Run:

```bash
.venv/bin/python -m pytest tests/test_frontend_creator_os_layout.py::test_music_service_uses_playlist_and_song_upload_contracts -q
```

Expected: fail because helpers are not present.

- [ ] **Step 3: Replace music service helpers**

Modify `desktop/frontend/src/services/music.js`:

```javascript
export function listPlaylists({ scope } = {}) {
  const params = new URLSearchParams();
  if (scope) params.set("scope", scope);
  const query = params.toString();
  return requestJson(`/api/music/playlists${query ? `?${query}` : ""}`);
}

export function ensureDefaultPlaylist({ scope = "cloud" } = {}) {
  return requestJson("/api/music/playlists/default", {
    method: "POST",
    body: JSON.stringify({ scope }),
  });
}

export function createPlaylist({ name, scope = "cloud" } = {}) {
  return requestJson("/api/music/playlists", {
    method: "POST",
    body: JSON.stringify({ name, scope }),
  });
}

export function listPlaylistItems({ playlistId } = {}) {
  if (!playlistId) throw new Error("listPlaylistItems requires playlistId");
  return requestJson(`/api/music/playlists/${encodeURIComponent(playlistId)}/items`);
}

export function appendPlaylistItems({ playlistId, items } = {}) {
  if (!playlistId) throw new Error("appendPlaylistItems requires playlistId");
  return requestJson(`/api/music/playlists/${encodeURIComponent(playlistId)}/items`, {
    method: "POST",
    body: JSON.stringify({ items }),
  });
}

export function reorderPlaylistItems({ playlistId, orderedItemIds } = {}) {
  if (!playlistId) throw new Error("reorderPlaylistItems requires playlistId");
  return requestJson(`/api/music/playlists/${encodeURIComponent(playlistId)}/items/reorder`, {
    method: "POST",
    body: JSON.stringify({ ordered_item_ids: orderedItemIds }),
  });
}

export async function uploadSong({ file, mime, filename } = {}) {
  if (!file) {
    throw new Error("uploadSong requires file");
  }
  const form = new FormData();
  form.append("file", file, filename || file.name || "audio.bin");
  if (mime) form.append("mime", mime);
  if (filename) form.append("filename", filename);
  return uploadForm("/api/music/upload", form);
}
```

- [ ] **Step 4: Update playlist store**

Modify `desktop/frontend/src/stores/playlist.js` state:

```javascript
state: () => ({
  playlists: [],
  currentPlaylistId: "",
  playlistItems: [],
  syncing: false,
  lastError: "",
}),
```

Add getters:

```javascript
currentPlaylist: (state) => state.playlists.find((item) => item.id === state.currentPlaylistId) || null,
activeItems: (state) => state.playlistItems.filter((item) => item.deleted_at_ms == null),
```

Add actions `ensureDefault`, `loadPlaylists`, `loadItems`, `hydrate`, `appendItems`, and `reorder` using service helpers. `hydrate({ scope })` must ensure default playlist, set `currentPlaylistId`, then load items.

- [ ] **Step 5: Run frontend static test**

Run:

```bash
.venv/bin/python -m pytest tests/test_frontend_creator_os_layout.py::test_music_service_uses_playlist_and_song_upload_contracts -q
```

Expected: pass.

- [ ] **Step 6: Commit service/store**

```bash
git add desktop/frontend/src/services/music.js desktop/frontend/src/stores/playlist.js tests/test_frontend_creator_os_layout.py
git commit -m "feat: add frontend playlist service store"
```

---

## Task 6: Music Import Drawer Component

**Files:**
- Create: `desktop/frontend/src/components/MusicImportDrawer.vue`
- Modify: `tests/test_frontend_creator_os_layout.py`

- [ ] **Step 1: Add drawer structure test**

Add:

```python
def test_music_import_drawer_supports_batch_status_and_capacity_warning() -> None:
    drawer = read_source("components/MusicImportDrawer.vue")
    for token in [
        "导入本地歌曲",
        "将导入到",
        "currentTargetLabel",
        "最多 2000 首",
        "remainingCapacity",
        "queued",
        "uploading",
        "uploaded",
        "syncing",
        "done",
        "failed",
        "retryImport",
        "uploadSong",
        "appendItems",
        "multiple",
    ]:
        assert token in drawer
```

- [ ] **Step 2: Run drawer test to verify failure**

Run:

```bash
.venv/bin/python -m pytest tests/test_frontend_creator_os_layout.py::test_music_import_drawer_supports_batch_status_and_capacity_warning -q
```

Expected: fail because component file is missing.

- [ ] **Step 3: Implement `MusicImportDrawer.vue`**

Create the component with props:

```javascript
const props = defineProps({
  open: { type: Boolean, default: false },
  target: { type: String, required: true },
});
```

Use stores:

```javascript
const playlist = usePlaylistStore();
const targetLabel = computed(() => (props.target === "local" ? "本地" : "云端"));
const currentTargetLabel = computed(() => `${targetLabel.value}歌单 · ${playlist.currentPlaylist?.name || "默认歌单"}`);
const remainingCapacity = computed(() => Math.max(0, 2000 - (playlist.currentPlaylist?.item_count || playlist.activeItems.length || 0)));
```

Use per-file states:

```javascript
function fileTask(file) {
  return {
    id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    file,
    filename: file.name,
    titleAlias: stripExtension(file.name),
    status: "queued",
    error: "",
    uploadResult: null,
  };
}
```

Implement `startImport(task)`:

```javascript
task.status = "uploading";
task.error = "";
try {
  task.uploadResult = await uploadSong({ file: task.file, mime: task.file.type, filename: task.file.name });
  task.status = "uploaded";
  task.status = "syncing";
  await playlist.appendItems([
    {
      content_hash: task.uploadResult.content_hash,
      title_alias: task.titleAlias,
      artist_alias: "",
      device_id: deviceId.value,
    },
  ]);
  task.status = "done";
} catch (err) {
  task.status = "failed";
  task.error = err instanceof Error ? err.message : String(err);
}
```

If `task.uploadResult` exists during retry, skip `uploadSong` and only call `playlist.appendItems`.

- [ ] **Step 4: Add scoped CSS**

Style as a right-side floating drawer with no page layout shift. Use dark UI colors already present in `MusicPage.vue`; avoid adding large outer border frames.

- [ ] **Step 5: Run drawer static test**

Run:

```bash
.venv/bin/python -m pytest tests/test_frontend_creator_os_layout.py::test_music_import_drawer_supports_batch_status_and_capacity_warning -q
```

Expected: pass.

- [ ] **Step 6: Commit drawer**

```bash
git add desktop/frontend/src/components/MusicImportDrawer.vue tests/test_frontend_creator_os_layout.py
git commit -m "feat: add music import drawer"
```

---

## Task 7: Wire Music Page To New Store And Drawer

**Files:**
- Modify: `desktop/frontend/src/pages/MusicPage.vue`
- Modify: `tests/test_frontend_creator_os_layout.py`

- [ ] **Step 1: Add music page wiring test**

Add:

```python
def test_music_page_uses_import_drawer_and_meta_song_tracks() -> None:
    music = read_source("pages/MusicPage.vue")
    for token in [
        "MusicImportDrawer",
        "importDrawerOpen",
        "@click=\"importDrawerOpen = true\"",
        ":open=\"importDrawerOpen\"",
        "@close=\"importDrawerOpen = false\"",
        "playlist.hydrate",
        "item.title_alias",
        "item.meta_song",
        "`/api/music/file/${encodeURIComponent(item.content_hash)}`",
    ]:
        assert token in music
    assert "uploadLocalImport" not in music
    assert "onImportFile" not in music
```

- [ ] **Step 2: Run wiring test to verify failure**

Run:

```bash
.venv/bin/python -m pytest tests/test_frontend_creator_os_layout.py::test_music_page_uses_import_drawer_and_meta_song_tracks -q
```

Expected: fail because `MusicPage.vue` still imports `uploadLocalImport`.

- [ ] **Step 3: Update `MusicPage.vue` imports and state**

Replace `uploadLocalImport` import with:

```javascript
import MusicImportDrawer from "../components/MusicImportDrawer.vue";
import { useEnvironmentStore } from "../stores/environment";
```

Add:

```javascript
const environment = useEnvironmentStore();
const importDrawerOpen = ref(false);
```

Update `onMounted`:

```javascript
onMounted(async () => {
  environment.attach();
  await refreshPlaylist();
});
```

Add `onBeforeUnmount` to detach if `MusicPage.vue` already imports lifecycle hooks.

- [ ] **Step 4: Map playlist items to tracks**

Replace track mapping with:

```javascript
const tracks = computed(() =>
  playlist.activeItems.map((item) => ({
    id: item.id,
    title: item.title_alias || "未命名歌曲",
    artist: item.artist_alias || "未知艺人",
    contentHash: item.content_hash,
    metaSong: item.meta_song,
    url: playableTrackUrl(item),
  })),
);

function playableTrackUrl(item) {
  if (!item.content_hash) {
    throw new Error("playlist item requires content_hash");
  }
  return `/api/music/file/${encodeURIComponent(item.content_hash)}`;
}
```

- [ ] **Step 5: Replace import label with drawer button**

Replace the right-side import label with:

```vue
<button type="button" title="导入" aria-label="导入" @click="importDrawerOpen = true">
  <Upload :size="17" />
</button>
```

Render drawer near the drawer panel:

```vue
<MusicImportDrawer
  :open="importDrawerOpen"
  :target="environment.target"
  @close="importDrawerOpen = false"
  @imported="refreshPlaylist"
/>
```

- [ ] **Step 6: Run wiring test and full frontend static layout test**

Run:

```bash
.venv/bin/python -m pytest tests/test_frontend_creator_os_layout.py -q
```

Expected: pass.

- [ ] **Step 7: Commit music page wiring**

```bash
git add desktop/frontend/src/pages/MusicPage.vue tests/test_frontend_creator_os_layout.py
git commit -m "feat: wire music page import drawer"
```

---

## Task 8: Full Verification And Browser Check

**Files:**
- No new source files.

- [ ] **Step 1: Run backend tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_music_routes.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Run frontend source tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_frontend_creator_os_layout.py tests/test_frontend_workspace_layout.py -q
```

Expected: all tests pass.

- [ ] **Step 3: Build frontend**

Run:

```bash
PATH=/Users/bytedance/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH ./node_modules/.bin/vite build
```

from `desktop/frontend`.

Expected: Vite build exits with code 0.

- [ ] **Step 4: Run repository hygiene check**

Run:

```bash
git diff --check
```

Expected: no output.

- [ ] **Step 5: Browser verification**

Open `http://127.0.0.1:1420/music`, click the right-side import icon, and verify:

- The drawer opens over the player without shifting layout.
- The drawer says `将导入到 云端歌单` or `将导入到 本地歌单` according to the global environment.
- The capacity copy displays `最多 2000 首`.
- The file input accepts multiple audio files.
- Closing the drawer leaves playback state unchanged.

- [ ] **Step 6: Final implementation commit**

If Tasks 1-7 were committed separately, inspect verification changes with:

```bash
git status --short
```

If `git status --short` prints no files changed by verification, do not create an empty commit. If it prints files changed by verification fixes, stage those exact files and commit with:

```bash
git commit -m "fix: complete playlist import verification"
```

---

## Self-Review

**Spec coverage:** The plan covers `meta_song`, `content_hash`, owner access, playlist item aliases, ordered positions, 2000 limit, server-side metadata extraction, batch frontend import, partial failure retry, and current local/cloud target behavior.

**Placeholder scan:** This plan contains no `TBD`, no incomplete file paths, and no unscoped test commands.

**Type consistency:** Backend names use `content_hash`, `title_alias`, `artist_alias`, `position`, and `meta_song`. Frontend service methods use the same snake_case payload fields required by the API.
