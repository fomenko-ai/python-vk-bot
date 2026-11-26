# 0005: HTTPX2 on main, HTTPX on the Python 3.9 branch

Status: accepted
Date: 2026-11-26
Task: httpx2-migration

## Context

The user requested migration to actively maintained HTTPX2 and approved canonical
imports on main, preserved transport responsibilities, a documented client-injection
breaking change, and HTTPX throughout compat/py39. Decisions 0001 and 0002 establish
ownership and buffered multipart handling; only their HTTP library selection changes.
PTB stable 22.8 still uses HTTPX as verified in the linked reference review.

## Decision

Use HTTPX2 >=2.16.2,<3 on main without aliases or a second HTTP implementation.
Keep Bot, HTTPTransport, Application and LongPoll responsibilities and ownership.
Reject foreign injected client types explicitly. Adapt query redaction to HTTPX2's
logger and URL types. Normalize invalid polling URL errors into sanitized library
exceptions, including malformed bracketed hosts before HTTPX2 normalization.

Keep HTTPX for all Python versions in compat/py39. Transfer applicable fixes with
branch-native imports; preserve branch metadata, dependencies and Python 3.9 syntax.
This decision does not claim a transfer has already been performed.

## Alternatives Considered

### Conditional HTTPX/HTTPX2 dependencies in compat/py39

Would adopt HTTPX2 on newer Python but create interpreter-dependent exception and
client types and require two dependency/test paths. Maintenance cost outweighs the
benefit for the legacy branch.

### Support both clients in main

Would preserve old client injection but require adapters or duplicated exception,
logging and type handling. Main has no older-Python constraint requiring this.

## Consequences

### Positive

- One HTTP type system per branch, no process-wide aliases, no new abstractions.
- Explicit ownership, cancellation and multipart buffering remain understandable.
- Dependency evolution remains separate from PTB architectural alignment.

### Negative

- Injected HTTPX clients and custom transports need migration to HTTPX2.
- Default CA store, logging names and User-Agent change with the dependency.
- Applicable transport fixes need HTTPX adaptation in the legacy branch.

## Documentation

- [Migration and source review](../development/httpx2-migration.md)
- [PTB reference](../architecture/python-telegram-bot-compatibility.md#httpx2-transport)
- [Original framework decision](0001-async-framework.md)
- [Buffered media decision](0002-media-attachments.md)
