from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ..domains import profile as profile_domain
from .dependencies import CurrentUser, DbSession

router = APIRouter(prefix="/user", tags=["user"])


class UpdateProfileRequest(BaseModel):
    username: str
    avatar_url: str | None = None
    birthday: str | None = None
    bio: str | None = None
    gender: str | None = None


class UploadAvatarRequest(BaseModel):
    image_data_url: str


@router.get("/profile")
async def get_profile(
    user: CurrentUser,
    session: DbSession,
) -> dict:
    return await profile_domain.get_profile(session, user.user_id)


@router.put("/profile")
async def update_profile(
    req: UpdateProfileRequest,
    user: CurrentUser,
    session: DbSession,
) -> dict:
    response = await profile_domain.update_profile(
        session,
        user.user_id,
        username=req.username,
        avatar_url=req.avatar_url,
        birthday=req.birthday,
        bio=req.bio,
        gender=req.gender,
    )
    await session.commit()
    return response


@router.post("/avatar/upload")
async def upload_avatar(
    req: UploadAvatarRequest,
    user: CurrentUser,
) -> dict:
    avatar_url = await profile_domain.save_uploaded_avatar(user.user_id, req.image_data_url)
    return {"avatar_url": avatar_url}
