# Event processing and background tasks

The public entry points are Application, its update_queue and create_task methods,
TypeHandler, ApplicationHandlerStop and Context.event. Their queue, cancellation and
lifecycle contracts are transferred from main commit `9874493` and verified on
Python 3.9–3.14; see
[verification](verification.md) for the completed checks and their limits.

## One queue, one dispatcher

Application owns a bounded FIFO and one consumer. The configurable update_queue_size
defaults to 256 pending items; this is local resource policy, not a VK limit. One additional
event can be executing. Managed task error notifications also use this FIFO. Ordering
is by successful insertion, not by network arrival or a timestamp. Waiting producers do
not have a separate ordering guarantee.

`await application.process_update(event)` inserts an event and waits for its dispatch.
It returns True after success or False for an already processed VK event. Handler errors
are reported and propagate to the caller. Cancelling this call skips its queued event
or cancels and awaits the active handler; other events continue normally.

`application.update_queue` is an application-owned UpdateQueue producer interface:

| Operation | Behavior |
| --- | --- |
| `await put(event, user_id=None, peer_id=None)` | Wait for capacity, then return after insertion |
| `put_nowait(event, user_id=None, peer_id=None)` | Insert immediately or raise asyncio.QueueFull |
| `qsize()`, `empty()`, `full()`, `maxsize` | Inspect pending capacity; excludes the active event |

There is no public get, task_done, join or shutdown: Application owns consumption and
completion. Constructing or replacing a separate UpdateQueue is not a supported way to
feed an Application. The property is read-only. Reacquire it after restarting the lifecycle;
references to the closed queue from a previous run reject new events.

In a handler, put raises QueueFull if full, instead of waiting for the consumer that is
awaiting that handler. Recursive process_update is rejected with LifecycleError. Do not
wait for an event's result from its own handler, including indirectly through another task.

Admission before start and after shutdown raises LifecycleError. When stop begins, external
producers are rejected and waiting put calls wake to receive LifecycleError. Already owned
tasks and the handler active at the stop request can finish publishing. Later handlers
draining the queue cannot publish more events or create more tasks. Once owned tasks finish,
admission closes completely and all remaining accepted items drain. Queue errors do not
silently discard items or retry them; callers choose their overload policy.

All operations belong to the application's event loop; the queue is not thread-safe.
Capacity does not limit the number of producer coroutines or tasks the caller creates.

## VK delivery

Callback authenticates group/secret and handles confirmation before entering the queue.
It waits for process_update before returning `ok`. Its HTTP timeout covers waiting for
queue capacity, queued time and handler execution. A timeout cancels the corresponding
queued/active event and awaits cooperative cleanup. Handler failure still returns an HTTP
error, permitting retry. Repeated cancellation does not abandon active handler cleanup.

Long Poll keeps its acquisition, cursor advancement and reconnection behavior, and awaits
each submitted event. Handler failure is reported and skipped. Graceful stop interrupts
idle polling but lets a submitted event finish; runner cancellation cancels that event.
Stop and runner cleanup share one polling cancellation request per run and both await
its cleanup, including when these operations overlap.
The ASGI server owns its listener and lifetime: stopping Application does not stop the
server. Use one transport mode per Application instance.

Every Update is checked for the configured group and deduplicated in the consumer,
including an Update inserted directly through update_queue. Cached event IDs represent
successful dispatch only. Failed/cancelled processing is not intentionally cached; handlers
must cooperate with cancellation rather than suppress it and return success.

Internal Python objects, including plain dictionaries, are not parsed into VK Updates and
never enter VK deduplication. Direct Python admission is trusted application code and is
not a substitute for Callback authentication.

## Handlers and state

Numeric groups run in ascending order; only the first matching handler in each group runs.
Handler, MessageHandler, MessageEventHandler, CommandHandler and filters receive only
Update objects. TypeHandler accepts any chosen type, including Update:

```python
application.add_handler(TypeHandler(BackgroundResult, handle_result))
application.add_handler(TypeHandler(Update, inspect_vk_event), group=-1)
```

Matching uses isinstance by default; strict=True matches only the exact type. Callbacks
are always awaited. There is no block=False mode or concurrent handler dispatch.

Context.event holds the current Python object. VK state scopes come from Update.user_id
and Update.peer_id; overriding them during insertion is rejected. Internal events have
temporary empty user_data/peer_data unless insertion explicitly supplies those identifiers.
Context.bot_data is shared. An internal object is not inspected for attributes that happen
to be named user_id or peer_id. All state is process-local and remains caller-managed.

