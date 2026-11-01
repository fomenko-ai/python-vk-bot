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
dependencies. Do not generate persistent coverage artifacts by default.

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

## Python compatibility

The `compat/py39` branch supports Python 3.9–3.14. The `.python-version` file selects
Python 3.14 for development; the minimum consumer version is set in `pyproject.toml`.

Ruff and ty target Python 3.9 for production and tests. The development group installs
async-timeout on all interpreters for portable test deadlines and checking conditional
imports. Consumers receive it only with the Callback extra on Python <3.11.
When changing dependency constraints, also check types against interpreter-specific
dependency environments; see [verification commands](docs/development/verification.md).

The opt-in `python_compatibility_tests/run_python_compatibility.sh` checks source syntax
under installed interpreters without downloading runtimes, importing the library or writing
bytecode. Its default Python 3.9–3.14 matrix exits nonzero when an interpreter fails or cannot
be found. Syntax success alone does not establish runtime support. See the
[verification results and reproduction commands](docs/development/verification.md).

After the default Python 3.14 checks pass, run the opt-in full regression matrix:

```bash
./python_compatibility_tests/run_runtime_compatibility.sh
# Or select installed interpreters:
./python_compatibility_tests/run_runtime_compatibility.sh 3.9 3.11
```

It installs the locked development and Callback dependencies in isolated uv environments
and runs pytest with strict markers on each selected interpreter. It preserves .venv,
does not download interpreters and does not create persistent reports. Dependency setup
may access the package index; tests still cannot access the live network.

## Quality script

`./scripts/ci.sh` runs dependency synchronization, Ruff, ty, pytest and package build on
Python 3.14. It does not start Docker, external services, or the Python compatibility
matrix. It fails if tests fail or no tests are collected. No CI hosting provider is
configured by this change.
It verifies the contributor environment; use the separate runtime script for all versions.

Keep secrets, caches, build output and generated reports out of Git. Do not log complete
updates, message bodies or credential-bearing exceptions. Review the architecture and
VK compatibility documents before changing public APIs or version-dependent behavior.
