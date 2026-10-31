# Contributing

Use Python 3.14 and uv. The root `python_vk_bot/` directory is the package.

```bash
uv sync --locked --all-extras
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run pytest --strict-markers
uv build
```

The optional Callback extra is installed for type checking and receiver tests.
HTTPX MockTransport replaces live HTTP; pytest-asyncio and pytest-cov are development
dependencies. Do not generate
persistent coverage artifacts by default.

## Test approval and current state

AGENTS.md requires approval of implemented main-code changes before adding or editing
corresponding tests. The approved regression suite is in `tests/unit`; an empty collection
is not a successful test run. Callback tests are skipped when Starlette is absent, so use
`--all-extras` for complete verification.

Tests cover serialization, models, settings sources/inheritance, API/network errors, Long Poll recovery,
handler ordering, callback authentication/confirmation, duplicates, cancellation, and
owned versus injected HTTP-client cleanup. An automatic fixture blocks socket connections
and DNS lookups, and isolates VK environment variables. Unit tests must not use credentials
or live networks. Live integration tests require a registered marker, explicit opt-in and
credentials supplied through environment variables.

The opt-in `python_compatibility_tests/run_python_compatibility.sh` checks source syntax
under installed interpreters without downloading runtimes, importing the library or writing
bytecode. Its default Python 3.9–3.14 matrix exits nonzero when an interpreter fails or cannot
be found. Syntax success alone does not establish runtime support. See the
[verification results and reproduction commands](docs/development/verification.md).

## Quality script

`./scripts/ci.sh` runs dependency synchronization, Ruff, ty, pytest and package build on
Python 3.14. It does not start Docker, external services, or the Python compatibility
matrix. It fails if tests fail or no tests are collected. No CI hosting provider is
configured by this change.

Keep secrets, caches, build output and generated reports out of Git. Do not log complete
updates, message bodies or credential-bearing exceptions. Review the architecture and
VK compatibility documents before changing public APIs or version-dependent behavior.
