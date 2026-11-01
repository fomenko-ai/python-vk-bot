"""Framework-neutral Callback authentication and an optional Starlette HTTP adapter."""

from __future__ import annotations

import asyncio
import hmac
import json
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Union

from pydantic import JsonValue, SecretStr

from .application import Application
from .errors import CallbackAuthenticationError, InvalidUpdateError, LifecycleError
from .models import Update

if TYPE_CHECKING:
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import Response


class Callback:
    def __init__(
        self,
        application: Application,
        *,
        secret: Union[str, SecretStr],
        confirmation_code: Union[str, SecretStr],
    ) -> None:
        self.application = application
        self._secret = secret if isinstance(secret, SecretStr) else SecretStr(secret)
        self._confirmation_code = (
            confirmation_code
            if isinstance(confirmation_code, SecretStr)
            else SecretStr(confirmation_code)
        )
        if not self._secret.get_secret_value() or not self._confirmation_code.get_secret_value():
            raise ValueError("Callback secret and confirmation code must be nonempty")

    async def handle(self, payload: dict[str, JsonValue]) -> str:
        secret = payload.get("secret")
        group_id = payload.get("group_id")
        if (
            type(group_id) is not int
            or group_id != self.application.group_id
            or not isinstance(secret, str)
            or not hmac.compare_digest(secret.encode(), self._secret.get_secret_value().encode())
        ):
            raise CallbackAuthenticationError("Callback authentication failed")
        if payload.get("type") == "confirmation":
            return self._confirmation_code.get_secret_value()
        update = Update.from_dict(payload)
        await self.application.process_update(update)
        return "ok"

    def create_app(
        self,
        *,
        path: str = "/callback",
        max_body_bytes: int = 1_048_576,
        max_pending: int = 32,
        request_timeout: float = 10.0,
    ) -> Starlette:
        """Create an ASGI app. Limits are local policy, not VK API limits.

        The host must run ASGI lifespan; it owns the listener and TLS configuration.
        """
        from starlette.applications import Starlette
        from starlette.requests import ClientDisconnect
        from starlette.responses import PlainTextResponse
        from starlette.routing import Route

        if sys.version_info >= (3, 11):
            from asyncio import timeout
        else:
            from async_timeout import timeout

        if max_body_bytes <= 0 or max_pending <= 0 or request_timeout <= 0:
            raise ValueError("Callback resource limits must be positive")
        pending = 0

        @asynccontextmanager
        async def lifespan(app: Starlette) -> AsyncGenerator[None, None]:
            async with self.application:
                yield

        async def endpoint(request: Request) -> Response:
            nonlocal pending
            if pending >= max_pending:
                return PlainTextResponse("busy", status_code=503)
            pending += 1
            try:
                async with timeout(request_timeout):
                    body = bytearray()
                    async for chunk in request.stream():
                        if len(body) + len(chunk) > max_body_bytes:
                            return PlainTextResponse("too large", status_code=413)
                        body.extend(chunk)
                    try:
                        payload = json.loads(body)
                    except (ValueError, UnicodeDecodeError):
                        return PlainTextResponse("invalid JSON", status_code=400)
                    if not isinstance(payload, dict):
                        return PlainTextResponse("invalid event", status_code=400)
                    return PlainTextResponse(await self.handle(payload))
            except CallbackAuthenticationError:
                return PlainTextResponse("forbidden", status_code=403)
            except InvalidUpdateError:
                return PlainTextResponse("invalid event", status_code=400)
            except (asyncio.TimeoutError, LifecycleError):
                return PlainTextResponse("unavailable", status_code=503)
            except ClientDisconnect:
                return PlainTextResponse("disconnected", status_code=400)
            except Exception:
                # Do not expose user code exceptions or echo private request data.
                return PlainTextResponse("processing failed", status_code=500)
            finally:
                pending -= 1

        return Starlette(routes=[Route(path, endpoint, methods=["POST"])], lifespan=lifespan)
