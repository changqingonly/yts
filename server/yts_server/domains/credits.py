from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import CreditAccount, CreditGrantRecord, CreditLedger, CreditReservation
from ..errors import AppError

DAILY_LOGIN_CREDITS = 10
WELCOME_REGISTER_CREDITS = 50
INSPIRATION_CREDITS = 1
CREATION_CREDITS = 3
CREDIT_RESERVATION_TTL_MINUTES = 30


@dataclass(frozen=True)
class CreditBalance:
    user_uuid: str
    balance: int
    frozen_balance: int
    updated_at: datetime | None


@dataclass(frozen=True)
class CreditReservationEntry:
    reservation_key: str
    amount: int
    status: str


async def get_balance(session: AsyncSession, user_uuid: str) -> CreditBalance:
    account = await _account(session, user_uuid)
    return CreditBalance(
        user_uuid=user_uuid,
        balance=account.balance,
        frozen_balance=account.frozen_balance,
        updated_at=account.updated_at,
    )


async def list_ledger(session: AsyncSession, user_uuid: str, *, limit: int, offset: int) -> list[CreditLedger]:
    result = await session.execute(
        select(CreditLedger)
        .where(CreditLedger.user_uuid == user_uuid)
        .order_by(CreditLedger.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(result.scalars().all())


async def grant_welcome_register_credit(session: AsyncSession, user_uuid: str, at: date) -> int:
    return await _grant_once(
        session,
        user_uuid,
        grant_type="welcome_register",
        grant_date=at.isoformat(),
        amount=WELCOME_REGISTER_CREDITS,
        idempotency_key=f"welcome-register:{user_uuid}:{at.isoformat()}",
        remark="grant welcome register credit",
    )


async def grant_daily_login_credit(session: AsyncSession, user_uuid: str, at: date) -> int:
    if await _has_grant(session, user_uuid, "welcome_register", at.isoformat()):
        return (await _account(session, user_uuid)).balance
    return await _grant_once(
        session,
        user_uuid,
        grant_type="daily_login",
        grant_date=at.isoformat(),
        amount=DAILY_LOGIN_CREDITS,
        idempotency_key=f"daily-login:{user_uuid}:{at.isoformat()}",
        remark="grant daily login credit",
    )


async def reserve_generation_credit(
    session: AsyncSession,
    *,
    user_uuid: str,
    request_id: str,
    scene: str,
) -> CreditReservationEntry:
    amount = _scene_amount(scene)
    account = await _account(session, user_uuid)
    if account.balance < amount:
        raise AppError.insufficient_credits()
    account.balance -= amount
    account.frozen_balance += amount
    account.version += 1
    reservation_key = f"{scene}:{request_id}"
    reservation = CreditReservation(
        id=_new_i64_id(),
        user_uuid=user_uuid,
        reservation_key=reservation_key,
        amount=amount,
        status="reserved",
        biz_type=scene,
        biz_id=request_id,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=CREDIT_RESERVATION_TTL_MINUTES),
    )
    session.add(reservation)
    session.add(
        CreditLedger(
            id=_new_i64_id(),
            user_uuid=user_uuid,
            change_amount=-amount,
            change_frozen_amount=amount,
            balance_after=account.balance,
            frozen_balance_after=account.frozen_balance,
            kind="reserve",
            biz_type=scene,
            biz_id=request_id,
            reservation_key=reservation_key,
            idempotency_key=f"{scene}-reserve:{request_id}",
            remark=f"reserve credit for {scene}",
        )
    )
    return CreditReservationEntry(
        reservation_key=reservation_key, amount=amount, status=reservation.status
    )


async def capture_generation_credit(
    session: AsyncSession, *, reservation_key: str, idempotency_key: str
) -> CreditBalance:
    reservation = await _reservation(session, reservation_key)
    if reservation.status != "reserved":
        raise AppError.bad_request("reservation_not_reserved", "reservation is not reserved")
    account = await _account(session, reservation.user_uuid)
    account.frozen_balance -= reservation.amount
    account.version += 1
    reservation.status = "captured"
    session.add(
        CreditLedger(
            id=_new_i64_id(),
            user_uuid=reservation.user_uuid,
            change_amount=0,
            change_frozen_amount=-reservation.amount,
            balance_after=account.balance,
            frozen_balance_after=account.frozen_balance,
            kind="capture",
            biz_type=reservation.biz_type,
            biz_id=reservation.biz_id,
            reservation_key=reservation_key,
            idempotency_key=idempotency_key,
            remark="capture reserved credit",
        )
    )
    return CreditBalance(
        user_uuid=account.user_uuid,
        balance=account.balance,
        frozen_balance=account.frozen_balance,
        updated_at=account.updated_at,
    )


async def release_generation_credit(
    session: AsyncSession, *, reservation_key: str, idempotency_key: str
) -> CreditBalance:
    reservation = await _reservation(session, reservation_key)
    if reservation.status != "reserved":
        raise AppError.bad_request("reservation_not_reserved", "reservation is not reserved")
    account = await _account(session, reservation.user_uuid)
    account.balance += reservation.amount
    account.frozen_balance -= reservation.amount
    account.version += 1
    reservation.status = "released"
    session.add(
        CreditLedger(
            id=_new_i64_id(),
            user_uuid=reservation.user_uuid,
            change_amount=reservation.amount,
            change_frozen_amount=-reservation.amount,
            balance_after=account.balance,
            frozen_balance_after=account.frozen_balance,
            kind="release",
            biz_type=reservation.biz_type,
            biz_id=reservation.biz_id,
            reservation_key=reservation_key,
            idempotency_key=idempotency_key,
            remark="release reserved credit",
        )
    )
    return CreditBalance(
        user_uuid=account.user_uuid,
        balance=account.balance,
        frozen_balance=account.frozen_balance,
        updated_at=account.updated_at,
    )


async def _grant_once(
    session: AsyncSession,
    user_uuid: str,
    *,
    grant_type: str,
    grant_date: str,
    amount: int,
    idempotency_key: str,
    remark: str,
) -> int:
    if await _has_grant(session, user_uuid, grant_type, grant_date):
        return (await _account(session, user_uuid)).balance
    account = await _account(session, user_uuid)
    account.balance += amount
    account.version += 1
    session.add(
        CreditGrantRecord(
            id=_new_i64_id(), user_uuid=user_uuid, grant_type=grant_type, grant_date=grant_date
        )
    )
    session.add(
        CreditLedger(
            id=_new_i64_id(),
            user_uuid=user_uuid,
            change_amount=amount,
            change_frozen_amount=0,
            balance_after=account.balance,
            frozen_balance_after=account.frozen_balance,
            kind="grant",
            biz_type=grant_type,
            biz_id=grant_date,
            reservation_key=None,
            idempotency_key=idempotency_key,
            remark=remark,
        )
    )
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise
    return account.balance


async def _account(session: AsyncSession, user_uuid: str) -> CreditAccount:
    account = await session.get(CreditAccount, user_uuid)
    if account is None:
        account = CreditAccount(user_uuid=user_uuid, balance=0, frozen_balance=0, version=0)
        session.add(account)
        await session.flush()
    return account


async def _has_grant(session: AsyncSession, user_uuid: str, grant_type: str, grant_date: str) -> bool:
    statement: Select = select(CreditGrantRecord).where(
        CreditGrantRecord.user_uuid == user_uuid,
        CreditGrantRecord.grant_type == grant_type,
        CreditGrantRecord.grant_date == grant_date,
    )
    return (await session.execute(statement)).scalar_one_or_none() is not None


async def _reservation(session: AsyncSession, reservation_key: str) -> CreditReservation:
    statement = select(CreditReservation).where(CreditReservation.reservation_key == reservation_key)
    reservation = (await session.execute(statement)).scalar_one_or_none()
    if reservation is None:
        raise AppError.bad_request("reservation_not_found", "reservation not found")
    return reservation


def _scene_amount(scene: str) -> int:
    if scene in {"lyrics", "creation"}:
        return CREATION_CREDITS
    if scene == "inspiration":
        return INSPIRATION_CREDITS
    raise AppError.bad_request("unknown_credit_scene", f"unknown credit scene: {scene}")


def _new_i64_id() -> int:
    return time.time_ns()
