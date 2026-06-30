from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ..domains import songs as songs_domain
from .dependencies import CurrentUser, DbSession

router = APIRouter(prefix="/song", tags=["song"])


class CreateSongRequest(BaseModel):
    name: str
    lyric_prompt: str
    style_prompt: str
    llm: str
    prompt: str


class UpdateSongRequest(BaseModel):
    name: str | None = None
    lyric_prompt: str | None = None
    style_prompt: str | None = None
    llm: str | None = None
    prompt: str | None = None


@router.post("/save")
async def save_song(req: CreateSongRequest, user: CurrentUser, session: DbSession) -> dict:
    response = await songs_domain.save_song(
        session,
        songs_domain.SaveSongCommand(
            user_uuid=user.user_uuid,
            name=req.name,
            prompt=req.prompt,
            lyric_prompt=req.lyric_prompt,
            style_prompt=req.style_prompt,
            llm=req.llm,
        ),
    )
    await session.commit()
    return response


@router.get("/list")
async def list_songs(
    user: CurrentUser,
    session: DbSession,
    limit: int = 20,
    offset: int = 0,
) -> list[dict]:
    return await songs_domain.list_songs(
        session,
        user_uuid=user.user_uuid,
        limit=max(1, min(limit, 200)),
        offset=max(0, offset),
    )


@router.get("/{song_id}")
async def get_song(song_id: int, user: CurrentUser, session: DbSession) -> dict:
    return await songs_domain.get_song(session, user_uuid=user.user_uuid, song_id=song_id)


@router.put("/{song_id}")
async def update_song(
    song_id: int,
    req: UpdateSongRequest,
    user: CurrentUser,
    session: DbSession,
) -> dict:
    response = await songs_domain.update_song(
        session,
        user_uuid=user.user_uuid,
        song_id=song_id,
        name=req.name,
        prompt=req.prompt,
        lyric_prompt=req.lyric_prompt,
        style_prompt=req.style_prompt,
        llm=req.llm,
    )
    await session.commit()
    return response


@router.delete("/{song_id}")
async def delete_song(song_id: int, user: CurrentUser, session: DbSession) -> dict:
    await songs_domain.delete_song(session, user_uuid=user.user_uuid, song_id=song_id)
    await session.commit()
    return {"ok": True}
