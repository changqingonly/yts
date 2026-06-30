from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver

from ..config import Settings

_CHECKPOINTER_CONTEXT: AbstractContextManager[Any] | None = None
_CHECKPOINTER: Any | None = None
_CHECKPOINTER_BACKEND: str | None = None


def build_langgraph_checkpointer(settings: Settings) -> Any | None:
    """Build the configured LangGraph checkpointer for runtime execution."""

    backend = settings.langgraph_checkpoint_backend.strip().lower()
    if backend == "disabled":
        return None
    if backend == "memory":
        return _memory_checkpointer(backend)
    if backend == "postgres":
        return _postgres_checkpointer(settings, backend)
    raise ValueError(f"unsupported langgraph checkpoint backend: {settings.langgraph_checkpoint_backend}")


def close_langgraph_checkpointer() -> None:
    global _CHECKPOINTER, _CHECKPOINTER_BACKEND, _CHECKPOINTER_CONTEXT

    context = _CHECKPOINTER_CONTEXT
    _CHECKPOINTER = None
    _CHECKPOINTER_BACKEND = None
    _CHECKPOINTER_CONTEXT = None
    if context is not None:
        context.__exit__(None, None, None)


def setup_langgraph_checkpointer(settings: Settings) -> None:
    backend = settings.langgraph_checkpoint_backend.strip().lower()
    if backend != "postgres":
        raise ValueError("langgraph checkpoint setup requires backend=postgres")
    with _postgres_saver_context(settings) as checkpointer:
        checkpointer.setup()


def _memory_checkpointer(backend: str) -> InMemorySaver:
    global _CHECKPOINTER, _CHECKPOINTER_BACKEND

    if _CHECKPOINTER is not None:
        if _CHECKPOINTER_BACKEND != backend:
            raise ValueError("langgraph checkpointer backend changed while a checkpointer is active")
        return _CHECKPOINTER
    _CHECKPOINTER = InMemorySaver()
    _CHECKPOINTER_BACKEND = backend
    return _CHECKPOINTER


def _postgres_checkpointer(settings: Settings, backend: str):
    global _CHECKPOINTER, _CHECKPOINTER_BACKEND, _CHECKPOINTER_CONTEXT

    if not settings.langgraph_checkpoint_postgres_dsn.strip():
        raise ValueError("langgraph checkpoint postgres_dsn must not be empty when backend=postgres")
    if _CHECKPOINTER is not None:
        if _CHECKPOINTER_BACKEND != backend:
            raise ValueError("langgraph checkpointer backend changed while a checkpointer is active")
        return _CHECKPOINTER
    try:
        context = _postgres_saver_context(settings)
    except ModuleNotFoundError as exc:
        raise ValueError(
            "langgraph checkpoint backend postgres requires langgraph-checkpoint-postgres"
        ) from exc

    checkpointer = context.__enter__()
    _CHECKPOINTER_CONTEXT = context
    _CHECKPOINTER = checkpointer
    _CHECKPOINTER_BACKEND = backend
    return checkpointer


def _postgres_saver_context(settings: Settings):
    from langgraph.checkpoint.postgres import PostgresSaver

    return PostgresSaver.from_conn_string(settings.langgraph_checkpoint_postgres_dsn)
