import asyncio
import io
import logging
import threading
from contextlib import ExitStack
from email import policy
from email.message import EmailMessage, MIMEPart
from email.parser import BytesParser
from pathlib import Path
from typing import Literal

import httpx
import pytest
from pydantic import JsonValue

from python_vk_bot import AudioMessageAttachment, Bot, DocumentAttachment, PhotoAttachment
from python_vk_bot.errors import (
    APIError,
    HTTPError,
    InvalidResponseError,
    LifecycleError,
    NetworkError,
    RateLimitError,
    UploadError,
)
from python_vk_bot.transport import FileInput

from .helpers import MockAPI, form, queue_photo_upload


def multipart_file(request: httpx.Request) -> MIMEPart:
    wire = (
        f"Content-Type: {request.headers['content-type']}\r\nMIME-Version: 1.0\r\n\r\n".encode()
        + request.content
    )
    message = BytesParser(policy=policy.default).parsebytes(wire)
    assert isinstance(message, EmailMessage)
    parts = list(message.iter_parts())
    assert len(parts) == 1
    return parts[0]


@pytest.mark.parametrize("source_kind", ["bytes", "path", "file"])
@pytest.mark.parametrize("explicit_name", [False, True])
async def test_photo_upload_multipart_and_ownership(
    bot: Bot,
    api: MockAPI,
    client: httpx.AsyncClient,
    tmp_path: Path,
    source_kind: str,
    explicit_name: bool,
    caplog: pytest.LogCaptureFixture,
) -> None:
    content = b"\x89PNG\r\n\x1a\nsynthetic-binary\x00\xff"
    path = tmp_path / "карта.png"
    path.write_bytes(content)
    queue_photo_upload(api)
    with ExitStack() as stack, caplog.at_level(logging.INFO, logger="httpx"):
        source: FileInput
        if source_kind == "bytes":
            source = content
        elif source_kind == "path":
            source = path
        else:
            source = stack.enter_context(path.open("rb"))
        async with bot:
            photo = await bot.upload_photo(
                7, source, filename="override.png" if explicit_name else None
            )
        if source_kind == "file":
            assert not isinstance(source, (bytes, Path))
            assert not source.closed
            assert source.tell() == len(content)
    assert isinstance(photo, PhotoAttachment)
    assert photo.to_attachment() == "photo-42_11_photo-key"
    assert photo.photo.model_extra == {"extra": 1}
    assert not client.is_closed
    assert len(api.requests) == 3
    discovery, upload, save = api.requests
    assert discovery.url.path == "/method/photos.getMessagesUploadServer"
    assert form(discovery)["peer_id"] == "7"
    assert discovery.headers["authorization"] == "Bearer synthetic-community-token"
    assert upload.method == "POST"
    assert upload.url.params["hash"] == "upload-secret"
    assert "authorization" not in upload.headers
    assert "access_token" not in upload.url.params
    assert "v" not in upload.url.params
    assert "synthetic-community-token" not in upload.content.decode(errors="replace")
    part = multipart_file(upload)
    assert part.get_param("name", header="content-disposition") == "photo"
    inferred_name = "photo.png" if source_kind == "bytes" else path.name
    assert part.get_filename() == ("override.png" if explicit_name else inferred_name)
    assert part.get_payload(decode=True) == content
    assert save.url.path == "/method/photos.saveMessagesPhoto"
    assert form(save) == {
        "v": "5.199",
        "server": "5",
        "photo": "opaque-photo",
        "hash": "save-secret",
    }
    assert "upload-secret" not in caplog.text
    assert "save-secret" not in caplog.text


@pytest.mark.parametrize("kind", ["doc", "audio_message"])
async def test_document_upload_and_save_parameters(
    bot: Bot, api: MockAPI, kind: Literal["doc", "audio_message"]
) -> None:
    api.add({"response": {"upload_url": "https://upload.example/document"}})
    api.add({"file": "opaque-document"})
    api.add({"response": {"type": kind, kind: {"id": 12, "owner_id": -42, "extra": True}}})
    with io.BytesIO(b"skip-document-bytes") as source:
        source.seek(5)
        async with bot:
            attachment = await bot.upload_document(
                7, source, filename="report.pdf", type=kind, title="Report", tags="report,map"
            )
        assert not source.closed
        assert source.tell() == len(b"skip-document-bytes")
    assert isinstance(attachment, DocumentAttachment if kind == "doc" else AudioMessageAttachment)
    assert attachment.to_attachment() == "doc-42_12"
    assert attachment.media.model_extra == {"extra": True}
    assert form(api.requests[0]) == {"v": "5.199", "peer_id": "7", "type": kind}
    part = multipart_file(api.requests[1])
    assert part.get_param("name", header="content-disposition") == "file"
    assert part.get_filename() == "report.pdf"
    assert part.get_payload(decode=True) == b"document-bytes"
    assert "authorization" not in api.requests[1].headers
    assert form(api.requests[2]) == {
        "v": "5.199",
        "file": "opaque-document",
        "title": "Report",
        "tags": "report,map",
    }


