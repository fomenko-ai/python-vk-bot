# VK API support

Verification date: **2026-11-06** (buttons and event answers). Implementation target:
**5.199**, represented as a string.
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
| messages.edit | Bot.edit_message / edit_message_media; message_id or documented cmid, attachment and keyboard, returns bool |
| messages.delete | Bot.delete_message; one message_id or peer-scoped cmid; explicit recipient-side deletion |
| photos.getMessagesUploadServer / photos.saveMessagesPhoto | Bot.upload_photo; multipart photo upload and typed saved attachment |
| docs.getMessagesUploadServer / docs.save | Bot.upload_document; doc/audio_message upload and typed saved attachment |
| messages.getByConversationMessageId | Bot.get_message; typed Message or None for an empty items list |
| messages.sendMessageEventAnswer | Bot.send_message_event_answer; ShowSnackbar or raw mapping, bool result |
| users.get | Bot.get_user_info; typed User or None; optional profile fields |
| groups.getLongPollServer | Bot.get_long_poll_server; secret key and typed cursor |
| Bots Long Poll a_check | Async LongPoll; failed=1/2/3 recovery and bounded retry delay |
| message_new | Typed Message including optional geo; preserved raw object |
| message_event | Typed MessageEvent; separate envelope and object event IDs |
| Five donut_subscription_* Callback events | Typed DonutSubscriptionEvent, user context, handler and filters; no synchronized access state |
| Callback HTTP | Callback authentication/confirmation and optional ASGI receiver |
| Other events | Raw Update.object retained; generic Handler can process them |

### Request and response inventory

- `messages.send`: peer_id, message, random_id, keyboard JSON,
  attachment, dont_parse_links; forwarding uses forward JSON with source peer_id and
  conversation_message_ids. Only single-recipient sends are wrapped. Raw Bot.request
  can return other documented response forms without implying typed coverage.
- `messages.edit`: peer_id, optional message/attachment, exactly one message_id/cmid, keyboard JSON,
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

## Buttons and event answers

