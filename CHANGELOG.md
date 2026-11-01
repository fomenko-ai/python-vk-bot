# Changelog

All notable changes will be documented here, following Keep a Changelog.

## 0.1.1 - 2026-11-01

### Changed

- The `compat/py39` branch supports Python 3.9–3.14 with compatible annotations, explicit
  polling cleanup, lazy creation of application locks and Python-dependent dependencies.
  See [compatibility status](docs/development/python-compatibility.md) for verified versions.
- Context is a regular dataclass on the compatibility branch.
- Callback uses an optional timeout backport on Python 3.9/3.10; Python >=3.11 uses asyncio.

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
