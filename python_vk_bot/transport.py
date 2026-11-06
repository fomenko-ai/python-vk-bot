"""Reusable HTTP transport; request credentials never become client defaults."""

from __future__ import annotations

import asyncio
import logging
import math
import re
from collections.abc import Mapping
from contextlib import suppress
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from types import TracebackType
from typing import BinaryIO, Literal, Optional, Union, cast
from urllib.parse import urlsplit

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
    UploadError,
)
from .models.api import APIEnvelope

Parameter: TypeAlias = Union[str, int, float, bool, None]
FileInput: TypeAlias = Union[bytes, Path, BinaryIO]


_HTTP_DATE = re.compile(
    r"(?:"
    r"(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun), [0-9]{2} "
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) [0-9]{4} "
    r"[0-9]{2}:[0-9]{2}:[0-9]{2} GMT"
    r"|(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday), "
    r"[0-9]{2}-(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)-[0-9]{2} "
    r"[0-9]{2}:[0-9]{2}:[0-9]{2} GMT"
    r"|(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun) "
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) (?:[0-9]{2}| [0-9]) "
    r"[0-9]{2}:[0-9]{2}:[0-9]{2} [0-9]{4}"
    r")"
)


def _parse_retry_after(value: Optional[str]) -> Optional[float]:
    """Parse RFC 9110 seconds or HTTP-date without retaining server data."""
    if value is None:
        return None
    value = value.strip(" \t")
    try:
        if re.fullmatch(r"[0-9]+", value):
            seconds = float(value)
        elif _HTTP_DATE.fullmatch(value):
            now = datetime.now(timezone.utc)
            deadline = parsedate_to_datetime(value)
            if deadline.tzinfo is None:
                # The obsolete asctime format has no zone; HTTP defines it as UTC.
                deadline = deadline.replace(tzinfo=timezone.utc)
            if "-" in value:
                # RFC 850's two-digit year is interpreted relative to the current century.
                year = now.year // 100 * 100 + deadline.year % 100
                if year > now.year + 50:
                    year -= 100
            else:
                # The email parser applies a century heuristic even to four-digit years.
                parts = value.split()
                year = int(parts[3] if "," in value else parts[-1])
            deadline = deadline.replace(year=year)
            seconds = max(0.0, (deadline - now).total_seconds())
        else:
            return None
    except (ValueError, TypeError, OverflowError):
        return None
    return seconds if math.isfinite(seconds) else None


def _read_upload(source: Union[Path, BinaryIO]) -> bytes:
    """Read in a worker; Path.read_bytes closes its own file even on failure."""
    try:
        content = source.read_bytes() if isinstance(source, Path) else source.read()
    except (OSError, ValueError):
        raise ValueError("Could not read the upload file") from None
    if not isinstance(content, bytes):
        raise TypeError("Upload files must be opened in binary mode")
    return content


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
        data: Union[Mapping[str, str], None] = None,
        params: Union[Mapping[str, str], None] = None,
        headers: Union[Mapping[str, str], None] = None,
        timeout: Union[float, None] = None,
        files: Union[Mapping[str, tuple[str, bytes]], None] = None,
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
                files=files,
                timeout=self.config.timeout if timeout is None else timeout,
                follow_redirects=False,
                auth=None,
            )
        except httpx.RequestError:
            raise NetworkError("VK HTTP request could not complete") from None
        if not response.is_success:
            raise HTTPError(
                response.status_code,
                retry_after=_parse_retry_after(response.headers.get("Retry-After")),
            )
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

    async def upload(
        self,
        server: str,
        source: FileInput,
        *,
        field: Literal["photo", "file"],
        filename: Union[str, None] = None,
    ) -> JsonValue:
        """Buffer a local file off-loop, then upload without community credentials.

        Memory usage is proportional to file size. Borrowed files are read from their
        current position and remain open. Cancellation drains a pending local read
        before returning ownership of a borrowed file to its caller.
        """
        if not self._started or self._client is None:
            raise LifecycleError("Initialize the bot or use its async context manager")
        if self._client.params:
            raise ValueError("Upload clients must not define default query parameters")
        if "content-type" in self._client.headers:
            raise ValueError("Upload clients must not define a default Content-Type header")
        try:
            # HTTPX percent-encodes an unmatched '[' in a host; reject malformed
            # bracketed hosts before that normalization can turn them into a request.
            urlsplit(server)
            url = httpx.URL(server)
        except (httpx.InvalidURL, ValueError):
            raise InvalidResponseError("Invalid upload server URL") from None
        if url.scheme != "https" or not url.host or url.userinfo or url.fragment:
            raise InvalidResponseError("Unexpected upload server URL")
        if not isinstance(source, (bytes, Path)) and not callable(getattr(source, "read", None)):
            raise TypeError("Provide bytes, a Path, or a binary file")
        if filename is None:
            name = getattr(source, "name", None)
            filename = Path(name).name if isinstance(name, str) else None
        if filename is None:
            filename = "photo.png" if field == "photo" else "document.bin"
        if (
            not filename
            or filename in {".", ".."}
            or any(char in filename for char in '/\\"')
            or any(ord(char) < 32 or ord(char) == 127 for char in filename)
        ):
            raise ValueError("filename must be a plain, nonempty file name")
        if isinstance(source, bytes):
            content = source
        else:
            reading = asyncio.create_task(asyncio.to_thread(_read_upload, source))
            try:
                content = await asyncio.shield(reading)
            except asyncio.CancelledError:
                # Repeated cancellation must not return a borrowed file while the
                # worker is still consuming it. Retrieve any read exception as well.
                while not reading.done():
                    with suppress(Exception, asyncio.CancelledError):
                        await asyncio.shield(reading)
                with suppress(Exception):
                    reading.result()
                raise
        if not content:
            raise ValueError("Cannot upload an empty file")
        payload = await self._request("POST", server, files={field: (filename, content)})
        if isinstance(payload, dict) and ("error" in payload or "error_code" in payload):
            raise UploadError("VK upload server rejected the file")
        return payload

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
