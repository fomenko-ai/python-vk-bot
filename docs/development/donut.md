# VK Donut subscription events

`DonutSubscriptionHandler` receives five subscription events through the existing
Callback API receiver, validated `Update` and serial Application dispatcher. It reports
facts received from VK; it does not synchronize all subscribers or decide paid access.

## Setup and runnable example

Enable VK Donut in your community's management settings, following VK's available
onboarding requirements. In the community's Callback API settings, configure a server
using API version **5.199**, its public HTTPS `/callback` URL and a secret. Copy the
confirmation code supplied by VK into your deployment configuration. Enable these events:

- `donut_subscription_create`
- `donut_subscription_prolonged`
- `donut_subscription_cancelled`
- `donut_subscription_expired`
- `donut_subscription_price_changed`

For the [complete example](../../examples/donut_subscriptions.py), also enable
community messaging and the `message_new` event. Set `VK_TOKEN` to a community token
with the permissions required for messaging, `VK_GROUP_ID` to the positive community ID,
and `VK_CALLBACK_SECRET` / `VK_CALLBACK_CONFIRMATION` to the configured values.
The example reads environment variables; it does not automatically load `.env`.

From the repository root on Python 3.14:

```bash
uv sync --locked --extra callback
uv run --extra callback uvicorn examples.donut_subscriptions:create_app --factory
```

