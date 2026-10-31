# 0001: A modular async framework on Python 3.14

Status: accepted
Date: 2026-10-31
Task: modernize-framework

## Context

This new library needs asynchronous HTTP, VK method wrappers, event delivery, dispatch,
and user state with clear ownership boundaries. The user approved a modular architecture
and selected Python 3.14. Test changes require approval of the implemented main code.

## Decision

Use HTTPX with explicit resource ownership, Pydantic v2 at data boundaries, Bot for VK
methods, and Application for serial dispatch and lifecycle. Keep Long Poll and Callback
delivery separate. Use an optional Starlette adapter for Callback HTTP reception; no
server starts implicitly. Implement the documented method coverage and routing concepts.
Keep the root package layout. Start with Python >=3.14 and assess
other versions only after implementation and its tests are complete.

Use an awaitable run_polling, explicit async context management, ordered handler groups,
user/peer/application state, and bounded in-memory duplicate suppression. No persistent
delivery guarantee, background worker pool, builder, or conversation framework is added.

## Alternatives Considered

### Combine responsibilities in one module

Fewer modules, but couples network failures, state, and dispatch and makes independent
verification of each responsibility harder.

### aiohttp and a built-in server

Supports pooling and client/server HTTP. HTTPX fits the existing request shape and allows
MockTransport injection. An optional Callback adapter avoids a mandatory server dependency.

## Consequences

### Positive

- Independently understandable components and fully awaited I/O.
- Focused abstractions without unnecessary code generation.
- Cancellation and ownership are explicit.

### Negative

- Sequential handlers limit throughput; state and deduplication are process-local.
- Live VK behavior still requires optional integration verification.

## Documentation

- [Project architecture](../architecture/project-architecture.md)
- [PTB reference](../architecture/python-telegram-bot-compatibility.md)
- [VK API support](../development/api-compatibility.md)
