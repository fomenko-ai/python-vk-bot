# Project Coding Rules

These rules apply to AI-assisted changes in `python-vk-bot`, a Python framework for VK community bots.

1. Before making changes that affect more than two modules or files, propose an architectural option first and wait for user approval.
2. **Change tests only after the user has approved the changes in the main project code.** Preserve this approval gate to avoid unnecessary work and token usage. You may inspect existing tests and propose test changes before approval, but do not edit them.
3. Delete `*/__pycache__` directories only after an explicit user request.
4. Prefer focused changes over broad rewrites. Do not implement proposed architecture without approval when rule 1 applies.

## Architecture and python-telegram-bot Compatibility

The project aims for a developer experience conceptually consistent with `python-telegram-bot` while preserving VK-specific semantics.

1. **Architecture-first:** Before introducing or changing public APIs, handlers, models, or abstractions, evaluate their equivalents in the current stable `python-telegram-bot` release. Record the reference version and source in architectural documentation.
2. **Naming:** Prefer familiar names (`Application`, `ApplicationBuilder`, `Bot`, `Update`, `Handler`, `Context`, `filters`) only when the underlying concepts are genuinely equivalent. These names are examples, not mandatory classes.
3. **Developer experience:** Favor comparable application lifecycle, handler registration, filtering, context, and error-handling patterns when practical.
4. **VK semantics first:** Do not force Telegram-specific concepts onto VK community messaging. Explicitly model VK-specific events, permissions, keyboards, and transport behavior.
5. **Public API stability:** Document the current public API without historical interface comparisons or speculative compatibility layers. Document stability guarantees explicitly.
6. **Async-first:** Avoid blocking the event loop in HTTP operations, event polling, dispatch, and lifecycle hooks. Support cancellation and graceful shutdown.
7. **Typed boundaries:** Use type annotations and Pydantic v2 for structured VK API request/response and event validation where useful. Preserve access to unknown or extra VK fields when appropriate.
8. **Separation of concerns:** Keep HTTP transport, VK API methods, data models, update ingestion, dispatch, handlers, and application lifecycle independently understandable and testable.
9. **Documentation:** Maintain `docs/architecture/python-telegram-bot-compatibility.md` when architecture is established or changed. Explain material differences and cite relevant upstream documentation. Do not claim proposed components are implemented.
10. **No blind replication:** Use `python-telegram-bot` as a design reference, not code to copy. Avoid speculative abstractions.

## VK API and Messaging

1. Before changing version-dependent behavior, verify the latest officially documented applicable VK API version. Record the verified version, sources, verification date, and uncertainties in `docs/development/api-compatibility.md`. Recheck the target version when API compatibility work resumes; do not rely on a previously recorded version without verification.
2. Never invent undocumented VK methods, fields, events, or numeric rate limits. Keep API-version-specific assumptions explicit.
3. Use community tokens with only required permissions. Never assume bots may initiate arbitrary conversations with users.
4. Support VK Bots Long Poll and Callback API according to their distinct delivery and lifecycle semantics; do not treat them as interchangeable transports.
5. Design for network failures, Long Poll reconnection, duplicate event delivery, and safe processing. Use idempotency safeguards where needed.
6. Handle VK API errors, request throttling, timeouts, and retries explicitly. Do not automatically retry non-idempotent operations without safeguards.
7. Validate Callback API secrets and confirmation flows where applicable; avoid logging credentials or sensitive message contents.

## Python and Tooling

1. Develop and verify on Python 3.14, as approved by the user. Assess other Python versions only after implementation and regression testing are complete; do not advertise unverified support. Keep the existing root package layout unless a new architectural decision is approved.
2. Fully type production code and tests where practical.
3. Use Ruff for formatting, linting, and import sorting; use ty for static type checking unless the repository explicitly configures another tool. Do not introduce overlapping tooling without justification.
4. Use `pathlib.Path` for filesystem paths.
5. Keep runtime dependencies in `[project].dependencies`, optional feature dependencies in `[project.optional-dependencies]`, and development tools in the configured development dependency group.
6. Use uv for dependency management when configured by the project. Keep packaging metadata and lockfiles consistent.
7. Prefer a reusable async HTTP client (evaluate `httpx.AsyncClient` and `aiohttp`), injectable where useful for tests. Reuse connections, configure timeouts, and close owned resources reliably. Avoid synchronous `requests` in asynchronous execution paths.
8. Use Pydantic v2 deliberately at API boundaries; do not build redundant models or validate the same data unnecessarily.

## Tests and Resource Lifecycle

