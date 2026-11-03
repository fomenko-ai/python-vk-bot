# Project architecture

Status: implemented with network-free regression coverage. Python 3.14 baseline.
Unified-queue additions have focused regression coverage. See the
[verification log](../development/verification.md) for completed checks and limitations.
Media additions on `main` have network-free regression coverage. Live media operations
remain unverified; see [media verification status](../development/media-api.md).

## Design goals

The library separates asynchronous HTTP, VK methods, validated events, delivery,
dispatch and application state. Its public API focuses on community bots, explicit
resource ownership and predictable cancellation. Long Poll and Callback have distinct
delivery semantics and share the same update-processing pipeline.

## Current package

```text
python_vk_bot/
  __init__.py        public exports
  settings.py        public, extensible environment-backed BotSettings
  _config.py         shared constraints/defaults and explicit TransportConfig
  bot.py            typed VK method wrappers and raw request escape hatch
  transport.py      reusable HTTPX client, serialization and API envelope handling
  errors.py         safe, structured error categories
  models/
    base.py         extra-field retention policy
    api.py          API errors, envelopes and Long Poll responses
    attachments.py  typed media envelopes, raw fallback and identifier serialization
    messages.py     messages, geo, users and keyboard structures
    keyboards.py    typed outgoing buttons, enums and VK JSON serialization
    events.py       event envelope, typed views and raw object access
  long_poll.py      session acquisition, cursor and recovery
  application.py    lifecycle, managed tasks, queued serial dispatch and duplicate cache
  queues.py         bounded producer interface and private completion records
  context.py        user, peer and application data
  handlers.py       generic/message/message-event/command handlers
  filters.py        predicates and boolean composition
  callback.py       Callback authentication and optional ASGI adapter
```

Bot depends on transport and models. LongPoll depends on Bot. Application owns Bot's
lifecycle, invokes handlers, and can consume LongPoll. Callback feeds Application and
has no dependency on polling. Models have no HTTP/application dependencies.

```mermaid
flowchart LR
    LP[Long Poll] --> U[Validated Update]
    CB[Callback: authenticate] --> U
    U --> Q[Application queue]
    R[Internal Python objects] --> Q
    Q --> A[Application: serial dispatch and VK deduplication]
    A --> H[Handler and Context]
    H --> B[Bot]
    B --> T[HTTPTransport]
    T --> VK[VK API]
```

## Lifecycle and ownership

Bot is an async context manager. An internally created HTTPX client is reused and closed
on shutdown; an injected client remains caller-owned. Requests require initialization.
Default Authorization headers and credential query parameters on injected clients are
rejected to avoid leaking them to Long Poll. API authorization is attached per request.
Redirects are not followed. Network and validation exception text excludes payloads/URLs.
An HTTPX logging filter removes URL query strings from HTTPX's standard request log
records, including unrelated HTTPX query strings in the same process. This prevents
Long Poll keys appearing in INFO logs. Custom transports/hooks must follow the same policy.

Application.initialize initializes Bot and invokes post_init. start starts the consumer
and enables intake. stop rejects new intake/tasks, interrupts idle polling, and drains
active dispatch, managed tasks and accepted events. shutdown invokes post_stop once while
Bot is available, closes Bot's resources and invokes post_shutdown. An async context manager
combines these operations. run_polling is awaitable and owns this lifecycle but never
creates/closes the caller's event loop. Nested contexts are rejected. A handler may call
stop without waiting for itself; it must leave shutdown to the owner. Direct stop does
not invoke post_stop. Hooks must not recursively invoke lifecycle methods. Externally
owned tasks must not outlive their resource owner.

Cancellation propagates. Callback shutdown drains active dispatch; user handlers must
cooperate with cancellation and must not block the event loop. No detached handler tasks
or implicit external service startup occur. Context data remains until explicitly removed
by the caller or the Application instance is discarded.

## Dispatch and state

All process_update calls enqueue events and await completion receipts, including concurrent
Callback requests. update_queue also accepts internal Python objects. One consumer processes
events in insertion order. Numeric groups run in ascending order; only the first matching handler
in each group runs. Generic Handler supports unmodeled events. Filters are synchronous,
short predicates. Regex uses search; commands match an explicit /command token, without
Telegram-specific mentions. A message with geo is still a message; use filters.LOCATION.

TypeHandler routes by Python type. Existing handlers and filters receive only VK Updates.
ApplicationHandlerStop ends the current dispatch successfully, including VK deduplication.

Context.event holds the original object. Context has user_data keyed by from_id/user_id,
peer_data keyed by peer_id, and shared
bot_data. Missing identities receive temporary empty dictionaries. State is process-local,
not persistent, and does not have an eviction policy. Handlers may implement simple
conversation levels in these dictionaries. No ConversationHandler or storage backend is
claimed. Serial dispatch protects these maps only inside awaited handlers/error callbacks,
not background computations. Internal events can explicitly select scopes via user_id/peer_id
queue arguments; otherwise their dictionaries are temporary and empty.

