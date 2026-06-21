"""统一 API 契约(Pydantic)。前端唯一依赖;本地/云两实现共用。

切换实现(本地 sidecar / 云端)不改这些 schema。
"""
from .common import ExecutionSummary, StageTrace
from .creation import (
    CreationRequest,
    CreationResult,
    InspirationRequest,
    InspirationResult,
)

__all__ = [
    "ExecutionSummary",
    "StageTrace",
    "CreationRequest",
    "CreationResult",
    "InspirationRequest",
    "InspirationResult",
]
