# Verification

## Donut events and version 0.5.0 (2026-11-05)

Added **38 network-free Donut regression cases** after main-code approval, covering
all five events, raw/extra field retention, cached typed views, user identity, monetary
validation, filters, handler selection, ordered groups, user context, Callback
authentication, failed-handler retry, duplicate suppression and HTTP validation.
The narrow Donut suite passed, followed by the full suite: **360 tests** on Python 3.14.4.
No production-code fixes were needed during this test stage.

The requested new version is **0.5.0**, with changelog date **2026-11-05**. Package
metadata and uv.lock agree; no dependency versions changed.

| Check | Result |
| --- | --- |
| `uv lock` | Passed |
| `uv sync` | Passed |
| `uv sync --locked --extra callback` | Passed |
| `uv run ruff check .` | Passed |
| `uv run ruff format --check .` | Passed, 73 files |
| `uv run ty check` | Passed |
| `uv run pytest --strict-markers` | Passed, 360 tests |
| `git diff --check` | Passed |
| Live VK delivery / other Python versions | Not run; outside the first-stage verification scope |

The Donut tests use existing socket/DNS isolation and mocked HTTP/ASGI delivery.
No live credentials, subscription synchronization, access service or persistent storage
are involved. Changes remain local; no commit, tag or publication was performed.

## Unified queue regression verification (2026-11-03)

After the user approved the test stage, **51 new cases** were added on CPython 3.14.4:

- 29 background-event cases: mixed VK/internal FIFO, type matching, explicit state scopes,
  stop exceptions, deduplication, error context, bounded admission, waiting producers,
  managed-task failure/cancellation and publishing results during shutdown.
- 14 lifecycle cases: manual/context/polling hook order, Bot availability in post_stop,
  cleanup errors, reentry guards, concurrent shutdown, repeated cancellation, restart
  and graceful versus cancelled active Long Poll dispatch. Existing startup-failure cases
  also verify that post_stop is not called for failed initialization.
- 4 Callback cases: HTTP timeout before admission and while queued, authentication and
  confirmation during queue overload, successful handler-stop acknowledgement, and ASGI
  lifespan draining results before post_stop.
- 4 background-example cases: local computation, stop/deduplication, outgoing messages,
  scoped state and shutdown drain; main() also runs with mocked HTTP and Long Poll.

The full unit suite passed: **320 tests**. Narrow suites passed first. No production-code
fixes were needed during this test stage. Tests use MockTransport/ASGITransport and the
existing socket/DNS isolation fixture; no live network or credentials were used.

| Check | Result |
| --- | --- |
| `uv sync --locked --extra callback` | Passed |
| `uv run --no-sync ruff check .` | Passed |
| `uv run --no-sync ruff format --check .` | Passed, 69 files |
| `uv run --no-sync ty check` | Passed |
| `uv run --no-sync pytest --strict-markers` | Passed, 320 tests |
| `git diff --check` | Passed |
| Live VK / integration checks | Not run; outside this isolated unit-test task |
| Other Python versions | Not run; verification target is Python 3.14 |

The unrelated staged interactive-map edit is preserved. No commit, publication or
compatibility-branch transfer was performed.

## Version and documentation update (2026-11-03)

The user approved package version **0.4.0** and changelog date **2026-11-03**.
`uv lock` updated only the local package version; `uv sync --locked --extra callback`
rebuilt and installed it successfully. Ruff lint/format (67 files), ty,
`pytest --strict-markers` (**269 existing tests**) and `git diff --check` passed
on Python 3.14.4. No test files changed and no publication was performed.

The README background-task overview is two paragraphs after Media and location;
detailed contracts remain in [the event processing guide](event-processing.md).
The requested external-project references were removed from documentation and the
local task record. A case-insensitive search including ignored project files found
no remaining matches, excluding Git internals, virtual environments and tool caches.
At this checkpoint, new regression tests awaited main-code approval; see the completed
regression verification above for the subsequent test stage.

## Unified queue main-code verification (2026-11-03)

On CPython 3.14.4, the existing Application, Callback and Long Poll suite passed
**52 tests**, followed by the full existing suite: **269 tests passed**. No tests
were added or edited at this checkpoint, pending approval of the implemented
main code. These results establish existing-test compatibility, not comprehensive
coverage of the new queue/task/lifecycle contracts.

Passed: `uv sync --locked --extra callback`, `ruff check .`, `ruff format --check .`
(67 files), `ty check`, `pytest --strict-markers` and `git diff --check`. Checks after
synchronization used `uv run --no-sync` to retain the optional Callback dependencies.
A final verification retry ran outside the sandbox after uv could not write its
cache lock; all checks then passed. Dependency metadata and uv.lock are unchanged.

Not run at this checkpoint: new focused regression scenarios, the mocked background-result
example, live VK/integration checks, and other Python versions. The later regression entry
above covers the new scenarios/example; live services remain outside this task.
The pre-existing staged interactive-map edit was preserved. No commit or release
was made and no compatibility-branch transfer was started.

