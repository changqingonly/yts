"""FastAPI 应用装配。HTTP 入口,挂 core;profile 决定云/本地行为。"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from yts_core.config import get_settings
from yts_core.orchestration.checkpointing import close_langgraph_checkpointer

from .cors import DiagnosticCORSMiddleware
from .db.bootstrap import create_all_tables
from .errors import register_error_handlers
from .routes import (
    auth,
    creation,
    credits,
    health,
    music,
    music_stream,
    provider_gated,
    song,
    user,
    workflow,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if settings.phoenix_enabled:
        from .eval.phoenix import init_phoenix

        init_phoenix()
    await create_all_tables()
    try:
        yield
    finally:
        close_langgraph_checkpointer()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="yts", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        DiagnosticCORSMiddleware,
        allow_origins=["http://127.0.0.1:1420", "http://localhost:1420"],
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )
    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(auth.router, prefix="/api")
    app.include_router(user.router, prefix="/api")
    app.include_router(credits.router, prefix="/api")
    app.include_router(song.router, prefix="/api")
    app.include_router(music.router, prefix="/api")
    app.include_router(provider_gated.router, prefix="/api")
    app.include_router(creation.router, prefix="/api")
    app.include_router(workflow.router, prefix="/api")
    app.include_router(music_stream.router)  # WS /music/stream(无 /api 前缀,对齐流式契约)
    app.state.settings = settings
    return app


app = create_app()
