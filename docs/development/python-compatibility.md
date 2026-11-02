# Python compatibility branch

`compat/py39` supports CPython 3.9–3.14 with the same `python-vk-bot` distribution and
`python_vk_bot` import names. Package metadata permits Python >=3.9; later interpreters
and other Python implementations have not been verified. The default contributor
interpreter remains Python 3.14.

The library installs, imports and passes all 272 regression tests on the checked
3.9–3.14 interpreters. Before the media API transfer, both base wheel installation and sdist installation with the
Callback extra were also checked in clean Python 3.9 consumer environments.
See [exact results and reproduction commands](verification.md).

## Installation

The branch must be pushed before another machine can install it from Git. These commands
are templates: replace `OWNER` with the repository owner. They do not imply publication
of either the branch or a new PyPI release. Run them in the consumer project's environment.

```bash
python -m pip install "python-vk-bot @ git+https://github.com/OWNER/python-vk-bot.git@compat/py39"

# With the optional Callback server dependencies:
python -m pip install "python-vk-bot[callback] @ git+https://github.com/OWNER/python-vk-bot.git@compat/py39"

# Alternatively, from a uv consumer project:
uv add git+https://github.com/OWNER/python-vk-bot.git --branch compat/py39
```

For a local checkout, switch it to this branch and install its working tree from the
consumer project (replace the path):

```bash
uv add /path/to/python-vk-bot
```

Runtime dependencies are installed automatically from the branch's package metadata.
The library's development dependency group is not installed into consumer projects.
Consumers resolve their own dependency set; this repository's uv.lock is for reproducing
contributor environments, not a constraint imposed on downstream users. For reproducible
Git installations, select a reviewed commit or release tag and lock the consumer project.
Installing the branch and main into the same environment does not provide two independent
libraries: they have the same distribution and import names.

## Media transfer

Media API, keyboard and map examples are transferred from main commit
`f3b906b66b2192e5a1e42431f191e6a98e04ed36`. Runtime aliases and model annotations
use Python 3.9-compatible typing, and the map state is a regular dataclass.
New concurrency tests use portable timeout and owned-task helpers. Branch-specific
dependencies, Python targets and lifecycle safeguards are retained.

## Runtime choices

- Typed keyboard buttons are transferred from main commit
  `2740cfd3d6e9ca49d1aa8db42b0dfb1071f1d455`. They use `typing.Union` and
  `typing_extensions.TypeAlias`. Button enums use native `StrEnum` on Python 3.11+
  and `str`/`Enum` with value-based `str()` on Python 3.9/3.10; serialized VK values
  and Pydantic validation are equivalent across the checked runtimes. Package version
  is 0.3.0, with the changelog dated 2026-11-02. Python-specific dependencies and
  interpreter targets remain configured for this branch.
- Annotations use Optional/Union, explicit forward references and postponed evaluation.
  Self and TypeAlias come from typing_extensions. Pydantic remains at v2 boundaries.
- Context is a regular dataclass with the same fields, defaults and error repr policy.
- Application creates its internal locks on first use in async code, allowing ASGI
  construction before the event loop starts on Python 3.9. Use one loop per instance.
- Long Poll generators close in finally. run_polling waits without forwarding caller
  cancellation to the child automatically, then cancels and awaits owned polling during
  cleanup. stop() can cancel polling without cancelling the owner; external owner
  cancellation propagates after cleanup.
- Callback uses the standard asyncio timeout on Python >=3.11 and async-timeout >=5.0.1,<6
  on 3.9/3.10. The backport is part of the callback extra only; the base package imports
  without server dependencies. Timeout errors are caught through asyncio.TimeoutError,
  which also works before its aliasing to the built-in TimeoutError.
- Python 3.9 selects pydantic-settings >=2.11,<2.12. Python >=3.10 selects >=2.12,<3.
  Other dependencies are resolved using their declared Python requirements.

## Verification workflow

Run the contributor checks on Python 3.14, then the explicit compatibility matrix:

```bash
uv sync --locked --all-extras
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run pytest --strict-markers
./python_compatibility_tests/run_python_compatibility.sh
./python_compatibility_tests/run_runtime_compatibility.sh
```

The runtime script uses a separate uv environment for each already-installed Python,
installs locked runtime/dev/Callback dependencies and runs all tests with strict markers.
It does not replace the contributor .venv or download Python interpreters. Package
installation may need network access; unit tests block live sockets and DNS. Missing
interpreters, dependency errors and failed tests cause a nonzero exit status.
Pass version arguments to select a subset, such as `3.9 3.11`.

Both production and tests use Ruff's Python 3.9 target. ty also targets 3.9 by default;
the test dependency group includes async-timeout on every interpreter so its conditional
production import can be type-checked from Python 3.14. Consumer installations still
receive that backport only with `[callback]` on Python <3.11.

The public class and method names remain those documented in the architecture. This is
an alpha library; compatibility work does not add a stable-API guarantee. Exact generated
JSON Schema layout and runtime typing implementation objects are not stability guarantees.
VK API version, methods, payloads and delivery policies are not changed by this work.

## References verified on 2026-11-01

- [pydantic-settings 2.11.0](https://pypi.org/project/pydantic-settings/2.11.0/)
  declares Python >=3.9; [2.12.0](https://pypi.org/project/pydantic-settings/2.12.0/)
  declares Python >=3.10.
- [async-timeout 5.0.1](https://pypi.org/project/async-timeout/5.0.1/) documents
  conditional imports and its status as an upstreamed, deprecated backport.
- [Python 3.11 asyncio](https://docs.python.org/3.11/library/asyncio-task.html)
  documents timeout, cancellation and task waiting.
- [Python 3.9 release schedule](https://peps.python.org/pep-0596/) records upstream
  end of life on 2025-10-31.
- [pip Git sources](https://pip.pypa.io/en/stable/topics/vcs-support/) and
  [uv dependency sources](https://docs.astral.sh/uv/concepts/projects/dependencies/)
  document branch, tag and revision installation.
