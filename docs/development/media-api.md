# Media and message operations

This describes the implemented API on `main`, covered by network-free regression tests.
No live VK upload, photo replacement or deletion has been verified. The separate Python
3.9 branch has not received these changes yet.

## Upload and send

Use an initialized Bot, for example inside `async with Bot(token) as bot`:

```python
from pathlib import Path

photo = await bot.upload_photo(peer_id, Path("map.png"))
message_id = await bot.send_message(peer_id, "Map", attachment=photo, keyboard=keyboard)

document = await bot.upload_document(peer_id, Path("report.pdf"), title="Report", tags="report")
await bot.send_message(peer_id, "Report", attachment=document)
```

Both upload methods accept `bytes`, `pathlib.Path`, or an open binary file. Pass
`filename="map.png"` or `filename="report.pdf"` with bytes to specify the uploaded name.
Path and named file inputs infer their basename; unnamed inputs default to `photo.png`
or `document.bin`. Filenames must be plain names without directory separators, quotes
or control characters. No file conversion is performed.

`upload_photo` returns `PhotoAttachment`. `upload_document` returns `DocumentAttachment`
for `type="doc"` (default), or `AudioMessageAttachment` for `type="audio_message"`.
Voice encoding/format acceptance remains VK's responsibility; the library does not
record or transcode audio. Graffiti uploads are outside the typed wrapper.

Upload methods save an attachment but do not send a message. `send_message` and
`edit_message` accept a supported `Attachment` object or an existing VK identifier
string. A string may contain VK's comma-separated list. These methods never upload
files. `attachment.to_attachment()` returns the wire identifier, retaining `access_key`.
Voice attachments use the document identifier prefix. Possessing an identifier does
not grant permission to reuse it in another conversation.

## Replace a photograph

```python
updated = await bot.edit_message_media(
    peer_id,
    png_bytes,
    message_id=message_id,
    caption="Updated map",
    keyboard=keyboard,
    filename="map.png",
)
```

Use exactly one of `message_id` or `conversation_message_id`; the latter is sent to
`messages.edit` as `cmid`. Identifiers must be positive integers. `edit_message_media`
accepts a local binary input, a `PhotoAttachment`, or one `photo...` identifier. Existing
photos skip the upload/save stages. Paths must be `Path` objects; strings are identifiers,
not URLs or filesystem paths. This convenience method currently replaces photos only.

For an already saved attachment:

```python
updated = await bot.edit_message(
    peer_id,
    "Updated map",
    conversation_message_id=cmid,
    attachment=photo,
    keyboard=keyboard,
)
```

Both edit methods return `bool` for the VK integer status. Errors propagate. `text=None`
(`caption=None` in the convenience method), `attachment=None` and `keyboard=None` omit
those fields from the request; empty strings are transmitted explicitly. To request
removal of a keyboard, pass `Keyboard(buttons=[], inline=True)`. At least text or an
attachment must be supplied to `edit_message`.

The library does not fetch/merge the previous message. Supply the desired caption,
complete attachment list and keyboard on every edit when preserving them matters.
Omission does not constitute a library guarantee that VK preserves a field. A new
attachment value describes the desired set, not an append operation.

Uploading and editing are separate operations, not a transaction. An edit failure may
leave a saved, unused photo. No cleanup, retry, or fallback send runs automatically;
callers needing to reuse a saved photo after failure should call `upload_photo` and
`edit_message` separately. After a network timeout the remote operation may already
have completed.

See [interactive_map.py](../../examples/interactive_map.py). Its standard-library PNG
renderer creates a synthetic grid; replace it with application rendering code. A lock
serializes each message's full render/upload/edit sequence. One map is active per peer,
only its creator can navigate, and state lasts for the running process. The example
passes caption and keyboard explicitly and never sends a replacement message on failure.

## Read incoming media and location

`Message.attachments` contains the raw JSON dictionaries. `Message.typed_attachments`
returns fresh views reflecting the current raw list; it does not change message JSON
serialization. Do not modify the view to update the raw message.
Each view owns a deep copy, including nested unknown metadata in known payloads,
envelopes and generic fallbacks. Mutating a view does not affect the raw message or
another view; the next read still reflects any edits made directly to the raw list.