@pytest.mark.parametrize("kind", ["photo", "document"])
@pytest.mark.parametrize("stage", ["discovery", "save"])
@pytest.mark.parametrize("code", [5, 6])
async def test_upload_api_errors_propagate_without_retry(
    bot: Bot, api: MockAPI, kind: str, stage: str, code: int
) -> None:
    if stage == "save":
        api.add({"response": {"upload_url": "https://upload.example/file"}})
        api.add(
            {"server": 1, "photo": "private-data", "hash": "private-hash"}
            if kind == "photo"
            else {"file": "private-data"}
        )
    api.add({"error": {"error_code": code, "error_msg": "private-server-message"}})
    upload = bot.upload_photo if kind == "photo" else bot.upload_document
    async with bot:
        with pytest.raises(RateLimitError if code == 6 else APIError) as caught:
            await upload(7, b"content")
    assert caught.value.code == code
    expected_method = (
        ("photos.getMessagesUploadServer" if stage == "discovery" else "photos.saveMessagesPhoto")
        if kind == "photo"
        else ("docs.getMessagesUploadServer" if stage == "discovery" else "docs.save")
    )
    assert caught.value.method == expected_method
    assert "private" not in str(caught.value)
    assert len(api.requests) == (1 if stage == "discovery" else 3)


@pytest.mark.parametrize("status", [302, 401, 429, 500])
async def test_upload_http_failure_never_saves_or_retries(
    bot: Bot, api: MockAPI, status: int
) -> None:
    api.add({"response": {"upload_url": "https://upload.example/file"}})
    api.responses.append(
        httpx.Response(status, headers={"location": "https://redirect.example/"}, json={})
    )
    async with bot:
        with pytest.raises(HTTPError) as caught:
            await bot.upload_photo(7, b"image")
    assert caught.value.status_code == status
    assert len(api.requests) == 2


@pytest.mark.parametrize("error", [httpx.ReadTimeout, httpx.WriteTimeout, httpx.ConnectError])
async def test_upload_network_failure_is_safe(
    bot: Bot, api: MockAPI, error: type[httpx.RequestError]
) -> None:
    api.add({"response": {"upload_url": "https://upload.example/file"}})
    api.responses.append(error("private-url"))
    async with bot:
        with pytest.raises(NetworkError) as caught:
            await bot.upload_document(7, b"document")
    assert "private" not in str(caught.value)
    assert len(api.requests) == 2


@pytest.mark.parametrize(
    ("payload", "error_class"),
    [
        ({"error": "private-rejection"}, UploadError),
        ({"error_code": 42, "error_msg": "private-rejection"}, UploadError),
        (None, InvalidResponseError),
        ([], InvalidResponseError),
        ({"server": 1, "photo": "private", "hash": ""}, InvalidResponseError),
        ({"server": "1", "photo": "private", "hash": "hash"}, InvalidResponseError),
        ({"photo": "private", "hash": "hash"}, InvalidResponseError),
    ],
)
async def test_invalid_photo_upload_responses_stop_before_save(
    bot: Bot, api: MockAPI, payload: JsonValue, error_class: type[Exception]
) -> None:
    api.add({"response": {"upload_url": "https://upload.example/file"}})
    api.add(payload)
    async with bot:
        with pytest.raises(error_class) as caught:
            await bot.upload_photo(7, b"image")
    assert "private" not in str(caught.value)
    assert len(api.requests) == 2


async def test_upload_invalid_json(bot: Bot, api: MockAPI) -> None:
    api.add({"response": {"upload_url": "https://upload.example/file"}})
    api.responses.append(httpx.Response(200, content=b"private-not-json"))
    async with bot:
        with pytest.raises(InvalidResponseError, match="invalid JSON"):
            await bot.upload_document(7, b"document")
    assert len(api.requests) == 2


@pytest.mark.parametrize("payload", [None, [], {}, {"file": ""}, {"file": 1}])
async def test_invalid_document_upload_response(bot: Bot, api: MockAPI, payload: JsonValue) -> None:
    api.add({"response": {"upload_url": "https://upload.example/file"}})
    api.add(payload)
    async with bot:
        with pytest.raises(InvalidResponseError):
            await bot.upload_document(7, b"document")
    assert len(api.requests) == 2


@pytest.mark.parametrize("payload", [[], {}, [{"id": 1}], [{"id": 1, "owner_id": 0}], [{}, {}]])
async def test_invalid_saved_photo(bot: Bot, api: MockAPI, payload: JsonValue) -> None:
    api.add({"response": {"upload_url": "https://upload.example/file"}})
    api.add({"server": 1, "photo": "opaque", "hash": "hash"})
    api.add({"response": payload})
    async with bot:
        with pytest.raises(InvalidResponseError):
            await bot.upload_photo(7, b"image")
    assert len(api.requests) == 3


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {},
        {"type": "audio_message", "audio_message": {"id": 1, "owner_id": 7}},
        {"type": "doc", "doc": {"id": True, "owner_id": 7}},
    ],
)
async def test_invalid_saved_document(bot: Bot, api: MockAPI, payload: JsonValue) -> None:
    api.add({"response": {"upload_url": "https://upload.example/file"}})
    api.add({"file": "opaque"})
    api.add({"response": payload})
    async with bot:
        with pytest.raises(InvalidResponseError):
            await bot.upload_document(7, b"document")