Expose the ASGI receiver through your HTTPS deployment and complete VK's server
confirmation. ASGI lifespan owns Application startup and shutdown. No server starts
when the library or example is imported. See [Callback setup](../../README.md#callback-api).

The example remembers the latest received event name in `context.user_data`. Send
`/donut` in a private conversation with the community to inspect it. The example makes
no outgoing request in response to a subscription event and does not infer a conversation
ID from its user ID. Stored facts disappear when the process restarts. The reply is
explicitly a received notification, not a current subscription or access check.

## Handler API

```python
from python_vk_bot import Context, DonutSubscriptionHandler, Update


async def on_donut(update: Update, context: Context) -> None:
    event = update.donut_subscription
    if event is None:
        return
    # event.user_id identifies the subscriber; update.group_id identifies the community.
    context.user_data["last_donut_event"] = update.type


application.add_handler(DonutSubscriptionHandler(on_donut))
```

The snippet assumes an existing Application. The complete factory above creates one.
The callback is awaited using ordinary Handler execution. Registration order, numeric
groups, `ApplicationHandlerStop` and error callbacks retain their standard behavior:
only the first matching handler in each group runs.

Select a subset with enum members or exact event strings:

```python
from python_vk_bot.models import DonutSubscriptionEventType

application.add_handler(
    DonutSubscriptionHandler(
        on_donut,
        event_types={
            DonutSubscriptionEventType.CREATE,
            DonutSubscriptionEventType.PROLONGED,
        },
    )
)
```

`event_types=None` selects all five events; an empty iterable selects none. The iterable
is copied at construction. Unknown names raise `ValueError`; a bare string instead of
an iterable of names raises `TypeError`. `predicate=filters.ALL` can be replaced with an
additional synchronous filter. No callback runs for ordinary messages, unknown events,
or internal Python objects through this handler.

`filters.DONUT_SUBSCRIPTION` and the five constants with suffixes `_CREATE`, `_PROLONGED`,
`_CANCELLED`, `_EXPIRED` and `_PRICE_CHANGED` use the existing Filter contract. They support
`&`, `|` and `~`, for example:

```python
from python_vk_bot import Handler, filters

application.add_handler(
    Handler(
        on_donut,
        predicate=filters.DONUT_SUBSCRIPTION_CREATE | filters.DONUT_SUBSCRIPTION_PROLONGED,
    )
)
```

These are alternative registrations; registering them in one group does not call both.

## Typed objects and validation

`DonutSubscriptionEvent` and `DonutSubscriptionEventType` are exported from both
`python_vk_bot.models` and the package root. The model is a shared view of the five
event objects, independent of API responses or application subscription state.

| Event suffix | Fields described by VK |
| --- | --- |
| `create`, `prolonged` | `user_id: int`, `amount: int`, `amount_without_fee: float` |
| `cancelled`, `expired` | `user_id: int` |
| `price_changed` | `user_id: int`, `amount_old: int`, `amount_new: int`, `amount_diff: float`, `amount_diff_without_fee: float` |

Amounts are in rubles. The library requires a positive integer `user_id` and rejects
booleans, strings and floating-point IDs. All monetary fields default to `None` and
accept explicit null; zero stays zero. Integer monetary fields reject non-integer values;
float fields accept finite JSON numbers, including integers, but not strings or booleans.
This optionality is the library's shared-view policy: VK's prose documents field types
without a machine-readable per-event required-field contract. It does not establish
that monetary fields can be absent in real deliveries. See [source verification](api-compatibility.md#donut-contracts).

Pydantic retains extra fields in the envelope and typed event. Raw `Update.object`
remains available. The typed view is parsed once at construction and reused by
`update.donut_subscription`; it is not recomputed when raw fields are edited. Treat
received updates as input snapshots. Ordinary messages and unknown event types have
`donut_subscription is None`.

An illustrative input, with synthetic IDs and amounts:

```python
from python_vk_bot import Update

update = Update.from_dict(
    {
        "type": "donut_subscription_create",
        "group_id": 123456,
        "event_id": "example-event-001",
        "v": "5.199",
        "object": {"user_id": 987654, "amount": 300, "amount_without_fee": 285.0},
    }
)
```

The existing envelope requires `type`, `group_id`, `event_id`, `v` and `object`.
Invalid known event objects raise `InvalidUpdateError` through `from_dict`, with no
payload in the error text. Callback checks group/secret before parsing and dispatch;
the secret is excluded from the Update. Numeric envelope event IDs retain existing
string normalization. The event ID remains available for application idempotency.

`update.user_id` equals the event's user ID, so `context.user_data` is shared with other
updates from that user in this Application. `update.peer_id` is `None`; `peer_data` is
a temporary empty dictionary. `group_id` is a positive community identifier, distinct
from the negative community `owner_id` used by applicable VK API methods.

## Delivery and access boundaries

- Callback acknowledgement waits for successful dispatch. Failures remain retryable;
  partial side effects can run again. Standard cancellation and shutdown apply.
- Existing duplicate suppression is bounded and process-local, for successful event
  IDs within the Application's community. Eviction, restart, separate processes and
  failed handlers allow repeats. There is no durable or exactly-once guarantee.
- Subscriptions created before setup, missed notifications and delayed delivery can
  leave application data incomplete or out of date. Arrival order is not proof of
  business chronology. No notification history or subscriber census is fetched.
- Cancellation of renewal must not automatically revoke the remaining paid period.
  Expiration is a distinct event. A price change must not create an inferred payment.
- No payment date, access deadline or subscription level is inferred. Unknown local
  state is neither proof of expiration nor permission to access protected content.

An application that needs paid access must define its evidence policy, persistent
storage, recovery and atomic idempotency rules. `context.user_data` is not persistent
subscription storage. This stage provides no DonutService, store, TTL cache, `/premium`
authorization or protected-file delivery. Those require a separate application policy.

The official schemas restrict `donut.isDon`, `donut.getSubscription` and
`donut.getSubscriptions` to user tokens and do not provide an arbitrary `user_id`
parameter. A community token cannot be used as a documented universal membership
lookup. No wrappers for those methods are added. VK errors, including error 15, are
not evidence that a user lacks a subscription. See [API limitations](api-compatibility.md#donut-contracts).

This feature targets Callback delivery. Sharing Update parsing with Long Poll does
not assert that VK delivers these events through Bots Long Poll.

## Stability and verification

The documented imports, event names, handler selection and typed-view semantics form
the public contract for this feature. Private attributes and parsing implementation
are internal. The library remains alpha; breaking public changes must be documented
in the changelog. There is no Telegram interface compatibility guarantee.

Network-free regression tests on Python 3.14 cover all five event types, raw and extra
fields, identity and money validation, handler selection and filter composition, shared
user context and handler groups, Callback authentication, retry after failure, duplicate
suppression and HTTP validation. See [the test suite](../../tests/unit/test_donut.py).
Live VK delivery and community eligibility have not been tested; no credentials or live
API calls were used.