```python
from python_vk_bot import DocumentAttachment, PhotoAttachment

for attachment in message.typed_attachments:
    if isinstance(attachment, PhotoAttachment):
        sizes = attachment.photo.sizes
        photo_id = attachment.id
    elif isinstance(attachment, DocumentAttachment):
        filename = attachment.doc.title
        byte_count = attachment.doc.size
```

Supported envelopes are `PhotoAttachment`, `DocumentAttachment`, `VideoAttachment`
and `AudioMessageAttachment`; their payloads are under `photo`, `doc`, `video` and
`audio_message`. Common `id` and `owner_id` properties expose identifiers. Payload
models retain extra metadata, accessible through Pydantic's `model_extra` and
`model_dump()`. Envelope fields are frozen; these are views, not editable message state.

Unknown types and incomplete/malformed known types produce a generic `Attachment`
retaining all original fields. Its identifiers are `None`, and `to_attachment()` raises
`ValueError` rather than guessing a sendable identifier. The raw dictionaries remain
available even when typed parsing cannot represent an attachment.

```python
if message.geo is not None:
    latitude = message.geo.coordinates.latitude
    longitude = message.geo.coordinates.longitude
```

`geo` may be absent or null. A present `Geo` requires `coordinates` with both latitude
and longitude; incomplete coordinates fail event validation. The official broader geo
schema also permits metadata without coordinates; that shape remains outside this
library's typed `Geo` contract. Unknown geo/coordinate fields are retained.
`filters.LOCATION` selects messages with a validated, non-null `geo`.
No `send_location` convenience method is provided.

## Delete one message

```python
deleted = await bot.delete_message(
    peer_id,
    conversation_message_id=cmid,
    delete_for_all=True,
)
```

Supply exactly one positive `message_id` or `conversation_message_id`. The latter uses
VK's `cmids` parameter with `peer_id`. `delete_for_all` defaults to `False`, so recipient-side
deletion is opt-in. `spam=True` explicitly requests spam marking. The method returns
`bool`, propagates VK errors (including per-message errors), and rejects unexpected
result shapes/identifiers. Bulk deletion and user-token `group_id` routing are outside
this wrapper; `Bot.request` remains available for documented methods.

The current VKCOM schema describes an array of per-message result objects. The method
page describes per-message integer success without an explicit JSON example; the
wrapper additionally accepts a mapping keyed by global `message_id`. This mapping path
is not accepted for `cmids`, where the key's identifier scope would be ambiguous.
Live response shapes for both identifier modes remain to be checked.

Unlike a Telegram-style assumption of deleting a message for everyone, VK distinguishes
the deletion scope. Permissions and server-side restrictions can reject removal for
recipients (documented error 924). No Telegram time window is imposed locally.

## Resources and limitations

The reusable `httpx.AsyncClient` performs network I/O asynchronously. Local files are
read in a worker thread before multipart upload; HTTPX never reads a disk file on the
event loop. **The current uploader buffers the whole file in memory.** It is intended
for inputs that fit comfortably in process memory, not streaming multi-gigabyte files.
Avoid unbounded concurrent uploads. No extra runtime dependency is introduced.

Library-opened files close in the worker. Borrowed file objects stay open, are read from
their current position to EOF, and are not rewound. Do not use the same file concurrently.
Cancellation during a local read waits for that read to finish before returning control;
a blocking custom file reader can therefore delay cancellation. Network cancellation
propagates, and owned clients close with Bot's lifecycle.

Only HTTPS upload URLs returned by VK are used, without the community Authorization
header or redirects. HTTPX request logs redact query parameters. HTTP failures use
`HTTPError`, network/timeouts use `NetworkError`, upload rejection uses `UploadError`,
malformed responses use `InvalidResponseError`, and save/edit/delete API errors retain
their code and method. File read/argument errors use `ValueError` or `TypeError`.

