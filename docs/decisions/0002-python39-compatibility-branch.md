# 0002: Maintain Python 3.9 compatibility in a separate branch

Status: accepted
Date: 2026-11-01
Task: python39-compatibility

## Context

The user selected a separate compatibility branch and requested Python 3.9 as its
minimum interpreter. The main branch uses Python 3.14. The compatibility change must
preserve the package layout, imports, VK semantics and explicit async resource ownership.
The user approved production changes and subsequently authorized test/documentation updates.

## Decision

Maintain `compat/py39` with `requires-python = ">=3.9"`, compatible typing syntax and
Python-dependent dependency resolution in one lockfile. Keep the distribution name
`python-vk-bot` and import name `python_vk_bot`. Release numbering is managed separately
from this architectural decision.
Python 3.14 remains the default contributor interpreter in `.python-version`.

Use `typing_extensions` for Self/TypeAlias and Optional/Union for annotations evaluated
on Python 3.9. Context is a regular dataclass on every interpreter. Use try/finally to
close the Long Poll async generator. Wait for the polling task with asyncio.wait so
caller cancellation propagates separately from cancellation initiated by stop(); cancel
and await the owned task before leaving the application lifecycle.
Create internal locks lazily in async code because Python 3.9 binds them to the loop
at construction, while ASGI factories may construct Application outside the running loop.

For the optional Callback adapter, use asyncio.timeout on Python >=3.11 and the
async-timeout 5 backport on older interpreters. Import it only when creating the adapter.
Select pydantic-settings >=2.11,<2.12 on Python 3.9 and >=2.12,<3 on newer interpreters.

Broader runtime metadata is a compatibility target, not a claim that every interpreter,
dependency combination or platform has passed regression tests. Record actual checks
separately. The approved suite runs on every interpreter in the 3.9–3.14 matrix.

## Alternatives Considered

### Lower the baseline of the main branch

One development line would avoid backport maintenance. The user explicitly selected an
independent compatibility branch, retaining the main branch's Python 3.14 baseline.

### Publish a separate legacy distribution

Independent distribution naming complicates installation and risks conflicting imports.
A separate package is unnecessary for selecting a Git branch or tagged release.

### Generate older source during packaging

Syntax transformation cannot supply older asyncio behavior or compatible dependencies.
It would introduce a second source representation without reducing runtime verification.

## Consequences

### Positive

- Consumers can install the branch with ordinary package tools and automatic dependencies.
- Async task and HTTP resource ownership remain explicit on older interpreters.
- Python-specific dependencies do not force older packages onto all consumers.

### Negative

- Fixes need transfer between branches and testing against multiple dependency sets.
- Python 3.9 has reached upstream end of life; its dependency choices are constrained.
- async-timeout is an upstreamed, deprecated backport used only below Python 3.11.
- Context has an instance dictionary rather than dataclass slots.
- Tests require portable task and generator cleanup helpers to run on all six interpreters.

## Documentation

- [Python compatibility and installation](../development/python-compatibility.md)
- [Verification](../development/verification.md)
- [PTB design reference](../architecture/python-telegram-bot-compatibility.md)
