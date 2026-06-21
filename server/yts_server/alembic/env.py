"""Alembic 环境(骨架)。从 yts_core.config 取连接串;target_metadata 指向 db.Base。

注:async 引擎下迁移通常用同步 URL 跑;本骨架仅占位,真实迁移 TODO。
"""

from __future__ import annotations

import yts_server.db.models  # noqa: F401  注册模型到 metadata
from alembic import context
from yts_core.config import get_settings
from yts_server.db.session import Base

target_metadata = Base.metadata


def _sync_url() -> str:
    # 把 async 驱动换成同步驱动跑迁移
    url = get_settings().database_url
    return url.replace("+asyncpg", "").replace("+aiosqlite", "")


def run_migrations_offline() -> None:
    context.configure(url=_sync_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    from sqlalchemy import create_engine

    engine = create_engine(_sync_url())
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
