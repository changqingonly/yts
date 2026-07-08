from __future__ import annotations

import asyncio

from sqlalchemy import text
from yts_core.config import get_settings
from yts_core.inference.factory import make_backend
from yts_core.orchestration.checkpointing import setup_langgraph_checkpointer
from yts_server.db.bootstrap import create_all_tables
from yts_server.db.session import get_engine
from yts_server.main import create_app


async def main() -> None:
    try:
        settings = get_settings()
        await create_all_tables()
        if settings.langgraph_checkpoint_backend.strip().lower() == "postgres":
            setup_langgraph_checkpointer(settings)
        engine = get_engine()
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        backend = make_backend(settings)
        messages = [{"role": "user", "content": "Return the word ok."}]
        try:
            result = await backend.generate_text(messages)
        except Exception as exc:
            raise RuntimeError(f"LLM preflight failed: {type(exc).__name__}: {exc}") from exc
        if not result.text.strip():
            raise RuntimeError("LLM preflight returned empty text")
        app = create_app()
        if app.state.settings.profile != settings.profile:
            raise RuntimeError("app settings profile mismatch")
    except Exception as exc:
        raise SystemExit(f"servctl preflight failed: {type(exc).__name__}: {exc}") from None


if __name__ == "__main__":
    asyncio.run(main())
