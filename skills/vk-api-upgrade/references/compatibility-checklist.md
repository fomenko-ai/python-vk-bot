# Compatibility checklist

Use this checklist against the current checkout; the inventory below is a starting point,
not a substitute for reading the implementation.

## Evidence and scope

- [ ] Read `AGENTS.md`, applicable `docs/decisions/`, task records, Git status and diff.
- [ ] Inspect `_config.py`, `settings.py`, `bot.py`, `transport.py`, `models/`, `long_poll.py`,
  `callback.py`, `application.py`, relevant tests and `docs/development/api-compatibility.md`.
- [ ] Identify explicit version overrides as well as defaults; outbound API and community
  event versions are configured independently.
- [ ] Reopen [VK's version history](https://dev.vk.com/ru/reference/versions). Record the latest
  officially documented applicable API version and verification date; do not reuse old findings.
- [ ] Consult exact method/event documentation and the official
  [VKCOM schema](https://github.com/VKCOM/vk-api-schema) as supporting evidence. Record a tag or
  commit when using schema files. Resolve conflicts explicitly; do not derive API versions
  from schema package suffixes.

## API boundaries

| Area | Questions to answer |
| --- | --- |
| Methods | Are implemented methods available for community tokens at the target version? |
| Requests | Have required/optional fields, types, defaults or JSON serialization changed? |
| Responses | Do return types, empty results and API error envelopes match the wrappers? |
| Models | Do Pydantic v2 boundaries validate useful structure and retain unknown fields? |
| Events | Are envelopes, nested objects, identifiers and optional fields documented? |
| Authentication | Are token type, permissions and conversation access requirements explicit? |
| Errors | Are API codes distinguished from HTTP, network and validation failures? |
| Limits | Are any claimed limits sourced and scoped to the relevant method/token? |
| Deprecations | Which confirmed removals or replacements affect implemented coverage? |

Current wrappers include `messages.send`, `messages.edit`,
`messages.getByConversationMessageId`, `messages.sendMessageEventAnswer`, `users.get`
and `groups.getLongPollServer`. `Bot.request` is a raw escape hatch, not typed support
for every VK method. Inspect the actual code to detect additions or removals.

## Delivery, retries and security

- [ ] Check [Bots Long Poll](https://dev.vk.com/ru/api/bots-long-poll/getting-started):
  server/key/ts, wait and read timeouts, failed responses, cursor recovery and cancellation.
- [ ] Check [Callback API](https://dev.vk.com/ru/api/callback/getting-started): group and secret
  validation, confirmation, acknowledgement, duplicate delivery and shutdown behavior.
- [ ] Keep HTTP Callback delivery distinct from the interactive `message_event` event.
- [ ] Check `message_new`, `message_event`, unknown events and extra-field retention.
- [ ] Review duplicates, partial handler failure, restart and multiple-worker behavior;
  bounded in-memory deduplication does not guarantee exactly-once effects.
- [ ] Review polling retries separately from API mutations. Preserve stable `random_id`
  safeguards where sending is retried by a caller; do not promise unlimited deduplication.
- [ ] Verify owned HTTP clients/tasks close on errors and cancellation without blocking.
- [ ] Exclude tokens, Long Poll keys, headers and private message/event bodies from logs.

## Plan, verification and documentation

- [ ] Present each finding with evidence, affected files, proposed fix and user-visible risk.
- [ ] Obtain required implementation approval; seek test-edit authorization only after the
  corresponding main-code changes are approved. Do not add tests for proposed behavior.
- [ ] Run applicable existing tests for serialization, errors, validation, dispatch, retries,
  reconnection, cancellation and shutdown using mocked responses and events.
- [ ] Run configured `uv sync`, Ruff lint/format checks, ty and `pytest --strict-markers`.
  Follow lockfile requirements if metadata changes. Report passed/failed/not-run explicitly.
- [ ] Update the compatibility document and relevant public documentation for approved work;
  maintain PTB references when public architecture changes and add user-visible changelog entries.
- [ ] Record limitations of offline verification and any unresolved documentation gaps.

## Report fields

Record: configured version; verified target or unresolved status; date; official URLs;
confirmed incompatibilities; unverified assumptions; affected modules; proposed/implemented
changes; approval status; checks and results; remaining risks; next action.
