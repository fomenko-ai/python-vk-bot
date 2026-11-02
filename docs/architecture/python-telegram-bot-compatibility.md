# python-telegram-bot design reference

## Framework reference

Verified on 2026-10-31 against stable documentation for **22.8** and its tagged source:

- [Application](https://docs.python-telegram-bot.org/en/stable/telegram.ext.application.html)
- [Tagged implementation](https://github.com/python-telegram-bot/python-telegram-bot/blob/v22.8/src/telegram/ext/_application.py)
- [Bot](https://docs.python-telegram-bot.org/en/stable/telegram.bot.html)
- [Handlers and filters](https://docs.python-telegram-bot.org/en/stable/telegram.ext.html)
- [ApplicationBuilder configuration](https://docs.python-telegram-bot.org/en/stable/telegram.ext.applicationbuilder.html)

PTB separates API methods in Bot from update retrieval in Updater and dispatch/lifecycle
in Application. Application initializes resources, starts processing, stops, then shuts
down. Its convenience runners also invoke lifecycle hooks. Handler groups are ordered;
the first matching handler in each group runs. Context exposes user/chat/bot state;
error callbacks receive processing exceptions. Conversation management is an additional
handler abstraction, not a requirement for ordinary dispatch. Async execution does not
itself make shared mutable state safe under concurrency.

## Implemented design

| PTB | python-vk-bot | Compatibility | Difference |
| --- | --- | --- | --- |
| Application | Application | Responsibility | Awaitable runner; no event-loop ownership |
| Bot | Bot | Responsibility | Community token, VK methods and peer IDs |
| Update | Update with typed message/event objects | Conceptual | VK event_id, group_id, v; unknown events retained |
| Updater | LongPoll | Partial | VK key/server/ts and failed recovery |
| MessageHandler | MessageHandler | Conceptual | VK message_new; geo remains part of message |
| CallbackQueryHandler | MessageEventHandler | Different name | VK message_event is not a Telegram callback query |
| CallbackContext | Context | Partial | user_data, peer_data, bot_data; no Telegram chat aliases |
| filters | filters | Small subset | Text, location, regex and boolean composition |
| Error handlers | Application.add_error_handler | Partial | Error callback receives Context.error; failure still propagates |
| ConversationHandler | None | Deferred | Application state can implement simple levels |
| ApplicationBuilder | None | Deferred | Direct construction is sufficient |
| Explicit Bot / ApplicationBuilder configuration | BotSettings plus explicit constructors | Deliberate extension | Optional use of environment-backed settings, not a builder |

Callback API is HTTP event delivery, distinct from an interactive message_event. Long
Poll and Callback feed the same validated update/dispatch pipeline but have different
acknowledgement and resource semantics. No Telegram transport, permission, keyboard,
or message identifier assumptions are copied. No PTB implementation code is copied.

### Settings

Settings addition reviewed on 2026-10-31 against the same PTB 22.8 reference.
PTB's builder accepts token and request settings explicitly. BotSettings is our reusable
configuration-loading convenience, not a claimed PTB-equivalent class. It can be inherited
by user projects; creating clients and managing lifecycle remain separate responsibilities.
Loading follows [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/).

## Media API

Rechecked on **2026-11-01** against stable **PTB 22.8**:

- [Bot media methods](https://docs.python-telegram-bot.org/en/v22.8/telegram.bot.html#telegram.Bot.edit_message_media)
- [InputMediaPhoto](https://docs.python-telegram-bot.org/en/v22.8/telegram.inputmediaphoto.html)
- [InputFile](https://docs.python-telegram-bot.org/en/v22.8/telegram.inputfile.html)
- [Delete message](https://docs.python-telegram-bot.org/en/v22.8/telegram.bot.html#telegram.Bot.delete_message)
- [Tagged Bot source](https://github.com/python-telegram-bot/python-telegram-bot/blob/v22.8/src/telegram/_bot.py)

PTB's file inputs and media-edit convenience inform the public API. VK keeps upload,
save and messaging separate: `upload_photo` / `upload_document` return VK attachments;
`edit_message_media` currently replaces photos and returns VK's boolean status, not a
Telegram Message. It accepts a saved photo or local file; no InputMedia hierarchy is
needed. Peer IDs, message IDs/cmid, caption-as-message and VK keyboards retain their
native meanings. Removal for recipients requires explicit `delete_for_all=True`.

Raw `Message.attachments` and additive typed views coexist. No Telegram file IDs,
album constraints, deletion windows or live-location behavior are inferred. See the
[media contracts and verification limits](../development/media-api.md).

Upload client defaults rechecked on **2026-11-01** against stable **PTB 22.8** and
its [HTTPXRequest reference](https://docs.python-telegram-bot.org/en/v22.8/telegram.request.httpxrequest.html).
PTB exposes HTTPX configuration through its request implementation. This library
borrows an AsyncClient with explicit ownership checks; VK's separate upload URLs
must retain their server-issued query parameters. Multipart uploads therefore reject
default client query parameters and Content-Type instead of rewriting a borrowed
client's settings. Typed attachment views deep-copy raw JSON, including unknown
nested fields; they remain independent snapshots rather than mutable message state.

## Keyboard API reference

Rechecked on **2026-11-02** against stable **PTB 22.8**:

- [Inline keyboard example](https://docs.python-telegram-bot.org/en/v22.8/examples.inlinekeyboard.html)
- [Ordinary keyboard example](https://docs.python-telegram-bot.org/en/v22.8/examples.conversationbot.html)
- [InlineKeyboardMarkup](https://docs.python-telegram-bot.org/en/v22.8/telegram.inlinekeyboardmarkup.html)

PTB's button objects arranged in rows inform TextButton and CallbackButton. VK's
Keyboard retains inline/one_time settings, action types, colors and JSON payload
semantics. ButtonColor and ButtonType are string-valued enums, using StrEnum on
Python 3.11+ and str/Enum with value-based str() on Python 3.9/3.10. Flat Pydantic constructors
serialize to VK action envelopes in JSON mode. Raw VK dictionaries remain accepted.
Callback buttons emit message_event rather than Telegram callback queries. No Telegram
callback-data cache, string keyboard shorthand or layout builder is implemented.
See the [keyboard contract](../development/keyboards.md) and
[decision](../decisions/0003-typed-keyboard-buttons.md).

## Python compatibility branch

Rechecked stable [Application documentation](https://docs.python-telegram-bot.org/en/stable/telegram.ext.application.html)
on 2026-11-01: reference version **22.8**. PTB still separates initialization, start,
stop and shutdown; its convenience runner manages the event loop. This branch keeps
our awaitable runner and caller-owned event loop, with portable cleanup of owned polling.
Its Python 3.9 target is an independent project decision, not a claim about PTB's
interpreter support. Handler registration and Context state scopes retain their existing
mapping; Context is a regular dataclass. See [Python compatibility](../development/python-compatibility.md)
for implementation choices and verification limits.
