from __future__ import annotations

from datetime import date

from fastapi import APIRouter

from ..domains import credits as credits_domain
from ..domains import usage as usage_domain
from .dependencies import CurrentUser, DbSession

router = APIRouter(tags=["credits"])


@router.get("/credits/balance")
async def get_balance(
    user: CurrentUser,
    session: DbSession,
) -> dict:
    balance = await credits_domain.get_balance(session, user.user_uuid)
    return {
        "user_uuid": balance.user_uuid,
        "balance": balance.balance,
        "frozen_balance": balance.frozen_balance,
        "updated_at": balance.updated_at.isoformat() if balance.updated_at else None,
    }


@router.get("/credits/ledger")
async def list_ledger(
    user: CurrentUser,
    session: DbSession,
    limit: int = 20,
    offset: int = 0,
) -> list[dict]:
    rows = await credits_domain.list_ledger(
        session, user.user_uuid, limit=max(1, min(limit, 100)), offset=max(0, offset)
    )
    return [
        {
            "id": str(row.id),
            "change_amount": row.change_amount,
            "change_frozen_amount": row.change_frozen_amount,
            "balance_after": row.balance_after,
            "frozen_balance_after": row.frozen_balance_after,
            "kind": row.kind,
            "biz_type": row.biz_type,
            "biz_id": row.biz_id,
            "remark": row.remark,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


@router.get("/usage/daily")
async def daily_usage(
    user: CurrentUser,
    session: DbSession,
) -> dict:
    return await usage_domain.get_daily_usage(session, user.user_uuid, date.today())
