# Verification

Checked on 2026-11-01 on Linux x86_64, branch `compat/py39`. All **243 regression tests**
pass on each interpreter below. Tests were adapted after explicit user approval of the
production changes. Dependency installation uses uv.lock with the Callback extra and
configured development group.

## Python matrix

| CPython | Package syntax | Locked installation and import | Full regression suite |
| --- | --- | --- | --- |
| 3.9.25 | Passed | Passed | 243 passed |
| 3.10.20 | Passed | Passed | 243 passed |
| 3.11.15 | Passed | Passed | 243 passed |
| 3.12.13 | Passed | Passed | 243 passed |
| 3.13.14 | Passed | Passed | 243 passed |
| 3.14.4 | Passed | Passed | 243 passed |

The Python 3.14 suite passed before the older-runtime regression runs. The runtime matrix
uses isolated uv environments, leaving the contributor .venv on Python 3.14.
The syntax script compiles all 18 package sources without importing dependencies or
writing bytecode. Syntax success is only one part of the runtime assessment.

```bash
# Already-installed interpreters only; no Python runtime downloads.
./python_compatibility_tests/run_python_compatibility.sh
./python_compatibility_tests/run_runtime_compatibility.sh

# Optional subset:
./python_compatibility_tests/run_runtime_compatibility.sh 3.9 3.11
```

The runtime script installs dependencies before running pytest. Setup may contact the
package index; tests use HTTPX MockTransport/ASGITransport and a fixture that blocks socket
connections and DNS lookups. Missing interpreters, dependency resolution/installation
failures and failed tests result in a nonzero exit code. Neither script is part of default
pytest discovery. The runtime script disables pytest's persistent cache and bytecode writes.

## Configured checks

| Check | Result |
| --- | --- |
| `uv lock` | Not rerun; transfer does not change dependency metadata |
| `uv sync --locked --all-extras` | Passed |
| `uv run ruff check .` | Passed; Python 3.9 target for production and tests |
| `uv run ruff format --check .` | Passed |
| `uv run ty check` | Passed; Python 3.9 language target in the contributor environment |
| `uv run pytest --strict-markers` | Passed on Python 3.14.4; 243 tests |
| Runtime matrix | Passed; 243 tests on each Python 3.9–3.14 interpreter |
| `uv build --out-dir <temporary-directory>` | Not rerun for this transfer |
| `git diff --check` | Passed |
| Live VK integration | Not run; opt-in, requires credentials |
| Minimum dependency combinations | Not run; verified the resolved lockfile sets |

The new tests exposed a malformed upload-host case that HTTPX normalized rather than
rejecting. Upload URL validation now rejects unmatched host brackets before sending.

## Live media check

`tests/integration/test_media_edit.py` has two cases: global message ID and conversation
message ID. It sends a test photo, verifies its initial state, replaces photo/text/keyboard,
then reads the same message and checks unchanged identifiers and changed content.
Cleanup attempts to delete only that test's message for recipients.

Both cases were collected with live execution explicitly disabled and **skipped**.
No VK credentials were inspected or used and no authenticated requests were made.
See [live test instructions](media-api.md#live-integration-test) for the explicit flag,
dedicated token/peer variables and side effects. Default test discovery remains unit-only.

## Reproduce contributor checks

```bash
uv sync --locked --all-extras
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync ty check
uv run --no-sync pytest --strict-markers
uv build
```

For type checking against a specific interpreter's dependency set, synchronize into a
separate environment. For example, choose a fresh temporary path for COMPAT_ENV:

```bash
COMPAT_ENV=/tmp/python-vk-bot-typecheck39
UV_PROJECT_ENVIRONMENT="$COMPAT_ENV" uv sync --locked --all-extras --python 3.9
uv run --no-sync ty check --python "$COMPAT_ENV" --python-version 3.9
```

The default ty target is Python 3.9 even though the contributor interpreter is 3.14.
async-timeout is present in the dev group on all interpreters so conditional imports
can be checked. It remains conditional and optional in consumer package metadata.

## Regression scope

- Media uploads, request serialization, typed attachment fallback, edit/delete behavior,
  cancellation while reading/uploading and concurrent interactive map navigation.

- Request serialization, API/network errors, validation, credentials, redirects, retry
  policies, polling reconnection and safe logging.
- Models, unknown fields, settings validation, environment/dotenv precedence and inheritance.
- Filters, commands, handler groups, scoped state, ordered dispatch and deduplication.
- Startup failures, owned/borrowed HTTP clients, cancellation, graceful shutdown and
  stopping from a handler.
- Callback secrets/confirmation, body limits, capacity, deadlines and retries.
- Constructing Application before the event loop starts, followed by concurrent dispatch.
- Cancelling the polling owner while HTTP cleanup is suspended: cancellation waits for
  that cleanup to finish before the runner exits.
- External cancellation of a Callback request propagates, frees capacity and permits
  retry of the same event rather than marking it processed.

Test task helpers cancel and await owned tasks on every exit; Long Poll generator helpers
always close the generator. TaskGroup, contextlib.aclosing and the anext builtin are not
required by the test suite. Tests use portable deadlines; the production Callback path
still selects asyncio.timeout on 3.11+ and its backport on older versions.

## Consumer packaging before the media transfer

The checks below predate the media API transfer and have not been repeated for it.

Built both wheel and sdist, then installed them into separate clean Python 3.9 environments
outside the repository, without the repository lockfile:

- Base wheel: imports and BotSettings construction passed. Starlette, Uvicorn and
  async-timeout were absent, confirming that base imports do not require the Callback extra.
- Sdist with `[callback]`: source build, imports, settings and ASGI app creation passed.
- Both installed distributions report `Requires-Python: >=3.9`; `uv pip check` passed.

The Python 3.9 consumer resolution included Pydantic 2.13.5 and pydantic-settings 2.11.0;
Callback additionally selected Starlette 0.49.3, Uvicorn 0.39.0 and async-timeout 5.0.1.

## Limits

These results cover the listed CPython patch versions on Linux x86_64 with the resolved
dependencies. Other platforms, later interpreters, alternate Python implementations and
all possible dependency combinations were not tested. Mocked tests do not establish
live-server conformance, durable delivery or exactly-once processing. Coverage percentages
were not remeasured for this change. No persistent reports or coverage files were generated.
