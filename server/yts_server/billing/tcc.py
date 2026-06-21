"""TCC 三段式预约:reserve → (成功)capture / (失败)release。

本轮 stub。真实实现需放进 DB 事务保证 exactly-once(见 wiki Server-Stack-Plan)。
未来若用 LangGraph 建 reserve/capture/release 三节点 + 条件边(saga),此处改为编排内补偿。
"""
from __future__ import annotations

from contextlib import asynccontextmanager


async def reserve(scene: str) -> str:
    # TODO: 写冻结预占,返回 reservation_id
    return f"resv-stub-{scene}"


async def capture(reservation_id: str) -> None:
    ...  # TODO: 最终扣费,写 ledger


async def release(reservation_id: str) -> None:
    ...  # TODO: 解冻回滚


@asynccontextmanager
async def reservation(*, scene: str, enabled: bool = True):
    """计费包裹。enabled=False(本地 profile)直通,不计费。"""
    if not enabled:
        yield None
        return
    rid = await reserve(scene)
    try:
        yield rid
    except Exception:
        await release(rid)
        raise
    else:
        await capture(rid)
