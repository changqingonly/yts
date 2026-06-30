from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


@dataclass
class AppError(Exception):
    status_code: int
    code: str
    message: str
    field: str | None = None

    @classmethod
    def bad_request(cls, code: str, message: str, field: str | None = None) -> AppError:
        return cls(status_code=400, code=code, message=message, field=field)

    @classmethod
    def unauthorized(cls, message: str = "unauthorized") -> AppError:
        return cls(status_code=401, code="unauthorized", message=message)

    @classmethod
    def forbidden(cls, message: str = "forbidden") -> AppError:
        return cls(status_code=403, code="forbidden", message=message)

    @classmethod
    def not_found(cls, code: str, message: str) -> AppError:
        return cls(status_code=404, code=code, message=message)

    @classmethod
    def quota_exhausted(cls, scene: str) -> AppError:
        return cls(
            status_code=429,
            code="daily_quota_exhausted",
            message=f"daily quota exhausted for {scene}",
            field=scene,
        )

    @classmethod
    def insufficient_credits(cls) -> AppError:
        return cls(status_code=402, code="insufficient_credits", message="insufficient credits")

    @classmethod
    def provider_not_configured(cls, scene: str) -> AppError:
        return cls(
            status_code=501,
            code="provider_not_configured",
            message=f"provider is not configured for {scene}",
            field=scene,
        )


def error_body(error: AppError) -> dict[str, Any]:
    body: dict[str, Any] = {"code": error.code, "detail": error.message}
    if error.field:
        body["field"] = error.field
    return body


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_request: Request, error: AppError) -> JSONResponse:
        return JSONResponse(status_code=error.status_code, content=error_body(error))
