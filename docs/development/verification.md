# Verification

## HTTP transport safeguards and migration skill transfer (2026-11-26)

Target: compat/py39, base `1074000`. Sources:
`7e56db9a7d8962759d950356c9863cf214dc0408` and
`f3e4d7c938dea56a92805befcbd619a5c995de8a` from main. The user requested a visible
branch switch and no commit; changes were applied selectively in the shared checkout.
The source behavior and regression approvals were reused for equivalent safeguards.

Transferred sanitized Long Poll URL parsing and 24 applicable transport regressions,
using HTTPX and the Python 3.9-compatible three-argument traceback formatter.
The explicit S113 suppression is limited to the MockTransport client in the timeout
precedence test, whose purpose is to verify that real request timeouts are applied.
No runtime timeout or TLS verification is disabled.

Also transferred the clarification rule, branch-aware HTTP client guidance and bundled
skill reference updates, adapted to this branch's 0.8.1/Python 3.9+/HTTPX baseline.
At the user's request, changelog entries are grouped under 0.8.1 (2026-11-26).
No version, date, dependency metadata or lockfile change was made. The complete exclusions and rationale are in the
[compatibility guide](python-compatibility.md#http-transport-and-bundled-skill-transfer-2026-11-26).
In particular, no HTTPX2 dependency or invalid-Location fix was simulated in HTTPX.

| Check | Result |
| --- | --- |
| `uv sync --locked --all-extras` | Passed using target lockfile |
| Focused transport/Long Poll suite on Python 3.14.4 | 78 passed |
| `uv run ruff check .` | Passed |
| `uv run ruff format --check .` | Passed, 79 files |
| `uv run ty check` | Passed with configured Python 3.9 target |
| `uv run pytest --strict-markers` on Python 3.14.4 | 498 passed |
| `run_python_compatibility.sh` on Python 3.9–3.14 | Passed, 23 production sources each |
| `run_runtime_compatibility.sh` on Python 3.9–3.14 | Passed, 498 tests on each interpreter |
| Wheel and sdist build in /tmp | Passed; reference bytes match branch source |
| Embedded skill examples | Compiled/imported without running bots |
| `git diff --check` | Passed |

Checked runtimes: 3.9.25, 3.10.20, 3.11.15, 3.12.13, 3.13.14, 3.14.4.
No live VK calls, credentials, external service tests, staging, commit, push, tag or
publication. A future user-created commit should include both source SHAs in its body.

## Message lookup validation transfer (2026-11-26, production stage)

Source main commit `fbabd118098be5e0f1cc50d9c4c3610885730545` is selectively
transferred onto compat/py39 base `a467a40`. Validation and shared API/PTB
documentation are included; the return annotation remains Optional[Message].
By subsequent user request, version 0.8.1 and changelog date 2026-11-26
match the source. Branch dependencies and Python targets are preserved.
No commit is created; the user controls staging and committing.

Passed: locked all-extras uv sync on Python 3.14.4, Ruff lint and format check,
ty and git diff --check. All 474 existing tests passed on Python 3.14.4 before
the compatibility matrix. Both compatibility scripts passed on Python 3.9.25,
3.10.20, 3.11.15, 3.12.13, 3.13.14 and 3.14.4: 23 package sources checked for
syntax and 474 existing regression cases passed on each interpreter.
Sandbox cache restrictions required elevated uv execution.

The new source test_message_lookup.py awaits approval of the transferred
production code under AGENTS.md; these results do not cover its 82 new cases.
Official VK schema/package sources were rechecked on 2026-11-26 and still
report 5.199 / 5.199.99; the uncertainty recorded in API compatibility remains.
No live VK calls, packaging build, commit, push, tag or publication.

After the metadata update, uv lock changed only the local project version.
Locked all-extras sync, Ruff lint/format, ty, git diff --check and all 474 tests
passed on Python 3.14.4. The interpreter matrix was not repeated for this
metadata-only update; runtime code and dependency versions are unchanged.

## Detailed send results transfer (2026-11-26, production stage)

Source main commit `c9b7f13dfe3d56e1b286620fc61216707e754823` is selectively
transferred onto compat/py39 base `ee2a848`. No target commit is created.
Production methods, public exports, response models and shared documentation
are included. Optional/Union annotations preserve Python 3.9 model evaluation.
By subsequent explicit user request, version 0.8.0 and changelog date 2026-11-26
match the source commit. Branch dependencies and Python targets are retained.
Main-only verification history is excluded.

Passed: uv sync --all-extras; uv sync --locked --all-extras; Ruff lint and
format check; ty; git diff --check; pytest --strict-markers on Python 3.14.4
(474 existing tests). Syntax checks passed for 23 package sources on Python
3.9.25, 3.10.20, 3.11.15, 3.12.13, 3.13.14 and 3.14.4. The isolated runtime
script passed all 474 existing tests on each of those six interpreters.
Initial transfer errors in two upload call sites and formatting were corrected
before the successful rerun. Sandbox cache restrictions required elevated uv.

After the version/date update, uv lock changed only the local project version.
All-extras sync, locked sync, Ruff lint/format, ty and all 474 existing tests
passed again on Python 3.14.4. The interpreter matrix preceded this metadata-only
update and was not repeated; runtime code and dependencies are unchanged.

The new test_message_send_ids.py from main is deliberately not transferred yet:
local rules require approval of the transferred production code before test edits.
These results establish existing regression coverage, not the source commit's
110 detailed-send cases. No live VK calls, packaging checks, commit or push.

## Keyboard limits transfer (2026-11-16)

Source main commit `94921e3714ffbc35ae407730c027b2cb00695d8c` is transferred
to the working tree on compat/py39 base `3174a4e`. No target commit is created
at the user's request. Code, shared documentation and 35 approved keyboard
regression cases are included. `Self` comes from typing_extensions; evaluated
model and test annotations use Union instead of Python 3.10 union operators.
Native/fallback enums and compatibility-only regressions are retained.

By explicit user request, version 0.7.0 and changelog date 2026-11-16 match
main. Branch-specific dependency requirements and Python targets are preserved;
the lockfile is synchronized. Main-only verification history is excluded.
No publication is claimed.

Passed on Python 3.14.4: `uv sync --locked --all-extras`, Ruff lint, Ruff format
check, ty and `pytest --strict-markers` (474 tests, including 74 keyboard cases).
Both compatibility scripts passed: syntax for 23 package sources and all 474
tests on each of Python 3.9.25, 3.10.20, 3.11.15, 3.12.13, 3.13.14 and 3.14.4.
Initial sandbox uv-cache errors were resolved by approved elevated execution;
an import sorting finding was corrected before final checks. No live VK requests
or consumer packaging checks were run for this transfer.

## Native buttons, snackbar and Retry-After transfer (2026-11-06)

Source main commit `ad23faf6641b50f761c8b2c0dd8b1d25da3c4e60` is transferred
into the working tree on compat/py39 base `29da37e`. No target commit was created,
at the user's request. The target branch is checked out for review.

Production code, examples, shared documentation and the approved 69 regression cases
are included. Union/Optional/TypeAlias annotations, timezone.utc and parenthesized
exception handling preserve Python 3.9 compatibility. Native/fallback string enums
and compatibility-only tests remain intact. By explicit user request, version 0.6.0 and release date 2026-11-06 match main.
Dependency requirements and Python targets are retained; uv.lock is synchronized.
Main-only verification history is excluded.

All checks passed: locked all-extras uv sync, Ruff lint, Ruff format, ty and
pytest --strict-markers on Python 3.14.4 (439 tests). Initial Ruff formatting/import
findings were corrected. Initial uv sync was blocked by sandbox cache permissions;
the approved rerun passed. Syntax checks passed for all 22 package sources, and
isolated locked installations plus all 439 tests passed on each interpreter:
3.9.25, 3.10.20, 3.11.15, 3.12.13, 3.13.14 and 3.14.4.
Git diff whitespace checks passed. No live VK operations or packaging builds were run.
The source's API verification record is preserved; this transfer changes no VK target
version or API semantics. No push, tag or publication was performed.

After the metadata follow-up, uv lock, uv sync, locked all-extras sync, Ruff lint
and format, ty and all 439 tests passed again on Python 3.14.4. Only the local
package version changed in uv.lock. The interpreter matrix was not repeated for
this metadata-only update; runtime code and dependency versions are unchanged.

## Donut event transfer (2026-11-05)

Selectively transferred main commit `31acf2b1d21543c6c72bb9b1f9e453bf96b3b49e`
onto compat/py39 base `699f295a78a22a9f8b5a789dab18287d261558dc`.
Models, Update parsing, handler, filters, exports, example, shared documentation
and all 38 Donut tests are included. Five extra cases check value-based enum str()
on every interpreter. Existing compatibility-only coverage is retained.

Adaptations: Optional/Union annotations, native StrEnum on 3.11+ with str/Enum
fallback on 3.9/3.10, string-set event matching, and if/elif in the example.
No transport, dispatcher or lifecycle contracts change. Branch-specific dependencies,
Python targets and installation instructions are preserved. By subsequent explicit
user request, package version 0.5.0 and changelog date 2026-11-05 match main; uv.lock
is synchronized without dependency changes. The empty source Unreleased bullet is
omitted. Source-only verification history is replaced by these target-specific results.

The focused Donut suite passed **43 cases** on Python 3.14.4 before the full contributor
checks and older-runtime assessment. Both compatibility scripts then passed:

| CPython | Syntax (21 package sources) | Locked installation and full regression |
| --- | --- | --- |
| 3.9.25 | Passed | 370 passed |
| 3.10.20 | Passed | 370 passed |
| 3.11.15 | Passed | 370 passed |
| 3.12.13 | Passed | 370 passed |
| 3.13.14 | Passed | 370 passed |
| 3.14.4 | Passed | 370 passed |

| Check | Result |
| --- | --- |
| `uv sync` / `uv sync --locked --all-extras` | Passed on Python 3.14.4 |
| `uv run --no-sync ruff check .` | Passed |
| `uv run --no-sync ruff format --check --no-cache .` | Passed; 74 files |
| `uv run --no-sync ty check` | Passed; target Python 3.9 |
| `uv run --no-sync pytest --strict-markers` | Passed; 370 tests on Python 3.14.4 |
| Syntax and isolated runtime compatibility scripts | Passed on all six interpreters |
| Donut example factory on Python 3.9 | Passed with synthetic settings; no server started |
| `git diff --check` | Passed |
| Live VK delivery / packaging builds | Not run; outside this transfer scope |

Both matrix scripts initially failed because the sandbox blocked uv cache writes;
approved reruns passed. The first syntax-script message about unavailable interpreters
was a cache-access failure, not evidence of missing Python installations. Tests use
network mocks and socket/DNS isolation. No live credentials or services were used.

Changes are deliberately uncommitted at the user's request. Source-to-target mapping
is `31acf2b` to the working-tree diff on `699f295`; there is no target commit yet.
No commit, push, tag or publication was performed.

After synchronizing release metadata to 0.5.0 / 2026-11-05, uv lock, uv sync,
locked all-extras sync, Ruff lint/format, ty and all 370 tests passed again on
Python 3.14.4. Only the local package version changed in the lockfile. The interpreter
matrix above preceded this metadata-only update and was not repeated; runtime code,
tests and dependency versions remained identical.

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
