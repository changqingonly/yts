"""FastAPI 应用装配。HTTP 入口,挂 core;profile 决定云/本地行为。"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from yts_core.config import get_settings

from .routes import creation, health


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if settings.phoenix_enabled:
        from .eval.phoenix import init_phoenix

        init_phoenix()
    # TODO: DB engine 预热 / 迁移检查(见 db/session.py)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="yts", version="0.1.0", lifespan=lifespan)
    app.include_router(health.router)
    app.include_router(creation.router, prefix="/api")
    app.state.settings = settings
    return app


app = create_app()