Raise ApplicationHandlerStop from a handler to stop remaining groups successfully. For a
VK event this still records successful deduplication. From an error callback it stops the
remaining error callbacks, but the original failure still propagates to process_update;
it does not acknowledge a failed VK event as successful. In a background coroutine it is
an ordinary task failure and cannot stop an unrelated or completed dispatch. In lifecycle
hooks it is an ordinary hook failure with the usual cleanup path.

Error callbacks retain `(Update | None, Context)`. An internal event supplies None as the
first argument and its object in Context.event. Context.error holds the exception. A failed
queued event is reported once and the consumer continues, without retry. Library logs
include exception types, not payloads or exception text.

## Managed tasks

```python
task = application.create_task(compute_and_enqueue(), update=source_update, name="compute")
worker = application.create_task(worker_loop(), name="worker", cancel_on_stop=True)
```

The method accepts a coroutine and returns an asyncio.Task with its result/exception.
Only RUNNING admits tasks. Calls before start, from post_init, during stop or after
shutdown raise LifecycleError and close the rejected coroutine without running it.
To start a worker at application startup, use the body of async with or explicit
initialize/start. No implicit services or worker processes are launched.

Ordinary errors are submitted to the same serial consumer and retained on the returned
Task. The optional update argument is the originating object; absent or internal origins
give error callbacks a None first argument. Internal task origins have no automatic
user/peer scopes. CancelledError is not reported as an error. The Application retains
tasks until completion and retrieves exceptions to avoid unobserved-task warnings.

Default tasks must be finite: stop awaits them with the consumer still alive. Workers
marked cancel_on_stop receive cancel and their finally blocks are awaited. A caller can
also cancel the returned Task itself. Tasks spawned separately with asyncio.create_task
are owned by their creator, not automatically adopted by Application.

Background coroutines must not directly mutate shared Context state. Publish a result and
update state in its TypeHandler. Do not await a managed task from a handler if it can need
queue capacity, dispatch or error callbacks: the consumer is awaiting that handler.
In particular, even a task failure needs the consumer to finish error reporting.

## Lifecycle and cleanup

1. initialize initializes Bot and calls post_init.
2. start starts the consumer and admits events/tasks.
3. stop rejects new intake/tasks, interrupts idle polling, and awaits active dispatch.
4. Workers marked cancel_on_stop are cancelled; finite tasks and their results finish.
5. The queue closes, remaining accepted events drain and the consumer exits.
6. shutdown calls post_stop once for a successfully started run, while Bot is available.
7. shutdown closes Bot and calls post_shutdown.

Direct stop does not call post_stop. Direct shutdown performs the complete sequence, as
do run_polling, async-context exit and Callback ASGI lifespan exit. Repeated completion
calls do not repeat hooks. After stop, complete shutdown and initialize before a new start.
Repeated start while running is a no-op. Context managers cannot be nested.

A handler or managed task calling stop requests stopping and returns without awaiting
itself. An outside owner can await stop or shutdown to observe completion. Calling shutdown,
initialize or start from a handler/managed task raises LifecycleError. Lifecycle hooks
must not recursively invoke lifecycle methods, directly or through child tasks.

Do not rely on post_stop to terminate a managed infinite task that stop is already waiting
for: use cancel_on_stop or arrange termination before stop. post_stop can close external
resources and send a final Bot message, but cannot enqueue results or launch managed tasks.

Initialization failure closes Bot without calling post_stop/post_shutdown. Cleanup runs in
owned tasks shielded from caller cancellation; cancellation is re-raised after cleanup.
An exception from post_stop does not prevent Bot shutdown or post_shutdown. The first
cleanup error is raised; subsequent cleanup errors are logged safely. Context exit preserves
an original body exception/cancellation when cleanup also fails. Repeated shutdown awaits
the same completion and may re-raise its original failure without repeating side effects.

Cancellation must be cooperative. Blocking code or a coroutine that suppresses cancellation
can prevent completion. Finite network/computation operations need their own timeouts;
there is no automatic deadline or forceful termination of arbitrary user code.

## Stability and limits

The documented APIs are public; underscore-prefixed queues, receipts and tasks are private
and have no compatibility guarantees. The library remains pre-1.0: public breaking changes
must be documented in CHANGELOG and migration notes; PTB source compatibility is not promised.

An in-memory insertion is not durable job acceptance. There is no persistence, distributed
deduplication, exactly-once guarantee, business retry policy, JobQueue or ConversationHandler.
Callback retry can repeat partial side effects; restarts lose queued work. Persist business
operations separately when required. No Telegram identifiers, events or permissions are
introduced into VK models.
