# PTB mechanisms: selected architecture and implementation steps

Date: 2026-11-03. The user selected **option 3: a unified event queue**
and authorized implementation. The main code and the steps below are complete.
After separate user approval, 51 regression cases were added; all 320 unit tests pass
on Python 3.14.4. Results are recorded in the [verification log](../development/verification.md).

## Selection rationale

The review covered requirements for general-purpose background tasks and dispatch,
python-vk-bot sources on main at HEAD `2740cfd`, existing tests and ADR 0001.
The pre-existing staged change to `examples/interactive_map.py` was preserved
and was outside the implementation scope.

Reference: stable PTB **22.8**, verified on 2026-11-03 through
[PyPI](https://pypi.org/project/python-telegram-bot/) and the
[Application documentation](https://docs.python-telegram-bot.org/en/v22.8/telegram.ext.application.html).
Detailed sources and differences appear in the [PTB comparison](python-telegram-bot-compatibility.md).
The VK API version, message schemas, API methods and retry policy are unchanged.

| Option | Assessment |
| --- | --- |
| 1. Exception and post_stop only | Insufficient: applications would need to implement the queue and task lifecycle |
| 2. Separate internal queue and shared lock | Fewer changes, but two admission paths and no shared FIFO |
| 3. Unified queue | Selected by the user for its similarity to PTB architecture and shared processing order |

## Step 1. Record the decision and boundaries

- Create [ADR 0004](../decisions/0004-unified-event-queue.md) using the project template.
- Keep VK delivery separate from Python object dispatch.
- Keep speech models, AI, brokers and application business rules outside the library.
- Preserve dependencies and the root package layout.

## Step 2. Introduce a shared queue and processing acknowledgement

Files: `python_vk_bot/queues.py`, `python_vk_bot/application.py`.

- One bounded FIFO and one consumer. The update_queue_size parameter defaults to 256.
- Public update_queue provides put, put_nowait and capacity inspection.
  Application owns consumption and completion acknowledgement.
- process_update inserts events into the same queue and waits for an individual processing result.
- Each active item runs in an awaited task, allowing cancellation of a specific handler
  while keeping the consumer alive.
- Outside a handler, put waits for capacity; inside a handler, a full queue raises QueueFull.
- The queue does not guarantee persistence across restarts.

## Step 3. Route objects and stop event processing

Files: `python_vk_bot/handlers.py`, `python_vk_bot/errors.py`,
`python_vk_bot/context.py`, `python_vk_bot/__init__.py`, `python_vk_bot/application.py`.

- TypeHandler receives the original Python object and supports isinstance and strict=True.
- Existing Handler/MessageHandler/CommandHandler/filters receive Update objects only.
- ApplicationHandlerStop stops the remaining groups for the current event without an error callback.
- A successfully stopped Update is included in deduplication; internal objects never are.
- Context.event contains the original object. Internal events can receive explicit user_id/peer_id
  scopes at admission; otherwise, temporary empty state dictionaries are used.
- ErrorCallback keeps its Update | None and Context signature. The internal object is available
  through Context.event, and the exception through Context.error.
- In an error handler, the control-flow exception stops the error-handler chain
  while preserving the original event error for the transport.

## Step 4. Preserve Callback and Long Poll contracts

Changes are contained in Application; `callback.py` and `long_poll.py` require no changes.

- Callback continues to validate group/secret and handle confirmation separately.
- The ok response follows successful dispatch, rather than insertion into memory alone.
- An HTTP timeout cancels the waiting item or its active handler and waits for cleanup.
- Long Poll preserves its ts/reconnect algorithm and waits for each event to finish processing.
- During normal stop, an already queued Long Poll event finishes; cancelling the runner
  cancels the corresponding processing. Events arriving after stop are rejected.
- Existing duplicate, handler-error and timeout checks remain applicable.

## Step 5. Manage tasks and shutdown

File: `python_vk_bot/application.py`.

- create_task accepts a coroutine only while RUNNING, returns asyncio.Task and tracks it
  until completion. Errors reach error handlers through the same consumer.
- Ordinary tasks are finite and awaited. Workers use cancel_on_stop=True;
  their finally blocks run before Bot closes.
- stop rejects new events and tasks. Already tracked producers and the handler
  active at stop may finish publishing results.
- The consumer stays alive while producers finish; the queue then closes and drains.
- Calling stop from a handler/task requests stopping without waiting for itself.
- stop does not invoke post_stop. Full shutdown runs stop → post_stop → Bot.shutdown
  → post_shutdown. This applies to runners, ASGI, async with and manual shutdown.
- post_stop runs once per started lifecycle, including repeated shutdown calls.
- A hook failure does not skip the remaining cleanup; cancelling the owner does not
  leave background cleanup operations unawaited.
- After stop, shutdown/initialize is required before another start; CHANGELOG explicitly
  records this contract change. Recursive lifecycle calls from hooks are forbidden.

stop must not wait for an infinite task whose termination is scheduled only in post_stop.
Handlers must not await a task that needs the same consumer to deliver a result or report
an error. These constraints are documented.

## Step 6. Add an example and public documentation

- `examples/background_result.py`: a command starts a local computation stub;
  BackgroundResult enters the shared queue, and TypeHandler sends a message.
- `examples/README.md`, `README.md`: API, setup and worker usage.
- `docs/development/event-processing.md`: capacity, cancellation, errors, state scopes,
  lifecycle, API stability and constraints.
- `docs/architecture/project-architecture.md`: the implemented architecture diagram.
- `docs/architecture/python-telegram-bot-compatibility.md`: PTB reference and differences.
- `CHANGELOG.md`, `pyproject.toml`, `uv.lock`: consistent version 0.4.0,
  with CHANGELOG dated 2026-11-03; the package has not been published.
- `.agent-work/completed/ptb-mechanisms.md`: final task state and results.

## Step 7. Verify main code and obtain approval — complete

Run existing Application/Callback/Long Poll tests first. Then run uv sync with the Callback
extra, Ruff check/format, ty and the full pytest --strict-markers suite on Python 3.14.
Record results in `docs/development/verification.md` and the task file.
Keep existing tests unchanged at this stage; passing them does not replace new regression coverage.

## Step 8. Add regression tests after approval — complete

Updated and added files:

- `tests/unit/test_application.py`: stopping between groups, deduplication, hook order,
  repeated shutdown, cleanup errors, cancellation and stopping from a handler/task.
- `tests/unit/test_background_events.py`: FIFO across types, TypeHandler, state scopes,
  task errors, worker cancellation, capacity limits, waiting producers, drain and restart.
- `tests/unit/test_callback.py`: cancellation in the queue/handler, duplicates and existing acknowledgement behavior.
- `tests/unit/test_background_result.py`: the example with MockTransport and no external network.

All checks are complete; the final task record has moved to completed.
No commit, publication, external application changes or branch transfer has been requested.