@pytest.mark.parametrize(
    "server",
    [
        "http://upload.example/file",
        "https://user:password@upload.example/",
        "https://upload.example/#secret",
        "https://",
        "https://[bad",
        "",
    ],
)
async def test_unsafe_upload_urls_rejected(bot: Bot, api: MockAPI, server: str) -> None:
    api.add({"response": {"upload_url": server}})
    async with bot:
        with pytest.raises(InvalidResponseError):
            await bot.upload_photo(7, b"image")
    assert len(api.requests) == 1


@pytest.mark.parametrize("filename", ["", "..", "../image.png", "a\\b", "a\r\nb", 'a"b'])
async def test_invalid_upload_filename(bot: Bot, api: MockAPI, filename: str) -> None:
    async with bot:
        with pytest.raises(ValueError, match="filename"):
            await bot.transport.upload(
                "https://upload.example/", b"image", field="photo", filename=filename
            )
    assert not api.requests


async def test_upload_lifecycle_and_local_file_errors(
    bot: Bot, api: MockAPI, tmp_path: Path
) -> None:
    with pytest.raises(LifecycleError):
        await bot.transport.upload("https://upload.example/", b"image", field="photo")
    async with bot:
        with pytest.raises(ValueError, match="empty"):
            await bot.transport.upload("https://upload.example/", b"", field="photo")
        with pytest.raises(ValueError, match="read the upload file") as caught:
            await bot.transport.upload(
                "https://upload.example/", tmp_path / "private-missing", field="photo"
            )
        assert "private" not in str(caught.value)
        with io.StringIO("text") as text_file, pytest.raises(TypeError, match="binary"):
            await bot.transport.upload(
                "https://upload.example/",
                text_file,  # ty: ignore[invalid-argument-type] -- invalid input boundary
                field="photo",
            )
    assert not api.requests


@pytest.mark.parametrize("default", ["params", "Content-Type", "cOnTeNt-TyPe"])
async def test_upload_rejects_conflicting_client_defaults_before_reading(
    default: str, api: MockAPI
) -> None:
    params = {"trace": "private-value"} if default == "params" else {}
    headers = {} if default == "params" else {default: "application/json"}
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(api), params=params, headers=headers
    ) as client:
        original_params = httpx.QueryParams(client.params)
        original_headers = httpx.Headers(client.headers)
        with io.BytesIO(b"image") as source:
            bot = Bot("synthetic-token", client=client)
            with pytest.raises(LifecycleError):
                await bot.transport.upload("https://upload.example/", source, field="photo")
            async with bot:
                with pytest.raises(ValueError, match="default") as caught:
                    await bot.transport.upload(
                        "https://upload.example/?hash=private-url", source, field="photo"
                    )
                assert "private" not in str(caught.value)
                assert source.tell() == 0
                assert not source.closed
            assert not client.is_closed
        assert client.params == original_params
        assert client.headers == original_headers
    assert not api.requests


async def test_file_read_runs_off_loop_and_repeated_cancellation_drains_it(
    bot: Bot, api: MockAPI
) -> None:
    loop = asyncio.get_running_loop()
    entered = asyncio.Event()
    release = threading.Event()
    thread_ids: list[int] = []

    class PendingFile(io.BytesIO):
        def read(self, size: int | None = -1, /) -> bytes:
            thread_ids.append(threading.get_ident())
            loop.call_soon_threadsafe(entered.set)
            if not release.wait(timeout=5):
                raise TimeoutError("Test did not release the reader")
            return super().read(size)

    with PendingFile(b"image") as source:
        async with bot, asyncio.timeout(3):
            task = asyncio.create_task(
                bot.transport.upload("https://upload.example/", source, field="photo")
            )
            try:
                await entered.wait()
                assert len(thread_ids) == 1
                assert thread_ids[0] != threading.get_ident()
                task.cancel()
                await asyncio.sleep(0)
                task.cancel()
                await asyncio.sleep(0)
                assert not task.done()
            finally:
                release.set()
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            assert source.tell() == len(b"image")
            assert not source.closed
    assert not api.requests


async def test_network_cancellation_during_upload_never_saves() -> None:
    entered = asyncio.Event()
    released = asyncio.Event()
    requests: list[httpx.Request] = []

    async def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json={"response": {"upload_url": "https://upload.example/"}})
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            released.set()
        raise AssertionError("Unreachable")

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        async with Bot("synthetic-token", client=client) as bot, asyncio.timeout(2):
            task = asyncio.create_task(bot.upload_photo(7, b"image"))
            await entered.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        assert not client.is_closed
    assert released.is_set()
    assert len(requests) == 2
