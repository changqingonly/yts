from __future__ import annotations

import time
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import SongDetail, SongPrompt
from ..errors import AppError


@dataclass(frozen=True)
class SaveSongCommand:
    user_uuid: str
    name: str
    prompt: str
    lyric_prompt: str
    style_prompt: str
    llm: str


async def save_song(session: AsyncSession, command: SaveSongCommand) -> dict:
    _validate_required(command.name, "name")
    _validate_required(command.prompt, "prompt")
    _validate_required(command.lyric_prompt, "lyric_prompt")
    _validate_required(command.style_prompt, "style_prompt")
    prompt = SongPrompt(
        id=_new_i64_id(),
        user_uuid=command.user_uuid,
        name=command.name.strip(),
        prompt=command.prompt.strip(),
        from_llm=command.llm.strip() or "unknown",
        version=1,
    )
    session.add(prompt)
    await session.flush()
    detail = SongDetail(
        id=_new_i64_id(),
        prompt_id=prompt.id,
        lyric_prompt=command.lyric_prompt.strip(),
        style_prompt=command.style_prompt.strip(),
    )
    session.add(detail)
    await session.flush()
    return _song_response(prompt, detail)


async def list_songs(
    session: AsyncSession, *, user_uuid: str, limit: int, offset: int
) -> list[dict]:
    result = await session.execute(
        select(SongPrompt)
        .where(SongPrompt.user_uuid == user_uuid)
        .order_by(SongPrompt.updated_at.desc())
        .offset(offset)
        .limit(limit)
    )
    prompts = list(result.scalars().all())
    return [await _response_for_prompt(session, prompt) for prompt in prompts]


async def get_song(session: AsyncSession, *, user_uuid: str, song_id: int) -> dict:
    prompt = await _owned_prompt(session, user_uuid, song_id)
    return await _response_for_prompt(session, prompt)


async def update_song(
    session: AsyncSession,
    *,
    user_uuid: str,
    song_id: int,
    name: str | None = None,
    prompt: str | None = None,
    lyric_prompt: str | None = None,
    style_prompt: str | None = None,
    llm: str | None = None,
) -> dict:
    song_prompt = await _owned_prompt(session, user_uuid, song_id)
    detail = await _detail_for_prompt(session, song_prompt.id)
    if name is not None:
        _validate_required(name, "name")
        song_prompt.name = name.strip()
    if prompt is not None:
        _validate_required(prompt, "prompt")
        song_prompt.prompt = prompt.strip()
    if llm is not None:
        song_prompt.from_llm = llm.strip() or "unknown"
    if lyric_prompt is not None:
        _validate_required(lyric_prompt, "lyric_prompt")
        detail.lyric_prompt = lyric_prompt.strip()
    if style_prompt is not None:
        _validate_required(style_prompt, "style_prompt")
        detail.style_prompt = style_prompt.strip()
    song_prompt.version += 1
    await session.flush()
    await session.refresh(song_prompt)
    await session.refresh(detail)
    return _song_response(song_prompt, detail)


async def delete_song(session: AsyncSession, *, user_uuid: str, song_id: int) -> None:
    prompt = await _owned_prompt(session, user_uuid, song_id)
    detail = await _detail_for_prompt(session, prompt.id)
    await session.delete(detail)
    await session.delete(prompt)


async def _response_for_prompt(session: AsyncSession, prompt: SongPrompt) -> dict:
    detail = await _detail_for_prompt(session, prompt.id)
    return _song_response(prompt, detail)


def _song_response(prompt: SongPrompt, detail: SongDetail) -> dict:
    return {
        "id": str(prompt.id),
        "prompt_id": str(prompt.id),
        "name": prompt.name,
        "prompt": prompt.prompt,
        "lyric_prompt": detail.lyric_prompt,
        "style_prompt": detail.style_prompt,
        "cover_url": None,
        "from_llm": prompt.from_llm,
        "version": prompt.version,
        "create_time": prompt.created_at.isoformat() if prompt.created_at else None,
        "update_time": prompt.updated_at.isoformat() if prompt.updated_at else None,
    }


async def _owned_prompt(session: AsyncSession, user_uuid: str, song_id: int) -> SongPrompt:
    prompt = await session.get(SongPrompt, song_id)
    if prompt is None or prompt.user_uuid != user_uuid:
        raise AppError.not_found("song_not_found", "song not found")
    return prompt


async def _detail_for_prompt(session: AsyncSession, prompt_id: int) -> SongDetail:
    detail = (
        await session.execute(select(SongDetail).where(SongDetail.prompt_id == prompt_id))
    ).scalar_one_or_none()
    if detail is None:
        raise AppError.not_found("song_detail_not_found", "song detail not found")
    return detail


def _validate_required(value: str, field: str) -> None:
    if not value.strip():
        raise AppError.bad_request(f"{field}_required", f"{field} is required", field)


def _new_i64_id() -> int:
    return time.time_ns()