1. **Do not edit or add tests until the user approves the corresponding main-code changes.** After approval, add or update focused regression tests for the approved behavior.
2. Unit tests must not depend on live networks, VK credentials, or external services. Mock HTTP responses and event delivery.
3. Cover request serialization, API errors, validation, handlers, filters, event dispatch, retries, Long Poll reconnection, cancellation, and graceful shutdown as applicable to implemented features.
4. Keep integration tests separate and explicitly marked. Tests requiring live VK credentials must be opt-in and disabled by default.
5. Use `try/finally`, async context managers, or equivalent cleanup for owned HTTP sessions, background tasks, and other resources, including failure paths.
6. Register pytest markers and run pytest with `--strict-markers` when markers are used.
7. Do not create tests for proposed or unimplemented behavior as if it already exists.

## Logging and Test Artifacts

1. Use standard Python logging. Avoid adding reporting frameworks without a concrete requirement.
2. Never log passwords, tokens, `SecretStr` values, authorization headers, or complete message/event payloads containing potentially sensitive user data.
3. Keep generated databases, logs, caches, virtual environments, credentials, and test artifacts out of Git.
4. Do not generate persistent test reports or artifact directories unless required by the project or requested by the user.

## Docker

1. Do not introduce Docker or Docker Compose without a concrete requirement.
2. If container support is added, keep builds reproducible and exclude `.git`, `.env`, credentials, virtual environments, caches, and generated artifacts from the build context.
3. Never start external services implicitly as part of ordinary library execution or default tests.

## Required Verification

After changing files, run the narrowest relevant checks first. Before handoff, run available configured quality checks, without violating the test-approval rule:

```bash
uv sync
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run pytest --strict-markers
```

1. Run only commands supported by the repository's actual configuration; report missing tools or configuration rather than silently assuming success.
2. Run `uv lock` after dependency metadata changes and verify `uv sync --locked` when a `uv.lock` is maintained.
3. If a configured pre-commit hook modifies files, review intended changes and rerun applicable checks.
4. Report each check as passed, failed, or not run, with reasons. Running existing tests does not authorize modifying tests.

## Agent Work Records

1. Store resumable task state in `.agent-work/active/`, using one file per issue or independently deliverable change.
2. Read the applicable task file before changing code and verify its claims against Git status, diff, and current sources.
3. Keep state, plan, verification results, blockers, and next action current.
4. Update the task file after significant milestones or decisions and before ending unfinished work.
5. Never store credentials, secrets, raw private logs, or private reasoning in task files.
6. Do not modify another active worker's task without coordination.
7. On completion, move lasting knowledge into project documentation and a concise summary into `.agent-work/completed/`.

## Architecture Decisions

1. Create decision records in `docs/decisions/` only for significant long-lived architectural choices with meaningful alternatives.
2. Use `docs/decisions/template.md` if present; otherwise establish a template before the first record.
3. Keep accepted decisions in Git; mark replaced records as `superseded` and link replacements.
4. Update normal project documentation after decisions; decision records explain why, while documentation describes current behavior.
5. Before changing transport contracts, public API, event models, dispatcher behavior, or application lifecycle, review relevant existing decisions.

## Changelog Management

1. Maintain a root-level `CHANGELOG.md` as the human-readable history of user-visible changes. Create it when preparing the first approved release or when the user requests it; do not invent historical releases.
2. Follow the Keep a Changelog structure with versioned release sections. Use relevant categories such as `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, and `Security`.
3. For approved changes that affect public APIs, supported VK API behavior, dependencies, compatibility, or user-visible functionality, update `CHANGELOG.md` in the same change set. Do not record internal-only edits unless they materially affect users.
4. Describe changes from the library user's perspective, concisely and factually. Clearly flag breaking changes and link to migration documentation when applicable.
5. Do not assign release versions or dates, move entries between release sections, or claim a release was published without explicit user approval or verifiable release evidence.
6. Respect the approval gates above: changelog edits do not authorize unapproved multi-file changes or test modifications. If approval is pending, propose the changelog entry without editing the file.

## Commit Message Rules

Follow the existing linear commit history style:

1. Use an English Conventional Commit subject: `<type>: <imperative summary>`.
2. Prefer `feat`, `fix`, `refactor`, and `chore`.
3. Keep the subject short, lowercase after the type, and without a trailing period.
4. Add a scope only when it clarifies the change.
5. Base the message on staged changes (`git diff --cached`).
6. For broad commits, describe the dominant change in the subject and supporting work in the body when needed.
