"""Reusable HTTP transport; request credentials never become client defaults."""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from types import TracebackType
from typing import Optional, Union, cast

import httpx
from pydantic import JsonValue, SecretStr, ValidationError
from typing_extensions import Self, TypeAlias

from ._config import TransportConfig
from .errors import (
    APIError,
    HTTPError,
    InvalidResponseError,
    LifecycleError,
    NetworkError,
    RateLimitError,
)
from .models.api import APIEnvelope

Parameter: TypeAlias = Union[str, int, float, bool, None]


class _RedactQuery(logging.Filter):
    """HTTPX INFO logs otherwise expose the Long Poll key in request URLs."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(
                value.copy_with(query=None)
                if isinstance(value, httpx.URL) and value.query
                else value
                for value in record.args
            )
        return True


class HTTPTransport:
    """Own a client or borrow an injected client without closing it."""

    def __init__(
        self, config: TransportConfig, *, client: Optional[httpx.AsyncClient] = None
    ) -> None:
        self.config = config
        self._client = client
        self._owns_client = client is None
        self._started = False
        httpx_logger = logging.getLogger("httpx")
        if not any(isinstance(item, _RedactQuery) for item in httpx_logger.filters):
            httpx_logger.addFilter(_RedactQuery())

    async def initialize(self) -> None:
        if self._started:
            return
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.config.timeout)
        if self._client.is_closed:
            raise LifecycleError("The injected HTTP client is closed")
        if "authorization" in self._client.headers:
            raise ValueError("Injected clients must not define a default Authorization header")
        if {"access_token", "key", "secret"}.intersection(self._client.params):
            raise ValueError("Injected clients must not define credential query parameters")
        self._started = True

    async def shutdown(self) -> None:
        self._started = False
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> Self:
        await self.initialize()
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        await self.shutdown()

    async def _request(
        self,
        method: str,
        url: str,
        *,
        data: Optional[Mapping[str, str]] = None,
        params: Optional[Mapping[str, str]] = None,
        headers: Optional[Mapping[str, str]] = None,
        timeout: Optional[float] = None,
    ) -> JsonValue:
        if not self._started or self._client is None:
            raise LifecycleError("Initialize the bot or use its async context manager")
        try:
            response = await self._client.request(
                method,
                url,
                data=data,
                params=params,
                headers=headers,
                timeout=self.config.timeout if timeout is None else timeout,
                follow_redirects=False,
                auth=None,
            )
        except httpx.RequestError:
            raise NetworkError("VK HTTP request could not complete") from None
        if not response.is_success:
            raise HTTPError(response.status_code)
        try:
            return cast(JsonValue, response.json())
        except ValueError:
            raise InvalidResponseError("VK returned invalid JSON") from None

    async def call(self, method: str, parameters: Mapping[str, Parameter]) -> JsonValue:
        if re.fullmatch(r"[A-Za-z]+\.[A-Za-z]+", method) is None:
            raise ValueError("Expected a VK method name such as messages.send")
        if {"v", "access_token"}.intersection(parameters):
            raise ValueError("Version and credentials belong to the transport configuration")
        data = {
            key: str(int(value)) if isinstance(value, bool) else str(value)
            for key, value in parameters.items()
            if value is not None
        }
        data["v"] = self.config.api_version
        payload = await self._request(
            "POST",
            f"https://api.vk.ru/method/{method}",
            data=data,
            headers={"Authorization": f"Bearer {self.config.token.get_secret_value()}"},
        )
        try:
            envelope = APIEnvelope.model_validate(payload)
        except ValidationError:
            raise InvalidResponseError("Invalid VK API envelope") from None
        if envelope.error is not None:
            code = envelope.error.error_code
            error_type = RateLimitError if code == 6 else APIError
            raise error_type(code, method)
        if "response" not in envelope.model_fields_set:
            raise InvalidResponseError("VK API envelope has no response")
        return envelope.response

    async def poll(self, server: str, *, key: SecretStr, ts: str, wait: int) -> JsonValue:
        url = httpx.URL(server)
        if url.scheme != "https" or not url.host or url.userinfo or url.query or url.fragment:
            raise InvalidResponseError("Unexpected Long Poll server URL")
        # The community token is only sent to api.vk.ru, never to the polling server.
        return await self._request(
            "GET",
            server,
            params={"act": "a_check", "key": key.get_secret_value(), "ts": ts, "wait": str(wait)},
            timeout=max(self.config.timeout, wait + 10.0),
        )
