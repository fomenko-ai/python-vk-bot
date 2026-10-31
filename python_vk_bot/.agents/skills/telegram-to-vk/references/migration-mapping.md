# Telegram to VK migration mapping

Baseline inspected on **2026-10-31**: python-vk-bot **0.1.0** source tree and
[PTB 22.8](https://docs.python-telegram-bot.org/en/v22.8/telegram.ext.html).
Inspect the user's actual installed versions before applying this mapping. This file travels
with the Python package and does not require repository documentation to be installed.

## Components

| PTB component | Current python-vk-bot interface | Adaptation |
| --- | --- | --- |
| Application / ApplicationBuilder | `Application(bot, group_id)` | Direct construction; no builder. `run_polling()` must be awaited. |
| Bot | `Bot(token, api_version=..., timeout=...)` | Community token; async context manager; methods use VK identifiers. |
| Configuration | `BotSettings()` | Reads VK_TOKEN and VK_GROUP_ID; optional explicit dotenv loading. Pass values to constructors. |
| Update | `Update.message`, `Update.message_event`, `Update.object` | VK events; unknown objects retained. No effective_message/chat aliases. |
| CallbackContext | `Context` | user_data, peer_data, bot_data; process-local state, no chat_data or args. |
| CommandHandler | `CommandHandler("start", callback)` | Exact /start token; no Telegram mention parsing. Parse arguments explicitly. |
| MessageHandler | `MessageHandler(callback, predicate=...)` | Callback comes first; only message-bearing updates. |
| filters | `filters.ALL`, `TEXT`, `LOCATION`, `Regex`, `Filter` | Small synchronous subset; supports &, \| and ~. No COMMAND filter. |
| CallbackQueryHandler | `MessageEventHandler(callback, predicate=...)` | Handles VK message_event; payload shape and answer identifiers differ. |
| ConversationHandler | No built-in equivalent | Explicit state transitions in the bot project; design persistence if required. |
| JobQueue | No built-in scheduler | Reuse an existing scheduler or propose one; manage task lifetime explicitly. |
| Persistence | No built-in backend | In-memory context does not survive restart; adapt the application's storage. |
| Error callbacks | `Application.add_error_handler(callback)` | Async `(update, context)`; update may be None, exception is context.error; errors propagate. |
| Updater / webhook delivery | `LongPoll` / `Callback` | Different VK delivery/acknowledgement semantics; choose one mode per Application. |
| Inline/reply keyboard | `Keyboard(buttons=..., inline=...)` | VK action dictionaries, not Telegram button objects. |
| send_message / reply_text | `Bot.send_message(peer_id, text, ...)` | Returns an integer ID; Message has no reply_text method. |
| Edit / forward | `Bot.edit_message` / `Bot.forward_message` | Explicit peer and correct identifier scope; forwarding uses the source peer. |
| Media / deletion | Attachment references supported; no upload/delete wrappers | Do not promise uploads or delete_message; raw Bot.request needs separately verified VK methods. |

For implementation details inspect the installed package's `__init__.py`, `application.py`,
`handlers.py`, `context.py`, `filters.py`, `bot.py`, `models/` and `callback.py`.

## Working command and message example

Run with Python 3.14 and VK_TOKEN/VK_GROUP_ID configured. Enable community messaging, Bots
Long Poll and message_new first. This example replies only to received messages.

```python
import asyncio

from python_vk_bot import (
    Application,
    Bot,
    BotSettings,
    CommandHandler,
    Context,
    MessageHandler,
    Update,
    filters,
)


def make_reply(text: str) -> str:
    # Keep platform-independent business logic outside handlers.
    return f"You said: {text}"


async def start(update: Update, context: Context) -> None:
    if update.message is not None:
        await context.bot.send_message(update.message.peer_id, "Send some text.")


async def echo(update: Update, context: Context) -> None:
    if update.message is not None:
        reply = make_reply(update.message.text)
        await context.bot.send_message(update.message.peer_id, reply)


async def main() -> None:
    settings = BotSettings()
    bot = Bot(settings.token, api_version=settings.api_version, timeout=settings.timeout)
    app = Application(bot, settings.group_id)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(echo, predicate=filters.TEXT))
    await app.run_polling(wait=settings.polling_wait)


if __name__ == "__main__":
    asyncio.run(main())
```

Handlers run serially, taking the first match in each numeric group. Registration order
above prevents /start from also reaching echo in the same group. Other slash commands
still reach echo: add explicit command policy if the source bot excluded all commands.
In an existing event loop, await `main()` instead of calling `asyncio.run()`.

## Button-event answer

This registration helper operates on an existing Application. Enable message_event for
the chosen delivery mode and supply valid VK callback buttons separately.

```python
from python_vk_bot import Application, Context, MessageEventHandler, Update


async def answer_button(update: Update, context: Context) -> None:
    event = update.message_event
    if event is not None:
        await context.bot.send_message_event_answer(event.event_id, event.user_id, event.peer_id)


def register_button_handler(app: Application) -> None:
    app.add_handler(MessageEventHandler(answer_button))
```

Use the object's `event.event_id` for the answer, not the envelope `update.event_id`.
The library preserves `event.payload` as JSON, including strings; validate the application's
expected shape before routing actions. Do not assume Telegram callback_data semantics.

## Platform and lifecycle pitfalls

- A message's `peer_id` identifies the destination conversation; `from_id` identifies its
  author. Keep VK identities separate from Telegram IDs and explicitly map existing users.
- `id` and `conversation_message_id` have different scopes. `edit_message` takes exactly one
  of `message_id` or `conversation_message_id`; the latter is serialized as VK's `cmid`.
- Keyboard action dictionaries and media attachment references are VK data. Telegram file
  IDs, entities and parse modes cannot be copied as working VK structures.
- Community tokens require appropriate permissions and conversation access. Do not assume
  the bot can initiate arbitrary conversations or that Telegram recipients opted into VK.
- Long Poll consumes batches and can lose remaining events on cancellation/crash. Callback
  acknowledges successful processing and can redeliver after failures. Bounded in-memory
  deduplication does not prevent repeated partial side effects or survive restarts.
- API mutations are not automatically retried. For a deliberate send retry, preserve the
  operation's nonzero int32 random_id and account for VK's documented deduplication limits.
  Polling backoff settings are not platform rate limits.
- Application owns Bot's lifecycle; an injected HTTPX client remains caller-owned. Await
  cancellation/cleanup and ensure application-owned scheduler tasks end before resources close.
- Context state is process-local. Choose per-user, per-peer or compound keys deliberately;
  durable conversations and multi-worker consistency require application-level design.
- Callback HTTP delivery is distinct from message_event button handling. The optional ASGI
  receiver requires the callback extra, secret, confirmation code and HTTPS deployment.
- Do not log tokens, context dictionaries, raw exceptions or complete updates. Use harmless
  placeholders and mocked HTTP/event delivery in verification.

## Shared logic and migration report

Keep business services independent of platform Update/Context objects. Adapt input and output
at existing handler boundaries, preserve integrations, and introduce shared adapters only if
both applications need them. Record explicit decisions for unsupported workflows, scheduling,
uploads, persistence and Telegram-only features instead of silently dropping them.

For each migrated component report its source version/interface, VK replacement, differences,
manual setup, checks and remaining work. Verify shutdown and error paths as well as happy paths.

## Official references

- [PTB Application](https://docs.python-telegram-bot.org/en/v22.8/telegram.ext.application.html)
- [PTB CallbackContext](https://docs.python-telegram-bot.org/en/v22.8/telegram.ext.callbackcontext.html)
- [VK API versions](https://dev.vk.com/ru/reference/versions)
- [VK messages.send](https://dev.vk.com/ru/method/messages.send)
- [VK messages.edit](https://dev.vk.com/ru/method/messages.edit)
- [VK message-event answers](https://dev.vk.com/ru/method/messages.sendMessageEventAnswer)
- [Bots Long Poll](https://dev.vk.com/ru/api/bots-long-poll/getting-started)
- [Callback API](https://dev.vk.com/ru/api/callback/getting-started)

Recheck applicable official VK documentation before version-dependent migration work.
This mapping describes library interfaces, not a guarantee of live-token permissions or
complete VK API coverage.
