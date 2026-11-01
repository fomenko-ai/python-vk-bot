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

`main` requires Python >=3.14; Ruff targets Python 3.14. The separate `compat/py39`
branch supports Python 3.9–3.14, with its own dependency constraints and tooling targets.
Both branches use Python 3.14 for development. See the
[branch comparison and installation guide](docs/development/python-compatibility.md).

The opt-in `python_compatibility_tests/run_python_compatibility.sh` checks source syntax
under installed interpreters without downloading runtimes, importing the library or writing
bytecode. After the contributor checks on Python 3.14 pass, use the runtime script
to install locked development and Callback dependencies and run the full regression
suite in an isolated uv environment for each interpreter:

```bash
./python_compatibility_tests/run_python_compatibility.sh
./python_compatibility_tests/run_runtime_compatibility.sh
# Explicit selection instead of automatic discovery:
./python_compatibility_tests/run_runtime_compatibility.sh 3.14
```

On `main`, both scripts default to all installed CPython >=3.14 discovered by uv,
deduplicated by installation key. Discovery is offline and no interpreters are downloaded.
Explicit version arguments replace that selection. An empty default matrix, unavailable
requested interpreter, dependency setup error or failed check produces a nonzero exit.
Failures for one interpreter do not prevent checking the remaining selected interpreters.

The runtime script preserves the contributor .venv and creates no persistent test reports;
dependency installation may access the package index, while unit tests block live networks.
Syntax success alone does not establish runtime support. See
[verification results and reproduction commands](docs/development/verification.md).
The `compat/py39` scripts retain their default Python 3.9–3.14 matrix; follow
[that branch's verification guide](https://github.com/fomenko-ai/python-vk-bot/blob/compat/py39/docs/development/verification.md).

## Keeping branches aligned

After committing changes to `main`, transfer applicable changes to `compat/py39` using
the [sync-compat-branch skill](skills/sync-compat-branch/SKILL.md). Preserve each branch's
Python requirement, dependency constraints and release metadata, and record source
commits. Follow the approval gates in `AGENTS.md`; report any blocked or excluded work.
See [Agent Skills](docs/agent-skills.md) for local skill setup.

## Quality script

`./scripts/ci.sh` runs dependency synchronization, Ruff, ty, pytest and package build on
Python 3.14. It does not start Docker, external services, or the Python compatibility
matrix. It fails if tests fail or no tests are collected. No CI hosting provider is
configured by this change.

Keep secrets, caches, build output and generated reports out of Git. Do not log complete
updates, message bodies or credential-bearing exceptions. Review the architecture and
VK compatibility documents before changing public APIs or version-dependent behavior.
