# Examples

Run these examples from the repository root on Python 3.14. Each script is a separate
application; start one at a time for the same community.

## Setup

Install the checkout and configure `VK_TOKEN` (a community token) and `VK_GROUP_ID`
(a positive community ID) in the environment:

```bash
uv sync --locked
```

`BotSettings` reads the environment at startup; it does not load `.env` automatically.
See [settings](../README.md#settings) for optional configuration and explicit dotenv use.

For the Long Poll examples, enable Bots Long Poll in the community settings and select
the events listed below. Use API version 5.199, matching the library's default.
The Callback example uses its own HTTP delivery setup instead.

| Example | Demonstrates | Events |
| --- | --- | --- |
| [echo.py](echo.py) | Text messages, filters and Long Poll lifecycle | `message_new` |
| [keyboards.py](keyboards.py) | Ordinary and inline keyboards, payloads and message editing | `message_new`, `message_event` |
| [interactive_map.py](interactive_map.py) | Photo upload and replacement with inline navigation | `message_new`, `message_event` |
| [callback.py](callback.py) | A Callback API receiver using an ASGI factory | `message_new` |

## Echo bot

```bash
uv run python examples/echo.py
```

Send a text message to the community. The bot replies with the same text. This is the
smallest example of `Application`, `BotSettings`, `MessageHandler` and `filters.TEXT`.

## Ordinary and inline keyboards

The example constructs Pydantic `TextButton` and `CallbackButton` objects and uses
`ButtonColor` enum members. Dictionary payloads are JSON encoded by the library.
See the [keyboard API](../docs/development/keyboards.md) for model payloads and serialization.

```bash
uv run python examples/keyboards.py
```

- `/keyboard` opens a persistent ordinary keyboard with **Помощь**, **О боте** and
  **Скрыть клавиатуру**. Text buttons are handled through `MessageHandler`; actions are
  selected by their JSON `payload`, independently of the displayed label. Hiding sends
  an empty ordinary keyboard. Send `/keyboard` to show it again.
- `/inline` sends a message with **Подтвердить** and **Отмена** callback buttons.
  `MessageEventHandler` acknowledges the click with a snackbar, then edits that message
  using `conversation_message_id`. Both buttons remain available for repeated use.

The example validates the payload namespace, structure and supported actions. Ordinary
message payloads are JSON strings; event payloads can also be objects. In a conversation,
any participant can change the inline selection: this demonstrates UI interaction,
without performing a privileged action or storing a confirmation workflow.

VK edit errors propagate through the application's error handling; there is no fallback
send. Running the example against a community is a live operation, not a unit test.

## Interactive map

```bash
uv run python examples/interactive_map.py
```

Send `/map`. The bot renders a synthetic PNG grid using the standard library, uploads
it and adds navigation and zoom buttons. Each click renders and uploads a replacement
photo, then edits the same message with an explicit caption and keyboard.

One active map per peer is stored in memory. Only its creator can navigate it, and a
lock serializes render/upload/edit operations. Restarting the process loses the state;
send `/map` again. The grid is a demonstration image, not geographical map data.

Actual photo replacement has not yet been verified against live VK. See the
[media guide](../docs/development/media-api.md) for limitations and the opt-in integration
test. Upload and edit are separate operations; a failed edit can leave an unused photo.

## Callback API receiver

Set `VK_CALLBACK_SECRET` and `VK_CALLBACK_CONFIRMATION` in addition to `VK_TOKEN` and
`VK_GROUP_ID`, then run:

```bash
uv run --extra callback uvicorn examples.callback:create_app --factory
```

Expose the application's `/callback` endpoint through your HTTPS deployment. Configure
that address, the same secret and the `message_new` event in the community's Callback
API settings. The confirmation value must match the code provided by VK.

The receiver echoes text messages. `CallbackSettings` extends `BotSettings` with the
required secret and confirmation fields, and the ASGI lifespan manages the application's
resources. See [Callback API](../README.md#callback-api) for delivery semantics.
