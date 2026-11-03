# 0004: One serial event queue with transport completion receipts

Status: accepted
Date: 2026-11-03
Task: ptb-mechanisms

## Context

Background computations need to return Python objects to the same state-owning dispatcher
that handles VK events. The user selected option 3, a unified queue, after comparing it
with minimal lifecycle additions and a separate internal queue. Regression-test updates
were separately authorized after the main-code changes were presented for review.

[Decision 0001](0001-async-framework.md) establishes serial dispatch, separate transports,
explicit lifecycle and no durable delivery guarantee. This decision extends those choices.
PTB 22.8 was verified on 2026-11-03 against
[PyPI](https://pypi.org/project/python-telegram-bot/),
[Application](https://docs.python-telegram-bot.org/en/v22.8/telegram.ext.application.html),
[TypeHandler](https://docs.python-telegram-bot.org/en/v22.8/telegram.ext.typehandler.html), and
[tagged source](https://github.com/python-telegram-bot/python-telegram-bot/blob/v22.8/src/telegram/ext/_application.py).

## Decision

Use one bounded FIFO and one consumer for VK Updates, internal Python objects and managed
task error callbacks. Application.process_update submits an item and awaits its receipt;
Application.update_queue exposes producer operations without exposing consumer ownership.
Queued event execution uses a separately awaited task so cancelling one request cancels
only its own dispatch. TypeHandler routes arbitrary objects; existing handlers and filters
remain VK-specific. Handler groups retain their first-match semantics.

Keep Callback authentication/confirmation outside the queue, and acknowledge ordinary
events only after successful dispatch. Keep Long Poll's existing cursor/reconnection code
and its wait for each event. Internal objects never enter VK deduplication. A successful
ApplicationHandlerStop does enter deduplication for VK events.

Application.create_task owns finite operations; cancel_on_stop explicitly marks workers
for cancellation. Stop rejects new work while accepted producers and the active handler
may finish publishing. Keep the consumer alive until producers finish, then close admission
and drain the queue. A stopping handler/task never awaits its own completion.

Stop itself does not invoke post_stop. Shutdown orchestrates stop, once-per-run post_stop,
Bot shutdown and post_shutdown; runners and ASGI/context-manager owners use shutdown.
This preserves the library's lifecycle ownership while making post_stop occur before
the HTTP client is closed. Recursion from lifecycle hooks is rejected.

Use native asyncio queue shutdown on the Python 3.14 main branch. No dependencies,
VK wire schema, API version or application-specific business models change.

## Alternatives Considered

### Minimal stop exception and hook

Leaves task/queue lifecycle to every application and does not meet the requested generic
background-result mechanism.

### Separate internal queue and shared lock

Less intrusive, but maintains two admission paths and does not establish FIFO between
accepted VK events and internal results. The user preferred closer PTB architecture.

### Raw asyncio.Queue and early HTTP acknowledgement

Allows bypassing lifecycle checks and competing consumers. Acknowledging in-memory
admission changes delivery semantics and offers no crash durability. Neither is needed.

## Consequences

### Positive

- One ordered dispatcher owns handler/error-callback state mutation.
- Internal objects require no fabricated VK identifiers.
- Callback errors, cancellation and duplicate acknowledgements retain explicit receipts.
- Task/resource lifetime and queue overload are documented and bounded locally.

### Negative

- Serial handlers can delay all event types; workers must return results through the queue.
- Managed-task errors also need the consumer: handlers must not await tasks that depend on it.
- Queue capacity limits pending items, not the number of producer tasks created by users.
- Graceful shutdown requires finite operations or cooperative worker cancellation.
- The producer facade is intentionally a subset of asyncio.Queue; no public get/join.
- There is no persistent queue, distributed deduplication or exactly-once delivery.

## Documentation

- [Event processing and lifecycle](../development/event-processing.md)
- [Project architecture](../architecture/project-architecture.md)
- [PTB mapping](../architecture/python-telegram-bot-compatibility.md)
- [Implementation steps](../architecture/ptb-mechanisms-proposal.md)
