from __future__ import annotations

import base64
import re
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from yts_core.config import get_settings

from ..db.models import UserAccount
from ..errors import AppError


async def get_profile(session: AsyncSession, user_id: int) -> dict:
    user = await session.get(UserAccount, user_id)
    if user is None:
        raise AppError.not_found("user_not_found", "user not found")
    return _profile_response(user)


async def update_profile(
    session: AsyncSession,
    user_id: int,
    *,
    username: str,
    avatar_url: str | None,
    birthday: str | None,
    bio: str | None,
    gender: str | None,
) -> dict:
    user = await session.get(UserAccount, user_id)
    if user is None:
        raise AppError.not_found("user_not_found", "user not found")
    username = username.strip()
    if not username:
        raise AppError.bad_request("username_required", "username is required", "username")
    existing = (
        await session.execute(
            select(UserAccount).where(UserAccount.username == username, UserAccount.id != user_id)
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise AppError.bad_request("username_exists", "username already exists", "username")
    user.username = username
    user.avatar_url = avatar_url
    user.birthday = _clean_optional(birthday)
    user.bio = _clean_optional(bio)
    user.gender = _clean_optional(gender)
    await session.flush()
    return _profile_response(user)


async def save_uploaded_avatar(user_id: int, image_data_url: str) -> str:
    extension, payload = _parse_image_data_url(image_data_url)
    avatar_dir = Path(get_settings().avatar_storage_dir)
    avatar_dir.mkdir(parents=True, exist_ok=True)
    file_name = f"{user_id}-{uuid.uuid4().hex}.{extension}"
    file_path = avatar_dir / file_name
    file_path.write_bytes(payload)
    return f"/static/user/avatar/uploaded/{file_name}"


def _profile_response(user: UserAccount) -> dict:
    return {
        "user_id": str(user.id),
        "uuid": user.uuid,
        "username": user.username,
        "email": user.email,
        "avatar_url": user.avatar_url,
        "birthday": user.birthday,
        "bio": user.bio,
        "gender": user.gender,
    }


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _parse_image_data_url(image_data_url: str) -> tuple[str, bytes]:
    match = re.match(r"^data:image/(png|jpeg|webp);base64,(.+)$", image_data_url)
    if not match:
        raise AppError.bad_request("avatar_invalid", "invalid avatar data url", "image_data_url")
    extension = "jpg" if match.group(1) == "jpeg" else match.group(1)
    try:
        payload = base64.b64decode(match.group(2).encode("ascii"), validate=True)
    except Exception as exc:
        raise AppError.bad_request("avatar_invalid_base64", "invalid avatar base64") from exc
    if not payload:
        raise AppError.bad_request("avatar_empty", "avatar image must not be empty")
    return extension, payload
