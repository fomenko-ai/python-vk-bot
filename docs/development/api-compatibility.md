# VK API support

Verification date: **2026-10-31**. Implementation target: **5.199**, represented as a string.
The official [version history](https://dev.vk.com/ru/reference/versions) lists 5.199 as
the newest documented version. Its entry describes internal changes without a method,
parameter, or response change. The official [VKCOM schema](https://github.com/VKCOM/vk-api-schema)
README also targets 5.199; package version 5.199.99 identifies the schema package, not
an API version to send.

The version history, Long Poll, Callback, messages.send and messages.edit pages were
verified through direct HTTPS retrieval. No authenticated calls were made. Availability
and permissions with live community tokens remain unverified. Recheck these sources
before changing version-dependent behavior.

## Implemented coverage

| Method / delivery | Library support |
| --- | --- |
| messages.send | Bot.send_message / forward_message; one peer, integer result; nonzero int32 random_id |
| messages.edit | Bot.edit_message; sends message_id or documented cmid, returns bool |
| messages.getByConversationMessageId | Bot.get_message; typed Message or None for an empty items list |
| messages.sendMessageEventAnswer | Bot.send_message_event_answer; bool result |
| users.get | Bot.get_user_info; typed User or None; optional profile fields |
| groups.getLongPollServer | Bot.get_long_poll_server; secret key and typed cursor |
| Bots Long Poll a_check | Async LongPoll; failed=1/2/3 recovery and bounded retry delay |
| message_new | Typed Message including optional geo; preserved raw object |
| message_event | Typed MessageEvent; separate envelope and object event IDs |
| Callback HTTP | Callback authentication/confirmation and optional ASGI receiver |
| Other events | Raw Update.object retained; generic Handler can process them |

### Request and response inventory

- `messages.send`: peer_id, message, random_id, keyboard JSON,
  attachment, dont_parse_links; forwarding uses forward JSON with source peer_id and
  conversation_message_ids. Only single-recipient sends are wrapped. Raw Bot.request
  can return other documented response forms without implying typed coverage.
- `messages.edit`: peer_id, message, exactly one message_id/cmid, keyboard JSON,
  dont_parse_links; documented success response is 1.
- `messages.getByConversationMessageId`: peer_id, conversation_message_ids;
  response has count and items. Fields unknown to Message remain accessible.
- `messages.sendMessageEventAnswer`: event_id, user_id, peer_id, optional event_data JSON.
- `users.get`: user_ids and fields=screen_name; response is an array.
- `groups.getLongPollServer`: positive group_id; response has key, server, ts.
- Long Poll: act=a_check, key, ts, wait. No community Authorization header is sent to
  the polling server. Request read timeout exceeds the requested wait.
- Event envelope: type, group_id, event_id, v, object. Callback secret is checked before
  validation and is excluded from the dispatched Update. Unknown fields are retained.

## Messaging contracts

- Generated random_id values are nonzero positive int32 integers. Callers can provide a stable
  nonzero signed int32 ID; no message sends are automatically retried.
- `Bot.edit_message` maps its conversation_message_id argument to VK's documented cmid.
- Forwarding identifies its source by message.peer_id, not message.from_id; these differ
  in group conversations.
- Batch sending remains outside the typed wrapper.
- Attachments retain arbitrary JSON, including fields not explicitly modeled by the library.
- Coverage is limited to the methods and fields described here; other VK API capabilities
  are not claimed as typed library features.

## Delivery and failure semantics

Long Poll failed=1 advances to the supplied ts and reports possible history loss.
Failed=2 refreshes session credentials while keeping the previous cursor. Failed=3
obtains both credentials and a new cursor. Recovery is iterative. Unexpected shapes
or unknown failure codes fail visibly. Network failures, HTTP 429/5xx and VK error 6
are retried only in the polling loop; authentication failures propagate. Delay caps
are local retry policy, not claimed VK request limits.

Callback requires the configured group and secret even for confirmation. Confirmation
returns the configured code; ordinary success returns HTTP 200 with `ok`. Failures are
not acknowledged as successful. Event deduplication is bounded, in-memory, and only
records successful dispatch; it does not provide exactly-once side effects. See the
[architecture](../architecture/project-architecture.md) for partial-failure limitations.

Community tokens need the permissions for the selected methods. Bots cannot assume they
may initiate conversations; VK permission/privacy errors are propagated without retries.
Long Poll/Callback must be enabled and subscribed to relevant events in community settings.
The event API version is configured there independently from the outbound request version.

## Uncertainties and remaining work

- The schema describes message_event.payload as a string; deployed integrations may use
  JSON objects. The model intentionally preserves either form without automatic decoding.
- Additional message and keyboard fields are retained, not fully validated. Keyboard action
  dictionaries remain caller-supplied VK structures; unsupported semantics are not invented.
- No schema generator is justified for the small current coverage.
- Network-free regression tests cover the implemented behavior; live-token integration is not run.
  See [verification results](verification.md).
- No automatic community provisioning, upload methods, bulk sending, persistent state,
  distributed deduplication, or durable event queue is provided.

## Sources

- [VK versions](https://dev.vk.com/ru/reference/versions)
- [messages.send](https://dev.vk.com/ru/method/messages.send)
- [messages.edit](https://dev.vk.com/ru/method/messages.edit)
- [Bots Long Poll](https://dev.vk.com/ru/api/bots-long-poll/getting-started)
- [Callback API](https://dev.vk.com/ru/api/callback/getting-started)
- [Method schema](https://github.com/VKCOM/vk-api-schema/blob/master/messages/methods.json)
- [Event schema](https://github.com/VKCOM/vk-api-schema/blob/master/callback/objects.json)
- [Error schema](https://github.com/VKCOM/vk-api-schema/blob/master/errors.json)