For uploads, an injected client must have empty default query parameters and no
default `Content-Type` header (case-insensitive). After the lifecycle check,
`HTTPTransport.upload` raises `ValueError` for either conflict before reading a file
or sending the multipart request. This preserves the server URL's query and lets
HTTPX generate the multipart boundary. Client settings are never modified and the
borrowed client stays caller-owned. Bot upload methods may already have requested
an upload server before this check; the restriction applies to the multipart stage.

These are additive APIs in a pre-1.0 package: the documented signatures and raw-message
representation are the supported contract for this release. Internal helpers are not
stable API; future public changes must be documented. Live VK behavior, availability
of upload URLs and acceptance of particular media are not library stability guarantees.

## Official reference, verified 2026-11-01

Target: VK API **5.199**. The official upload guide lists JPG/PNG/GIF, at most 50 MB,
combined width and height at most 14,000 pixels, and aspect ratio at least 1:20 for
message photos. Its document guide lists files up to 4 GB and excludes MP3 for ordinary
documents; these are VK limits, not a claim that the buffered uploader can practically
handle the largest permitted files. Validation of encoding/dimensions remains server-side.

- [Versions](https://dev.vk.com/ru/reference/versions)
- [Photo upload guide](https://dev.vk.com/ru/api/upload/photo-in-message)
- [Document upload guide](https://dev.vk.com/ru/api/upload/document-in-profile)
- [Photo upload server](https://dev.vk.com/ru/method/photos.getMessagesUploadServer)
- [Save photo](https://dev.vk.com/ru/method/photos.saveMessagesPhoto)
- [Document upload server](https://dev.vk.com/ru/method/docs.getMessagesUploadServer)
- [Save document](https://dev.vk.com/ru/method/docs.save)
- [Edit message](https://dev.vk.com/ru/method/messages.edit)
- [Delete message](https://dev.vk.com/ru/method/messages.delete)
- [VKCOM message responses](https://github.com/VKCOM/vk-api-schema/blob/master/messages/responses.json)
- [VKCOM message objects](https://github.com/VKCOM/vk-api-schema/blob/master/messages/objects.json)
- [VKCOM geo objects](https://github.com/VKCOM/vk-api-schema/blob/master/base/objects.json)

The guides contain older-version examples and the schema and method pages differ in
some details. For example, `messages.edit` lists text limits of 4096 in its method page
and 9000 in the schema; this wrapper does not invent a unified limit or a numeric edit
window. Documented editing failures include permission errors, age restriction (909),
message-kind restriction (920) and pinned-message restriction (949). The declared
`attachment` parameter supports the proposed replacement request, but does not prove
the complete interactive-map scenario works with a particular community token.

## Live integration test

The default `uv run pytest --strict-markers` run discovers only `tests/unit`. Live media
checks are in `tests/integration/test_media_edit.py`, use the registered `integration`
marker, and additionally require `VK_RUN_MEDIA_INTEGRATION=1`. Without that explicit
flag they skip, including when credentials are present or all of `tests/` is collected.

Supply `VK_TEST_TOKEN` and `VK_TEST_PEER_ID` through the environment. The token must be
a community token with the needed photo/message permissions, and the test peer must
already permit messages from this community. Use a dedicated test conversation: each
case sends a synthetic map, replaces it, reads it back, then attempts recipient-side
deletion of only the message it created. It never scans or deletes conversation history.
Saved uploaded photos can remain, and a failed send with an unknown result can leave a
message that cannot safely be identified for cleanup.

```bash
VK_RUN_MEDIA_INTEGRATION=1 uv run pytest --strict-markers -m integration tests/integration/test_media_edit.py
```

The two cases exercise `message_id` and `conversation_message_id`. They check the
original message, then verify that peer/global/conversation identifiers stay the same
while the photo owner/ID pair, text and keyboard label change. `messages.getById` is
used via `Bot.request` only to discover the new message's cmid; subsequent reads use
`Bot.get_message`. A zero or unusable creation ID fails the test rather than pretending
to verify a replacement. Errors and unsuccessful cleanup are visible test failures.

Only test collection and the disabled path have been run locally: **2 skipped**.
There is no live-server result yet. See [verification](verification.md).
