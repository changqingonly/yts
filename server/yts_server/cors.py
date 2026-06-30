from __future__ import annotations

import logging
from collections.abc import Sequence

from starlette.datastructures import Headers
from starlette.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)


class DiagnosticCORSMiddleware(CORSMiddleware):
    """CORSMiddleware that logs the exact reason for preflight rejections."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        allow_origins: Sequence[str] = (),
        allow_methods: Sequence[str] = ("GET",),
        allow_headers: Sequence[str] = (),
    ) -> None:
        super().__init__(
            app,
            allow_origins=allow_origins,
            allow_methods=allow_methods,
            allow_headers=allow_headers,
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        origin = headers.get("origin")
        if origin is None:
            await self.app(scope, receive, send)
            return

        method = scope["method"]
        if method == "OPTIONS" and "access-control-request-method" in headers:
            response = self.preflight_response(request_headers=headers)
            if response.status_code >= 400:
                logger.warning(
                    "CORS preflight rejected path=%s origin=%s request_method=%s "
                    "request_headers=%s failures=%s",
                    scope["path"],
                    origin,
                    headers["access-control-request-method"],
                    headers.get("access-control-request-headers", ""),
                    ",".join(self._preflight_failures(headers)),
                )
            await response(scope, receive, send)
            return

        await self.simple_response(scope, receive, send, request_headers=headers)

    def _preflight_failures(self, request_headers: Headers) -> list[str]:
        requested_origin = request_headers["origin"]
        requested_method = request_headers["access-control-request-method"]
        requested_headers = request_headers.get("access-control-request-headers")
        requested_private_network = request_headers.get("access-control-request-private-network")

        failures: list[str] = []
        if not self.is_allowed_origin(origin=requested_origin):
            failures.append("origin")
        if requested_method not in self.allow_methods:
            failures.append("method")
        if requested_headers is not None and not self.allow_all_headers:
            for header in [h.lower() for h in requested_headers.split(",")]:
                if header.strip() not in self.allow_headers:
                    failures.append("headers")
                    break
        if requested_private_network is not None and not self.allow_private_network:
            failures.append("private-network")
        return failures
