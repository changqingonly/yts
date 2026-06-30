from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from ..db.models import UserAccount
from ..domains import auth as auth_domain
from .dependencies import CurrentUser, DbSession

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: str
    key_id: str
    password_ciphertext_b64: str
    confirm_password_ciphertext_b64: str
    agreement_accepted: bool


class LoginRequest(BaseModel):
    account: str
    key_id: str
    password_ciphertext_b64: str


@router.get("/register_key")
async def register_key() -> dict:
    return auth_domain.register_key_response()


@router.get("/login_key")
async def login_key() -> dict:
    return auth_domain.register_key_response()


@router.get("/register_check")
async def register_check(session: DbSession, email: str = "") -> dict:
    email = email.strip()
    exists = False
    if email:
        exists = (
            await session.execute(select(UserAccount).where(UserAccount.email == email))
        ).scalar_one_or_none() is not None
    return {"email_ok": not exists, "email_msg": "" if not exists else "Email 不可用"}


@router.post("/register")
async def register(req: RegisterRequest, session: DbSession) -> dict:
    response = await auth_domain.register_user(
        session,
        email=req.email,
        key_id=req.key_id,
        password_ciphertext_b64=req.password_ciphertext_b64,
        confirm_password_ciphertext_b64=req.confirm_password_ciphertext_b64,
        agreement_accepted=req.agreement_accepted,
    )
    await session.commit()
    return response


@router.post("/login")
async def login(req: LoginRequest, session: DbSession) -> dict:
    response = await auth_domain.login_user(
        session,
        account=req.account,
        key_id=req.key_id,
        password_ciphertext_b64=req.password_ciphertext_b64,
    )
    await session.commit()
    return response


@router.get("/me")
async def me(user: CurrentUser) -> dict:
    return {
        "uuid": user.user_uuid,
        "user_uuid": user.user_uuid,
        "username": user.username,
        "email": user.email,
        "avatar_url": user.avatar_url,
        "offline_lease": "",
        "offline_lease_expires_at": 0,
    }


@router.post("/logout")
async def logout(
    user: CurrentUser,
    session: DbSession,
) -> dict:
    await auth_domain.logout(session, user.session_id)
    await session.commit()
    return {"ok": True}