Rechecked on **2026-11-06** at implementation time through direct HTTPS retrieval:
the [version history](https://dev.vk.com/ru/reference/versions) still lists **5.199** first.
The [button types](https://dev.vk.com/ru/api/bots/development/keyboard/key-types),
[keyboard structure](https://dev.vk.com/ru/api/bots/development/keyboard),
[callback actions](https://dev.vk.com/ru/api/bots/development/keyboard/callback-keys) and
[answer method](https://dev.vk.com/ru/method/messages.sendMessageEventAnswer) establish
the outgoing contracts. The official
[object schema](https://github.com/VKCOM/vk-api-schema/blob/master/messages/objects.json)
also describes open_link (label, link, optional payload) and location (optional payload).

- Typed open-link/location buttons serialize inside `action`, without color. Only
  text/callback buttons use color. A location row allows at most two buttons.
- VK documents payload as a JSON-object string of at most 255 characters. Payload
  strings remain caller-controlled; the library does not validate these limits.
- `ShowSnackbar` serializes a flat action object with fixed type and text. Its
  90-character maximum follows the callback guide. The raw mapping path remains
  available for other VK actions and does not apply model validation.
- The method uses a community token with the `messages` permission and requires
  event_id, user_id and peer_id from the message_event. Its success result is 1.

Documentation uncertainty: the button-types table mentions message_new for callback
payloads, while its callback description and dedicated callback guide specify
message_event. CallbackButton follows the latter; no message_new delivery is inferred
for callback clicks. No authenticated delivery was tested. See the
[keyboard guide](keyboards.md) for limits and the precise serialization contract.

## HTTP Retry-After

`HTTPError(status_code, *, retry_after=None)` exposes an optional delay in seconds.
The shared HTTP transport reads the header for every non-success HTTP response,
including API calls, uploads and Long Poll requests. It accepts integer nonnegative
ASCII seconds and HTTP-date (including obsolete HTTP date forms), following
[RFC 9110 sections 10.2.3 and 5.6.7](https://www.rfc-editor.org/rfc/rfc9110.html#section-10.2.3).
Date delays are relative to the local UTC clock; clock skew can affect the result.
Past dates produce 0.0. Missing, malformed or non-finite values produce None; decimal
fractions, signs and exponent notation are not valid numeric header values.

The exception stores only status_code and the parsed delay as custom attributes.
It does not attach the response, headers, credentials or request body. Transport and
Bot methods do not wait or retry. The polling loop retains its existing recovery
policy and does not use this header to change its backoff.
HTTP 429 is HTTPError; a successful HTTP response with VK error 6 is RateLimitError.
No delay is invented from an API error code. VK is not assumed to guarantee this
header; live availability remains unverified.

## Donut contracts

Rechecked on **2026-11-04** when implementation resumed: the official
[version history](https://dev.vk.com/ru/reference/versions) still lists **5.199** first.
The event fields were verified against the official
[community event documentation](https://dev.vk.com/ru/api/community-events/json-schema#donut_subscription_create)
through direct HTTPS retrieval. The web browsing tool could not open dev.vk.com;
direct retrieval succeeded. No authenticated requests were made.

| Event | Object fields documented by VK |
| --- | --- |
| donut_subscription_create | user_id integer, amount integer, amount_without_fee float |
| donut_subscription_prolonged | user_id integer, amount integer, amount_without_fee float |
| donut_subscription_cancelled | user_id integer |
| donut_subscription_expired | user_id integer |
| donut_subscription_price_changed | user_id integer, amount_old/amount_new integer, amount_diff/amount_diff_without_fee float |

Amounts are rubles. The official
[callback schema](https://github.com/VKCOM/vk-api-schema/blob/master/callback/objects.json)
contains no Donut definitions at verification time. The prose lists field types but
does not supply explicit per-event required flags. Therefore the shared model requires
a positive integer user_id as a library validation rule, while monetary fields are
optional and preserve absence as None. This is not a claim that VK omits those fields.
Unknown fields survive. No level_id, payment dates or access deadlines are modeled.

The official [Donut methods](https://github.com/VKCOM/vk-api-schema/blob/master/donut/methods.json),
[objects](https://github.com/VKCOM/vk-api-schema/blob/master/donut/objects.json) and
[responses](https://github.com/VKCOM/vk-api-schema/blob/master/donut/responses.json)
identify version 5.199 and establish these limits:

- isDon and getSubscription accept owner_id and require a user token. They do not
  declare a user_id argument for arbitrary subscriber checks with community tokens.
- getSubscriptions requires a user token and accepts fields/offset/count, not user_id.
- getSubscription returns owner_id, amount, next_payment_date and status; documented
  status values are active/expiring, not expired. level_id is not in this contract.
- next_payment_date is not established as a guaranteed paid-access termination date.

The library adds no Donut method wrappers, automatic reconciliation or authorization
policy. API errors remain errors, including code 15; they must not be converted into
negative subscription results. Callback parsing is supported without claiming Donut
delivery through Bots Long Poll. Live community delivery remains unverified.
See the [Donut guide](donut.md) for event/entitlement boundaries and duplicate handling.

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
- Additional message and keyboard fields are retained, not fully validated. Keyboard accepts
  typed text/callback/open-link/location buttons and raw VK action dictionaries;
  raw actions are caller-controlled.
- No schema generator is justified for the small current coverage.
- Network-free regression tests cover button/event-answer serialization, validation,
  HTTP Retry-After and existing behavior. Live integration is not run.
  See [verification results](verification.md).
- No automatic community provisioning, bulk sending, persistent state,
  distributed deduplication, or durable event queue is provided.

## Media verification and uncertainties

On 2026-11-01 the official version history, photo/document upload guides, upload-server
and save method pages, messages.edit and messages.delete were retrieved directly over
HTTPS and compared with VKCOM schemas. The web-reading tool could not open dev.vk.com;
direct retrieval succeeded. The target remains 5.199. No authenticated calls were made.

Community methods require the corresponding messages/photos/docs permissions. Uploads
do not grant permission to initiate a conversation. Photos use multipart field `photo`
and a server/photo/hash save tuple; documents use field `file` and a file save token.
Upload URLs carry their own query credentials, are not logged intact and receive no
community Authorization header. Upload/save/edit failures are separate and not retried.

The edit method documents `attachment`, `keyboard`, `message_id` and `cmid`, plus errors
for age, message kind and pinned messages. This confirms the request shape, not a live
photo-replacement result. Omitted fields have no library-level preservation guarantee.
The schema and method page disagree on the text length limit; no numeric edit window
or unified local text limit is introduced.

The delete schema returns full per-message result objects, while the method page only
describes per-message integer success. The wrapper validates full results and also
accepts an integer mapping keyed by a global message_id. cmid requests require full
results to avoid confusing identifier scopes. Both live response forms remain unverified.
The upload-server schema mentions graffiti, but the method page explicitly describes
doc/audio_message; only the latter two are exposed by upload_document.

Network-free media regression tests cover the new contracts and failures. An opt-in live
integration test is implemented, but has only been collected with live execution disabled.
It uses documented messages.getById to discover the cmid of its own newly sent message;
the current VKCOM method/response schemas were rechecked for this test on 2026-11-01.
The current uploader buffers file
content; it does not claim practical support for VK's maximum document size. The map
example is implemented but has not been run against VK. See [media API](media-api.md)
for detailed contracts, published upload limits, source links and remaining verification.

## Typed keyboard verification

On **2026-11-02**, direct HTTPS retrieval of the official version history confirmed
5.199 as its newest documented entry. The keyboard guide was also retrieved directly;
the web reader could not open these pages. The VKCOM message object schema was checked
and still declares 5.199. No API version or dependency change is made.

Text/callback actions require a label and accept a string payload. Typed button models
encode dictionary/Pydantic payloads and emit the nested action plus color envelope.
ButtonColor follows the guide's primary/secondary/positive/negative list; the schema
uses default instead of secondary. This discrepancy is recorded rather than introducing
an alias or claiming that both spellings are valid. Raw dictionaries remain unrestricted
VK structures. Numeric limits and live community delivery remain unverified; no new
numeric validators or authenticated calls were introduced. See [keyboards](keyboards.md).

## Sources

- [Keyboard guide](https://dev.vk.com/ru/api/bots/development/keyboard)
- [Message and keyboard object schema](https://github.com/VKCOM/vk-api-schema/blob/master/messages/objects.json)
- [VK versions](https://dev.vk.com/ru/reference/versions)
- [messages.send](https://dev.vk.com/ru/method/messages.send)
- [messages.edit](https://dev.vk.com/ru/method/messages.edit)
- [messages.getById](https://dev.vk.com/ru/method/messages.getById)
- [Bots Long Poll](https://dev.vk.com/ru/api/bots-long-poll/getting-started)
- [Callback API](https://dev.vk.com/ru/api/callback/getting-started)
- [Method schema](https://github.com/VKCOM/vk-api-schema/blob/master/messages/methods.json)
- [Event schema](https://github.com/VKCOM/vk-api-schema/blob/master/callback/objects.json)
- [Error schema](https://github.com/VKCOM/vk-api-schema/blob/master/errors.json)
