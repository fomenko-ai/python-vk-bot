# 0002: Media uploads and additive attachment views

Status: accepted
Date: 2026-11-01
Task: media-api

## Context

The approved media plan needs upload/save operations and replacement of a message's
photo without changing the raw attachment contract. Existing Bot, HTTPTransport and
Pydantic boundaries already provide the required separation. PTB 22.8 is the design
reference; VK has distinct upload/save stages, peer IDs and editing restrictions.

## Decision

Keep orchestration in Bot and multipart requests in the existing HTTPTransport. Add
typed attachment envelopes in models/attachments.py, preserving Message.attachments
and exposing fresh typed_attachments views. Unknown/incomplete incoming attachments
remain generic envelopes; upload/save responses require the expected complete model.
Typed envelopes are frozen and are not a second mutable copy of message state.

Use the existing HTTPX client and its ownership/error policy. Read local files in a
worker before upload; bytes are buffered in memory so HTTPX's multipart encoder never
performs synchronous disk reads on the event loop. This initial uploader is for inputs
that fit in memory. Borrowed file objects remain caller-owned; cancellation drains an
ongoing local read. No client, dispatcher or dependency replacement is required.

Expose photo replacement as an explicit upload followed by messages.edit, with a
photo-only convenience method. Saved identifiers skip uploading. Omitted fields are
omitted on the wire, without a fetch/merge step or preservation promise. There is no
automatic fallback send, retry, cleanup or transactional guarantee across stages.

## Alternatives Considered

### Replace Message.attachments with a discriminated union

This would give direct typed access but break dictionary consumers and make new or
malformed attachment kinds a risk to otherwise processable events.

### Introduce a separate media service and streaming multipart implementation

Streaming would bound memory for large documents, but requires a new async multipart
encoder or dependency plus stream/cancellation semantics. The approved map scenario
uses small generated images; buffered file input is explicit and retains HTTPX encoding.
A separate service currently adds no independent lifecycle or transport need.

## Consequences

### Positive

- Raw message representation remains stable and unknown VK fields survive.
- Existing transport lifecycle and injected-client checks continue to apply.
- Callers control retries, failed-edit handling and explicit keyboard/caption values.

### Negative

- File buffering uses memory proportional to upload size.
- A blocking custom file object's read can delay cancellation.
- Upload/save/edit are separate remote mutations; unused saved files may remain.
- A real-community integration test is needed to verify image replacement.

## Documentation

- [Media API](../development/media-api.md)
- [PTB reference](../architecture/python-telegram-bot-compatibility.md)
- [VK API support](../development/api-compatibility.md)