Errors invoke registered error callbacks with Context.error. Awaited process_update calls
receive the error; queued items without receipts do not stop the consumer. Library logs
include exception class names only. Error callbacks must avoid logging raw exceptions,
updates or context if their data may be private. Internal errors supply None as the callback's
first argument and the object in Context.event. Recursive dispatch is rejected.

See [event processing](../development/event-processing.md) for queue overload, managed-task
ownership, cancellation, complete lifecycle ordering and public API stability.

## Delivery, backpressure and retries

Long Poll fetches a batch, validates it and advances ts before serial dispatch. A failed
handler is reported and skipped; its partial side effects are not automatically replayed.
Cancellation/crash during a batch can lose remaining events: the cursor is not durable.
Malformed batches fail before cursor advancement. failed=1 reports lost server history;
failed=2 preserves the cursor while refreshing credentials; failed=3 resets it. Polling
retries transient network/HTTP failures and VK throttling with local capped backoff.
Polling is paused while handlers execute, providing natural backpressure with at most
one received batch in memory. Slow handlers may exhaust VK's retained history.

Callback checks the group and constant-time secret comparison before dispatch. Confirmation
returns the configured string; unknown valid event types may be handled generically.
The optional Starlette adapter owns Application through ASGI lifespan. It limits pending
requests and body size, times out processing, and responds with safe plain text. ASGI
server, routing exposure and TLS remain deployment responsibilities. These resource
defaults are local policy, not VK limits. Use one delivery mode per Application instance.

The duplicate cache remembers a bounded number of successfully dispatched event IDs for
the application's one group. Concurrent duplicates serialize and are acknowledged without
reprocessing. Failed or cancelled events are not cached: Callback retries can repeat a
handler's already completed side effects. Eviction/restarts/multiple processes also permit
duplicates. There is no exactly-once guarantee. Applications needing stronger guarantees
must persist deduplication and business operations transactionally; no database is added.

API mutations are never automatically retried. HTTP errors expose status_code; API errors
expose code and method. RateLimitError represents documented VK code 6. A caller retrying
messages.send should supply the same random_id and account for VK's finite deduplication
window, rather than assuming an unlimited guarantee.

## Model and transport choices

BotSettings derives from pydantic-settings BaseSettings. Instances read VK_* variables;
dotenv loading is explicit through `_env_file`. The library creates no global settings
instance. Users can inherit the class to add their own configuration and override source
options. Token, API-version and timeout constraints/defaults are shared with TransportConfig,
which remains an explicit BaseModel and never reads the environment. Bot and Application
still accept explicit arguments, and the settings layer neither creates clients nor starts
services. Callback-specific secrets are demonstrated in an example subclass, so polling
users do not need to supply them. See [settings usage](../../README.md#settings).

Pydantic v2 validates configuration, API envelopes, used response structures and event
boundaries. Unknown VK fields survive. Update.object retains the original JSON object,
with parsed message/message_event views for handlers. There is intentionally no generated
model collection or repeated validation in each handler. Keyboard accepts typed TextButton
and CallbackButton models alongside raw VK action dictionaries. Typed buttons validate
their fields and serialize flat inputs into VK action envelopes in JSON mode. ButtonColor
and ButtonType expose the supported values as StrEnum members. Raw action dictionaries
and extra capabilities remain extensible. See the [keyboard API](../development/keyboards.md).

HTTPX AsyncClient provides async pooling, explicit timeouts, injectable transports and
MockTransport for network-free regression tests. aiohttp ClientSession also supports these
core needs, but no existing requirement justified a different client API or mandatory
HTTP server dependency. Callback server dependencies are optional.

References: [HTTPX async](https://www.python-httpx.org/async/),
[HTTPX transports](https://www.python-httpx.org/advanced/transports/),
[aiohttp sessions](https://docs.aiohttp.org/en/stable/client_quickstart.html),
[Pydantic models](https://docs.pydantic.dev/latest/concepts/models/).

## Verification and limits

The implementation has regression coverage on Python 3.14. Other Python versions were
assessed before the media additions; their older results do not verify the expanded API.
See [verification results](../development/verification.md).
No support below Python 3.14, durable queue or distributed state is claimed.

## Media operations

Bot orchestrates upload-server discovery, multipart transfer, save and message editing.
HTTPTransport reuses its async client without forwarding API credentials to upload URLs.
Local reads run in a worker and the current uploader buffers file content in memory.
Borrowed files stay open; owned reads close their resources. No mutation retries or
automatic send fallback are added. These operations share Bot's existing lifecycle.

Message.attachments is raw JSON; typed_attachments produces fresh typed envelopes or a
generic fallback retaining unknown/malformed fields. Typed upload results use stricter
validation. Geo continues to require a coordinate pair when present. The map example
serializes rendering and editing per message without changing application dispatch.
See [decision 0002](../decisions/0002-media-attachments.md) and the
[media API](../development/media-api.md) for contracts, limits and pending verification.
