# Python compatibility branches

Choose the branch that matches your application's Python version:

| Branch | Package requirement | Verified runtime | Verification |
| --- | --- | --- | --- |
| `main` | Python >=3.14 | CPython 3.14.4 and 3.15.0–3.15.2; 109 tests each | [Main results](verification.md) |
| `compat/py39` | Python >=3.9 | CPython 3.9–3.14; 112 tests per interpreter | [Compatibility results](https://github.com/fomenko-ai/python-vk-bot/blob/compat/py39/docs/development/verification.md) |

These are separate implementations of the same `python-vk-bot` distribution and
`python_vk_bot` import namespace. Install one branch per environment. Runtime support
for versions beyond those recorded in the verification results and other Python
implementations has not been established. Both branches
use Python 3.14 as their default contributor interpreter.

## Install from GitHub

From a consumer project using uv:

```bash
# Main branch, Python >=3.14:
uv add git+https://github.com/fomenko-ai/python-vk-bot.git --branch main

# Compatibility branch, Python >=3.9:
uv add git+https://github.com/fomenko-ai/python-vk-bot.git --branch compat/py39
```

With pip, choose one of these commands:

```bash
python -m pip install "python-vk-bot @ git+https://github.com/fomenko-ai/python-vk-bot.git@main"
python -m pip install "python-vk-bot @ git+https://github.com/fomenko-ai/python-vk-bot.git@compat/py39"
```

For the optional Callback HTTP receiver, select the `callback` extra:

```bash
uv add "python-vk-bot[callback] @ git+https://github.com/fomenko-ai/python-vk-bot.git@main"
# Or, for the compatibility branch:
python -m pip install "python-vk-bot[callback] @ git+https://github.com/fomenko-ai/python-vk-bot.git@compat/py39"
```

Dependencies are installed automatically from the selected branch's `pyproject.toml`.
Its development dependency group is not installed into the consumer project.
The repository's `uv.lock` reproduces contributor environments; consumers resolve and
lock their own dependencies. For reproducible Git installs, pin a reviewed commit.
A branch name follows future commits; a package version alone does not identify
which branch's source was installed. These Git commands do not depend on a PyPI release.

For local development, check out the desired branch and run `uv sync --locked --all-extras`.
To use a local checkout in another project, run `uv add /path/to/python-vk-bot` there.

## Branch-specific behavior

`main` uses Python 3.14 syntax and standard-library features. Its metadata, dependencies
and Ruff target reflect that requirement.

`compat/py39` retains the documented public API while adapting annotations and async
resource handling for older interpreters. It uses conditional dependency constraints,
including `pydantic-settings` for Python 3.9 and `async-timeout` with the Callback extra
on Python 3.9/3.10. Python >=3.11 uses `asyncio.timeout`. Context is a regular dataclass
on that branch. See its [implementation guide](https://github.com/fomenko-ai/python-vk-bot/blob/compat/py39/docs/development/python-compatibility.md)
for details and its verification commands.

The library remains alpha. Python compatibility does not add a stable-API guarantee
or change the documented VK API version and delivery semantics.

## Maintaining both branches

Develop and run the configured checks on Python 3.14 first. After an authorized commit
to `main`, use the [transfer skill](../../skills/sync-compat-branch/SKILL.md) to carry
applicable changes to `compat/py39`, retaining source commit references.

Transfer shared descriptions, examples and behavior selectively. Keep Python requirements,
conditional dependencies, tool targets, installation instructions and release metadata
appropriate to each branch. Regenerate its lockfile after dependency metadata changes.
After changes affecting code, dependencies or tests, run the branch's syntax and runtime
scripts after the Python 3.14 contributor checks:

```bash
./python_compatibility_tests/run_python_compatibility.sh
./python_compatibility_tests/run_runtime_compatibility.sh
```

On `main`, both scripts discover installed CPython >=3.14 through uv and check each
distinct installation key. On `compat/py39`, the default matrix remains Python 3.9–3.14.
Arguments replace the default selection, for example `run_runtime_compatibility.sh 3.14`.
Neither script downloads interpreters. An empty discovered matrix or an unavailable
requested interpreter fails the command. Runtime checks use isolated environments with
locked development and Callback dependencies, preserving the contributor .venv.

See [main's verification guide](verification.md) for results and failure behavior.
Automatic discovery makes newer installed interpreters eligible for checks; advertise
support only after successful dependency and regression checks. Syntax checks alone do
not establish runtime compatibility.
