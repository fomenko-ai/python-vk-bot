# Changelog

All notable changes will be documented here, following Keep a Changelog.

## Unreleased

-

## 0.6.0 - 2026-11-06

### Added

- `OpenLinkButton` and `LocationButton` with automatic payload serialization, mixed
  typed/raw keyboards, and `ButtonType.OPEN_LINK` / `ButtonType.LOCATION` values.
- `ShowSnackbar` for typed callback answers through `Bot.send_message_event_answer`,
  validating VK's 90-character text limit while retaining raw mapping support.
- Optional `HTTPError.retry_after` in seconds, read from HTTP `Retry-After` integer
  seconds or HTTP-date. No automatic retries or waits are added; VK API error 6
  retains its separate `RateLimitError` behavior.

## 0.5.0 - 2026-11-05

### Added

- Typed support for all five VK Donut subscription Callback events through
  `Update.donut_subscription`, subscriber user context, `DonutSubscriptionHandler`
  and composable filters on Python 3.9–3.14. See the [Donut guide](docs/development/donut.md)
  and Callback example. These events report changes without synchronizing paid access.

### Fixed

- Concurrent graceful stop and polling-runner cancellation wait for Long Poll cleanup
  without interrupting it with a second cancellation request.

## 0.4.0 - 2026-11-03

### Added

- `ApplicationHandlerStop` to finish the current event successfully and skip later groups.
- `TypeHandler` and a bounded `Application.update_queue` for internal Python objects and
  VK updates, with explicit user/peer state scopes and `Context.event`.
- `Application.create_task` for owned finite tasks and workers cancelled on stop.
- A once-per-run `post_stop` hook before Bot shutdown, and a local background-result example.

### Changed

- Event processing uses a unified serial FIFO. Callback acknowledgement still waits for
  dispatch; request cancellation cancels that event's pending or active execution.
- **Breaking:** after `stop()`, complete `shutdown()` and `initialize()` before starting
  another run. Registration stays closed until shutdown completes. See the
  [lifecycle and queue contracts](docs/development/event-processing.md#lifecycle-and-cleanup).

## 0.3.0 - 2026-11-02

### Added

- Pydantic `TextButton` and `CallbackButton` models with automatic dictionary/model
  payload serialization and string-valued `ButtonColor` / `ButtonType` enums.
  Keyboards also accept raw VK button dictionaries on Python 3.9–3.14.
  See the [keyboard API](docs/development/keyboards.md).

## 0.2.0 - 2026-11-01

### Changed

- The `compat/py39` branch supports Python 3.9–3.14 with compatible annotations, explicit
  polling cleanup, lazy creation of application locks and Python-dependent dependencies.
  See [compatibility status](docs/development/python-compatibility.md) for verified versions.
- Context is a regular dataclass on the compatibility branch.
- Callback uses an optional timeout backport on Python 3.9/3.10; Python >=3.11 uses asyncio.

- An ordinary and inline keyboard example, with setup and usage instructions for all
  examples in the [examples guide](examples/README.md).
- Photo and document uploads from bytes, paths and binary files, with typed saved
  attachments and document/voice upload selection.
- Typed incoming photo, document, video and voice views through
  `Message.typed_attachments`, preserving raw attachments and unknown fields.
- Attachment support in message editing, a photo replacement convenience method and
  explicit message deletion. See [media contracts and limits](docs/development/media-api.md).
- An interactive PNG map example with serialized navigation updates. Live VK photo
  replacement remains unverified; an opt-in integration test is available.
- Installation and compatibility guidance for the separate `main` (Python >=3.14)
  and `compat/py39` (tested on Python 3.9–3.14) branches. See the
  [branch comparison](docs/development/python-compatibility.md).
- Repository, documentation, issue tracker and changelog links in package metadata.

### Fixed

- Isolate nested attachment metadata from raw message data when creating typed views.
- Reject conflicting injected-client defaults before multipart uploads instead of
  sending malformed requests. See [client restrictions](docs/development/media-api.md#resources-and-limitations).

## 0.1.0 - 2026-10-31

### Added

- Internal vk-api-upgrade Agent Skill for maintainers to audit VK API compatibility and
  implement approved upgrades.
- Bundled telegram-to-vk Agent Skill and migration reference in Python distributions,
  discoverable with `uvx library-skills` after package installation.
- Agent Skills documentation covering installation, AI agent setup, usage and approval rules.
- Public BotSettings based on pydantic-settings, with VK_* environment variables, explicit
  dotenv loading and subclass extensions; Long Poll and Callback examples use settings.
- Async Bot and Application with explicit lifecycle, ordered handlers, composable filters,
  scoped context data and error callbacks.
- Pydantic v2 message/event models preserving unmodeled VK fields and raw event objects.
- Callback authentication, confirmation and an optional ASGI receiver with resource limits.
- Bounded in-memory suppression of successfully processed duplicate events.
- Python 3.14 package baseline and VK API 5.199 support, verified against official
  documentation on 2026-10-31.
- Reusable HTTPX AsyncClient sessions with explicit ownership and timeouts.
- Asynchronous Long Poll with iterative session recovery.
- Messaging methods with nonzero int32 random_id generation, editing by message ID or cmid,
  and forwarding from the source conversation.

### Security

- Callback group/secret checks occur before event dispatch.
- Credentials and payloads are excluded from library error logs; HTTPX request log query
  strings are redacted to protect Long Poll keys.
