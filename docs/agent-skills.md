# Agent Skills

Agent Skills are instructions and supporting resources that an AI coding agent loads for a
specific task. They do not run as part of a bot. These skills use the
[Agent Skills format](https://agentskills.io/specification): a `SKILL.md` with name and
description, followed by instructions linking to detailed references as needed.

| Skill | Location | Audience | Distribution |
| --- | --- | --- | --- |
| `vk-api-upgrade` | `skills/vk-api-upgrade/` | Maintainers | Repository only |
| `telegram-to-vk` | `python_vk_bot/.agents/skills/telegram-to-vk/` | Library users | Bundled with Python package |

Use `vk-api-upgrade` to audit API versions, methods, models and event delivery, or prepare
an approved upgrade. Use `telegram-to-vk` to migrate a python-telegram-bot application while
preserving its business logic and explicitly accounting for VK differences and missing features.

## Install the migration skill

There are three separate steps: install the Python package, locate its bundled files, and
expose the chosen skill to your AI coding agent. Package installation alone does not register a skill.

In the bot project's root, install the package and its migration skill:

```bash
uv add python-vk-bot
uvx library-skills
```

Select `telegram-to-vk` and the `.agents/skills` target when prompted. The external
[Library Skills tool](https://library-skills.io/use/) scans installed project dependencies
and links selected skills into the project. It is not a python-vk-bot runtime dependency.
The installed package remains the canonical source. Rerun the command after moving or
recreating the environment to reconcile managed links.

To install from a local checkout, run `uv build` in this repository, then in a separate bot
project use the actual absolute path of the resulting wheel:

```bash
uv add /absolute/path/to/python_vk_bot-0.1.1-py3-none-any.whl
uvx library-skills
```

To inspect discovery and installation status without installing new skills:

```bash
uvx library-skills list --json
```

The wheel and source distribution contain the migration skill under the package's
`.agents/skills/` directory, following the
[Library Skills package layout](https://library-skills.io/create/). To read the bundled
resources directly in the environment where python-vk-bot is installed:

```python
from importlib.resources import files

skill = files("python_vk_bot").joinpath(".agents", "skills", "telegram-to-vk")
print(skill.joinpath("SKILL.md").read_text(encoding="utf-8"))
print(skill.joinpath("references", "migration-mapping.md").read_text(encoding="utf-8"))
```

For AI coding agents that support `.agents/skills` and symlinked skill directories, the link
makes the skill available in the consumer project. Consult your AI agent's documentation for
supported discovery paths and reload instructions. Reading the resources or creating a link
verifies file availability, not whether a particular running client loaded it.

## Enable the internal maintenance skill

`vk-api-upgrade` is excluded from Python distributions. Maintainers use its source in this
checkout. On a system supporting symlinks, run from the repository root:

```bash
mkdir -p .agents/skills
ln -s ../../skills/vk-api-upgrade .agents/skills/vk-api-upgrade
```

Inspect an existing destination before changing it; do not overwrite another skill.
The link is local setup, not a second implementation. No link is created automatically by
package installation. A maintainer may instead link the source directory from their personal
`~/.agents/skills` if their AI agent supports that location and they deliberately want it
available across projects.

The internal skill references repository files, so use it with the source checkout available.
The bundled migration skill is self-contained and works without repository docs.

## Example requests

- `Use $vk-api-upgrade to audit this checkout against current official VK documentation.
  Report confirmed gaps and propose changes before editing.`
- `Use $telegram-to-vk to inspect this Telegram bot and propose a VK migration, including
  unsupported features and the required community configuration.`
- `Use $telegram-to-vk to implement the approved handler migration while preserving the
  existing business services and persistence.`

## Approvals and security

Skills follow the target project's `AGENTS.md` and existing user authorization. In this
repository, changes spanning more than two files require plan approval. Editing or adding
tests requires approval of the corresponding main-code changes and separate authorization
for test edits. Running existing tests is allowed. The migration skill does not authorize
changes to the framework or unrelated projects.

Use mock HTTP responses and events for automated verification. Keep community tokens,
Callback secrets and private messages out of examples, logs and task records. Migration
does not grant VK permissions or guarantee Telegram feature parity. An API audit must
recheck official VK documentation and report unavailable or conflicting sources.

## Maintainer validation

Validate skill frontmatter and reference links, then build with `uv build`. Inspect both
archives for `python_vk_bot/.agents/skills/telegram-to-vk/SKILL.md` and its
`references/migration-mapping.md`. Verify the internal skill is absent. Install the wheel
and sdist into separate temporary Python 3.14 consumer projects with uv, read both resources
outside this checkout, and check Library Skills discovery/installation there. Keep generated
archives and environments out of Git. Run the repository's configured quality checks.

Keep the instructions and API examples synchronized with the code that ships them. Do not
add installer hooks, duplicate implementations or runtime dependencies to register skills.
