from __future__ import annotations

import logging
import sys

import structlog
from yts_core.config import Profile, Settings


def configure_logging(settings: Settings) -> None:
    renderer = _renderer(settings)
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    formatter = structlog.stdlib.ProcessorFormatter(
        processor=renderer,
        foreign_pre_chain=shared_processors,
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    handler.set_name("yts_structlog")
    root_logger = logging.getLogger()
    if not any(existing.get_name() == "yts_structlog" for existing in root_logger.handlers):
        root_logger.addHandler(handler)
    root_logger.setLevel(_logging_level(settings.logging_level))

    for logger_name in ["uvicorn", "uvicorn.error", "uvicorn.access"]:
        logging.getLogger(logger_name).handlers.clear()
        logging.getLogger(logger_name).propagate = True


def _renderer(settings: Settings):
    configured = settings.logging_format.strip().lower()
    if configured == "auto":
        configured = "json" if settings.profile == Profile.CLOUD else "console"
    if configured == "json":
        return structlog.processors.JSONRenderer()
    if configured == "console":
        return structlog.dev.ConsoleRenderer(colors=False)
    raise ValueError(f"unsupported logging format: {settings.logging_format}")


def _logging_level(value: str) -> int:
    level = logging.getLevelName(value.strip().upper())
    if isinstance(level, int):
        return level
    raise ValueError(f"unsupported logging level: {value}")
