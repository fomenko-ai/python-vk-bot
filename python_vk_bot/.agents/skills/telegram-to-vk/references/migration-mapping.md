# Telegram to VK migration mapping

Baseline inspected on **2026-11-26**: python-vk-bot **0.9.0** main source tree and
[PTB 22.8](https://docs.python-telegram-bot.org/en/v22.8/telegram.ext.html).
Inspect the user's actual installed versions before applying this mapping. This file travels
with the Python package and does not require repository documentation to be installed.

## Components

| PTB component | Current python-vk-bot interface | Adaptation |
| --- | --- | --- |
| Application / ApplicationBuilder | `Application(bot, group_id)` | Direct construction; no builder. `run_polling()` must be awaited. |
| Bot | `Bot(token, api_version=..., timeout=...)` | Community token; async context manager; methods use VK identifiers. |
| Configuration | `BotSettings()` | Reads VK_TOKEN and VK_GROUP_ID; optional explicit dotenv loading. Pass values to constructors. |
| Update | `Update.message`, `Update.message_event`, `Update.donut_subscription`, `Update.object` | VK events; unknown objects retained. No effective_message/chat aliases. |
| CallbackContext | `Context` | user_data, peer_data, bot_data and event; process-local state, no chat_data or args. |
| CommandHandler | `CommandHandler("start", callback)` | Exact /start token; no Telegram mention parsing. Parse arguments explicitly. |
| MessageHandler | `MessageHandler(callback, predicate=...)` | Callback comes first; only message-bearing updates. |
| filters | `filters.ALL`, `TEXT`, `LOCATION`, `Regex`, `Filter`, `DONUT_SUBSCRIPTION*` | Small synchronous subset; supports &, \| and ~. No COMMAND filter. |
| CallbackQueryHandler | `MessageEventHandler(callback, predicate=...)` | Handles VK message_event; payload shape and answer identifiers differ. |
| TypeHandler | `TypeHandler(event_type, callback, strict=False)` | Routes Python objects, including Update; subclass matching unless strict=True. |
| Custom events / background results | `Application.update_queue`, `process_update`, `create_task` | One serial queue; worker results need no fabricated VK Update. |
| ApplicationHandlerStop | `ApplicationHandlerStop` | Stops remaining handler groups for the current event. |
| ConversationHandler | No built-in equivalent | Explicit state transitions in the bot project; design persistence if required. |
| JobQueue | No built-in scheduler | Reuse an existing scheduler or propose one; manage task lifetime explicitly. |
| Persistence | No built-in backend | In-memory context does not survive restart; adapt the application's storage. |
| Error callbacks | `Application.add_error_handler(callback)` | Async `(event, context)`; event may be a VK Update, internal object or None; exception is context.error; errors propagate. |
| Updater / webhook delivery | `LongPoll` / `Callback` | Different VK delivery/acknowledgement semantics; choose one mode per Application. |
| Inline/reply keyboard | `Keyboard(buttons=..., inline=...)` | Typed TextButton, CallbackButton, OpenLinkButton and LocationButton, or raw VK action dictionaries. |
| send_message / reply_text | `Bot.send_message(peer_id, text, ...)` | Returns an integer ID; Message has no reply_text method. |
| Send result identifiers | `Bot.send_message_and_get_ids` / `Bot.forward_message_and_get_ids` | Return MessageSendResult with destination peer_id, optional global message_id and conversation_message_id; not a complete Message. |
| Edit / forward | `Bot.edit_message` / `Bot.forward_message` | Explicit peer and correct identifier scope; forwarding uses the source peer. |
| Media uploads | `Bot.upload_photo` / `Bot.upload_document` | Upload/save without sending; document type is doc or audio_message. No generic Telegram file-ID conversion. |
| Replace media / delete | `Bot.edit_message_media` / `Bot.delete_message` | Photo replacement or deletion by explicit peer and exactly one identifier; no fallback send. |
| Button notification | `ShowSnackbar(text=...)` | Pass as event_data to send_message_event_answer; raw mappings also accepted. |
| Donation subscription events | `DonutSubscriptionHandler(callback, event_types=...)` | VK-specific; validate the actual constructor and configured event types. |

For implementation details inspect the installed package's `__init__.py`, `application.py`,
`handlers.py`, `context.py`, `filters.py`, `bot.py`, `models/`, `queues.py`,
`transport.py` and `callback.py`.

## Message identifiers, media and buttons

Use send_message_and_get_ids when later edits require a conversation-scoped ID.
MessageSendResult.message_id may be None; do not substitute the conversation ID as a
global ID. forward_message_and_get_ids takes from_peer_id and conversation_message_id
for the source and returns identifiers of the new destination message. Ordinary
send_message and forward_message retain their integer result. get_message takes a
peer and conversation_message_id, returns Message or None for confirmed absence,
and raises InvalidResponseError for malformed or mismatched responses.

upload_photo and upload_document accept bytes, pathlib.Path or a binary file. A string
path is not a local-file input. Uploads buffer files in memory; borrowed files remain
open and are read from their current position. Upload/save/send/edit are separate
operations, with no transactional cleanup or automatic fallback. Saved attachments
can be sent later. Message.attachments retains raw dictionaries; typed_attachments
provides parsed views while preserving unknown attachment kinds.

edit_message_media accepts a local photo input, PhotoAttachment or VK photo identifier;
saved photos skip upload. Set caption and keyboard explicitly when their desired
values matter; omitted fields do not imply a fetch/merge preservation guarantee.
delete_message returns bool and defaults delete_for_all to False. Permissions and
server-side restrictions still apply.

Keyboard supports mixed typed buttons and raw VK dictionaries. ButtonColor and
ButtonType are VK enums. Validation includes keyboard dimensions, action row rules,
and known label lengths; inspect the installed limits module and models instead of
copying Telegram limits. ShowSnackbar is an outgoing action, not a callback query.

## Internal events and managed tasks

Application.update_queue is a producer facade, not a general asyncio.Queue: put and
put_nowait enqueue without waiting for dispatch; there is no public get/join.
process_update enqueues and awaits dispatch and must not be called recursively from
a handler. For internal objects, user_id and peer_id explicitly select state scopes;
Context.event retains the dispatched object. TypeHandler receives that object directly.
The bounded queue raises QueueFull rather than blocking an active handler on capacity.

Use Application.create_task only while running. Send results through the event queue
instead of mutating Context state in workers. Finite tasks are awaited during stop;
mark long-lived workers cancel_on_stop=True. Do not await a managed task from a handler
if that task depends on dispatcher progress, including its queued error callback.
This is task ownership, not a scheduler or a persistence layer.

Lifecycle hooks are post_init, post_stop and post_shutdown. shutdown orchestrates stop,
post_stop while Bot is available, HTTP cleanup and post_shutdown. Direct stop does not
invoke post_stop. Let the runner/context owner perform shutdown when a handler calls
stop. Await cancellation and cleanup before releasing borrowed resources.

## HTTP client boundary

On main, Bot(..., client=...) requires httpx2.AsyncClient. Its MockTransport,
ASGITransport, exceptions and URL objects must also come from httpx2. HTTPX classes
are distinct; do not pass a PTB HTTPX client into this Bot or install process-wide
import aliases from a library. HTTP client identity does not determine architectural
compatibility with PTB.

The caller closes injected clients; owned clients are reused and closed on shutdown.
Request timeouts and disabled redirects are applied by HTTPTransport per request.
Configure custom CA contexts, proxies, connection limits or optional HTTP/2 on an
injected client without disabling TLS verification. HTTPX2 uses the system trust store
by default; environment CA/proxy handling is controlled by trust_env. Logger names
are httpx2 and httpcore2.*. Standard HTTPX2 request logs have query redaction, but custom
hooks, transports and telemetry must not expose credentials or message payloads.

The compat/py39 branch retains HTTPX for all its supported Python versions. Determine
the installed branch/version before choosing client imports; do not infer the HTTP
library from the interpreter alone. The example below targets main on Python >=3.14.

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
- Application owns Bot's lifecycle; an injected HTTPX2 client on main remains caller-owned. Await
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