## Typed keyboard verification (2026-11-02)

Checked on CPython 3.14.4, Linux x86_64. The full unit suite has **269 passing tests**,
including 23 new typed-keyboard cases. They cover text/callback wire envelopes,
dictionary/model/string/absent payloads, payload aliases and subclass fields, enum
conversion and assignment validation, invalid fields, non-finite JSON rejection,
mixed raw/typed keyboards and mocked messages.send/messages.edit request bodies.
The integration helper narrows raw dictionary buttons before accessing action fields.

Locked synchronization with all extras, Ruff lint/format, whole-project ty checking
and `git diff --check` passed. Wheel and sdist builds passed for the main-code change.
No live VK execution or additional Python-version assessment was performed for typed
buttons; these tests verify local validation and serialization against synthetic responses.

## Media verification (2026-11-01)

Checked on 2026-11-01, Linux x86_64, CPython 3.14.4. The expanded regression suite has
**240 passing tests**: 109 existing cases and 131 media/model/example cases. Locked
dependency synchronization with the Callback extra, Ruff lint/format, ty and
`git diff --check` passed. No coverage percentage is claimed for this expanded suite;
the optional reproduction command below keeps coverage data in memory.

The 0.2.0 wheel and sdist build successfully. An isolated import from the wheel verified
the new attachment exports and version metadata. No publication, tagging or commit was
performed. Media changes are currently in `main`; the separate compatibility branch
has only its already-approved version update.

## Regression scope

- API serialization, response validation, safe errors, credentials, redirects, timeouts,
  cancellation, and owned/borrowed HTTP clients.
- Environment/dotenv/explicit settings precedence, subclass extensions and secret handling.
- Event models, extra fields, filters, commands and ordered handler groups.
- Long Poll cursor recovery, malformed batches, transient retries, bounded backoff and reset.
- Application state scopes, duplicate delivery, handler failures, cancellation and shutdown.
- Callback authentication, confirmation, body/pending limits, timeout cleanup, duplicate
  acknowledgements and retry after failure.
- Photo/document/voice upload stages, multipart contents, bytes/path/file sources, borrowed
  file positions, filename inference, upload credentials/log redaction and malformed URLs.
- HTTP, VK, upload-server and malformed-response failures without implicit mutation retries;
  off-loop file reads, repeated cancellation while reading, and upload cancellation.
- Typed and raw attachment views, preserved unknown fields, incomplete/unknown attachment
  fallback, media-edit upload bypass, explicit caption/keyboard values and deletion results.
- Missing/zero/extra location fields, valid generated PNG data, map ownership checks,
  failed-edit state retention, and serialization of concurrent navigation callbacks.

HTTPX MockTransport and ASGITransport supply synthetic responses. The unit fixture blocks
socket connections and DNS lookups. Live VK integration has not been run; mocked tests do
not establish delivery guarantees or live-server conformance. No minimum-dependency matrix
has been run. Tests used the synchronized lockfile, including the Callback extra.

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
```

For terminal-only coverage:

```bash
uv run --no-sync python - <<'PY'
import coverage
import pytest

cov = coverage.Coverage(source=["python_vk_bot"], branch=True, data_file=None)
cov.start()
status = pytest.main(["--strict-markers", "-q"])
cov.stop()
cov.report(show_missing=True)
raise SystemExit(status)
PY
```

## Original Python assessment (2026-10-31)

This assessment was performed after the Python 3.14 regression suite passed. Each installed
interpreter compiled all 17 package source files with `compile`, without importing modules
or writing bytecode. A syntax failure is sufficient to reject running the current source
on that interpreter; dependency installation and runtime tests were therefore not attempted
on the failing versions.

| Interpreter | Source syntax | Runtime verification |
| --- | --- | --- |
| CPython 3.9.25 | Failed in 7 files | Not run: incompatible syntax |
| CPython 3.10.20 | Failed in 7 files | Not run: incompatible syntax |
| CPython 3.11.15 | Failed in 7 files | Not run: incompatible syntax |
| CPython 3.12.13 | Failed in 2 files | Not run: incompatible syntax |
| CPython 3.13.14 | Failed in 2 files | Not run: incompatible syntax |
| CPython 3.14.4 | Passed | 109 regression tests passed |

`callback.py` and `long_poll.py` use unparenthesized multiple-exception clauses, which
require Python 3.14 ([PEP 758](https://peps.python.org/pep-0758/)). Python 3.9–3.11 also
reject type aliases and generic function syntax from Python 3.12
([PEP 695](https://peps.python.org/pep-0695/)). Source inspection additionally shows that
Context annotations rely on deferred evaluation from Python 3.14
([PEP 649](https://peps.python.org/pep-0649/)); changing exception syntax alone would not
establish support for another interpreter.

At the time of this assessment, the package requirement was `requires-python = ">=3.14"`
and the verified runtime was CPython 3.14.4. See the current matrix below for subsequent
checks on newer interpreters.

```bash
# Reproduce the original diagnostic; expected exit status 1 for Python <3.14.
sh python_compatibility_tests/run_python_compatibility.sh 3.9 3.10 3.11 3.12 3.13 3.14

