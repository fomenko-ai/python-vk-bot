# Verification

## Unified event transfer and review fixes (2026-11-03)

Transferred production code, shared documentation, examples and all four test-file
changes from main commit `9874493ab5d3d62e6327bcbd93f5dd6eb433796b`. Queue close,
lazy loop primitives, generics and owned polling cleanup are portable to Python 3.9.
Existing compatibility-only tests and timeout/task helpers are retained. Version
0.4.0 and changelog date 2026-11-03 match main by explicit user request; branch-specific
dependencies and Python targets are unchanged. uv lock changed only the package version.

The reviewed Long Poll cleanup defect is fixed locally: stop and runner cleanup share
one cancellation request per polling run. Regression tests cover both stop/cancel orders
and repeated runner cancellation while HTTP cleanup is suspended. Additional coverage
checks queue inspection before the loop and close with empty/full queues. The same defect
in main is outside this target-branch transfer; no changes were transferred back to main.

Production changes and then regression edits were approved before the test stage.
The focused application/Callback/background suites passed 94 cases on Python 3.14.4.
All **327 tests** passed on each interpreter below, after the Python 3.14 contributor run:

| CPython | Syntax (20 package sources) | Locked installation and full regression |
| --- | --- | --- |
| 3.9.25 | Passed | 327 passed |
| 3.10.20 | Passed | 327 passed |
| 3.11.15 | Passed | 327 passed |
| 3.12.13 | Passed | 327 passed |
| 3.13.14 | Passed | 327 passed |
| 3.14.4 | Passed | 327 passed |

| Check | Result |
| --- | --- |
| `uv sync --locked --all-extras` | Passed |
| `uv run --no-sync ruff check .` | Passed |
| `uv run --no-sync ruff format --check .` | Passed; 70 files |
| `uv run --no-sync ty check` | Passed |
| `uv run --no-sync pytest --strict-markers` | Passed; 327 tests on Python 3.14.4 |
| Syntax and isolated runtime compatibility scripts | Passed on all six interpreters above |
| `git diff --check` and staged diff check | Passed |
| Live VK integration | Not run; opt-in credentials required |
| Wheel/sdist build and consumer installation for 0.4.0 | Not run; previous build results below apply to 0.3.0 |

No new dependency metadata changes were needed during review fixes, so uv lock was not
rerun at that stage; locked sync confirms consistency. Tests use HTTP mocks and no live
services. Platform and dependency-combination limits below continue to apply.

The following sections record verification before this transfer.

Checked on 2026-11-02 on Linux x86_64, branch `compat/py39`. All **272 regression tests**
pass on each interpreter below. Tests were adapted after explicit user approval of the
production changes. Dependency installation uses uv.lock with the Callback extra and
configured development group.

## Python matrix

| CPython | Package syntax | Locked installation and import | Full regression suite |
| --- | --- | --- | --- |
| 3.9.25 | Passed | Passed | 272 passed |
| 3.10.20 | Passed | Passed | 272 passed |
| 3.11.15 | Passed | Passed | 272 passed |
| 3.12.13 | Passed | Passed | 272 passed |
| 3.13.14 | Passed | Passed | 272 passed |
| 3.14.4 | Passed | Passed | 272 passed |

The Python 3.14 suite passed before the older-runtime regression runs. The runtime matrix
uses isolated uv environments, leaving the contributor .venv on Python 3.14.
The syntax script compiles all 19 package sources without importing dependencies or
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

## Typed keyboard transfer

Transferred from main commit `2740cfd3d6e9ca49d1aa8db42b0dfb1071f1d455`, including
version 0.3.0 and changelog date 2026-11-02. Python-specific dependencies and
interpreter targets are retained. This document records the compatibility branch's
own verification results.

The 23 new cases cover text/callback action serialization, structured and encoded
payloads, aliases/subclass fields, enum validation, invalid fields and assignments,
mixed raw/typed keyboards, non-finite JSON rejection and mocked send/edit requests.
Portable enum tests additionally check value-based `str()` on every interpreter.
The integration helper narrows raw dictionary buttons before accessing their fields.
No live VK operations were run. See the [keyboard API](keyboards.md).

## Configured checks

| Check | Result |
| --- | --- |
| `uv lock` | Passed; synchronized project version 0.3.0 without dependency changes |
| `uv sync --locked --all-extras` | Passed |
| `uv run ruff check .` | Passed; Python 3.9 target for production and tests |
| `uv run ruff format --check .` | Passed |
| `uv run ty check` | Passed; Python 3.9 language target in the contributor environment |
| `uv run pytest --strict-markers` | Passed on Python 3.14.4; 272 tests |
| Runtime matrix | Passed; 272 tests on each Python 3.9–3.14 interpreter |
| `uv build --out-dir <temporary-directory>` | Passed; wheel and sdist report version 0.3.0 |
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
