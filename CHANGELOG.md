# Changelog

All notable changes will be documented here, following Keep a Changelog.

## 0.2.0 - 2026-11-01

### Added

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