# Expected exit status 0 with a locally installed Python 3.14.
sh python_compatibility_tests/run_python_compatibility.sh 3.14
```

The diagnostic uses `uv python find --system --no-project --no-python-downloads` and does not install
dependencies or alter the project environment. Missing interpreters are reported as
unchecked and cause a nonzero exit status. It is separate from ordinary pytest discovery.

## Pre-media main matrix

Verified on 2026-11-01, Linux x86_64, after the Python 3.14 contributor checks passed.
Each syntax check compiled all 17 package sources. Runtime checks used isolated uv
environments with the existing lockfile, development dependencies and Callback extra.
These results predate the media additions. The expanded 240-test suite has only been run
on Python 3.14.4; the older matrix is retained as historical evidence, not as verification
of the new APIs on other interpreters.

| Interpreter | Source syntax | Runtime verification |
| --- | --- | --- |
| CPython 3.14.4 | Passed | 109 tests passed |
| CPython 3.15.0 | Passed | 109 tests passed |
| CPython 3.15.1 | Passed | 109 tests passed |
| CPython 3.15.2 | Passed | 109 tests passed |
| CPython 3.15.0b2 (additional preview check) | Passed | 109 tests passed |
| CPython 3.16.0a1 (preview) | Passed | 109 setup errors in pytest-asyncio; no test bodies ran |

On 3.16.0a1, uv selected a source build of locked `pydantic-core==2.50.2`.
The first attempt failed because `cc` was unavailable. A subsequent check used Zig
from an isolated uv tool environment, exposed as `cc` through a temporary PATH
wrapper. After a C compile/run smoke check passed, pydantic-core built successfully
and all 27 locked packages installed without changing project dependencies.

Pytest collected 109 tests, but all failed during fixture setup in locked
`pytest-asyncio==1.4.1`. Its event-loop-policy fixture calls
`asyncio.get_event_loop_policy()`, which is absent on this interpreter. The removal
was documented in [Python's asyncio policy deprecation](https://docs.python.org/3.14/library/asyncio-policy.html).
No test bodies ran; this identifies an incompatible test dependency and leaves
the library's Python 3.16 runtime support unverified. Recheck with a compatible
test stack before advertising support. Tests and dependency constraints were not
adapted during this assessment.

The contributor .venv remains on Python 3.14.4; package metadata and uv.lock have no
changes from these checks. Other Python implementations were not tested.

Newer interpreters were installed explicitly with `uv python install --no-bin` before
running the scripts. The installed uv's bundled catalog only offered 3.15.0b2;
the stable 3.15 releases and 3.16 preview were discovered using
[Astral's current download metadata](https://github.com/astral-sh/uv/blob/main/crates/uv-python-managed/download-metadata.json)
with `--python-downloads-json-url`. The compatibility scripts themselves do not download
interpreters. Release status was checked against [python.org](https://www.python.org/downloads/)
and the [Python version status](https://devguide.python.org/versions/).

After the Python 3.14 contributor checks pass, run:

```bash
./python_compatibility_tests/run_python_compatibility.sh
./python_compatibility_tests/run_runtime_compatibility.sh
# Both scripts also accept explicit versions, bypassing discovery:
./python_compatibility_tests/run_python_compatibility.sh 3.14
./python_compatibility_tests/run_runtime_compatibility.sh 3.14
# Reproduce checks on stable newer releases:
./python_compatibility_tests/run_python_compatibility.sh 3.15.0 3.15.1 3.15.2
./python_compatibility_tests/run_runtime_compatibility.sh 3.15.0 3.15.1 3.15.2
# Preview check (dependency source builds may require a C/Rust toolchain):
./python_compatibility_tests/run_python_compatibility.sh 3.16.0a1
./python_compatibility_tests/run_runtime_compatibility.sh 3.16.0a1
```

Without arguments, both scripts use
`uv python list --only-installed --offline --no-python-downloads 'cpython>=3.14'`.
They deduplicate uv installation keys, so aliases to the same installation do not
repeat checks. Each request is resolved outside virtual environments, without project
version preferences. Explicit arguments replace the default and can be used for older
version diagnostics; they do not change the package's Python requirement.

The runtime script installs the locked package, development group and Callback extra
in isolated uv environments and runs `python -m pytest --strict-markers -p no:cacheprovider`
with bytecode writes disabled. It preserves the contributor .venv and produces no
persistent test reports. Dependency setup may access the package index; no Python
interpreters are downloaded and the unit tests still block live sockets and DNS.

An empty default matrix or discovery failure exits nonzero. Missing explicitly requested
interpreters are reported as `NOT CHECKED`. Dependency setup or regression failures also
produce a nonzero final status; remaining selected interpreters are still checked.
Newer installed CPython versions enter the default matrix automatically, but are not
declared supported until their runtime checks pass. The `compat/py39` branch retains
its explicit default matrix of Python 3.9–3.14.
