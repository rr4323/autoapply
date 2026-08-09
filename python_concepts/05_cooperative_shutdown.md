# Cooperative Shutdown with `asyncio.Event`

## What it is

The Python counterpart to Go's `signal.NotifyContext`/`context.Done()` pattern ([go_concepts/07_context.md](../go_concepts/07_context.md)) — a way to tell a running loop "stop after your current iteration" without killing it mid-operation. Since `asyncio` is single-threaded and cooperative ([02_asyncio_basics.md](02_asyncio_basics.md)), a loop can only actually stop at an `await` point where it chooses to check.

## Verified example

```python
async def worker(stop_event: asyncio.Event):
    while not stop_event.is_set():
        print("tick")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=0.3)
        except asyncio.TimeoutError:
            pass  # no shutdown signal yet within this tick — loop again
    print("worker exiting cleanly")

async def main():
    stop_event = asyncio.Event()
    task = asyncio.create_task(worker(stop_event))

    await asyncio.sleep(1)
    stop_event.set()

    await task  # wait for the worker to actually finish its current iteration
```
```
tick
tick
tick
tick
worker exiting cleanly
```

## Reading the pieces

- **`asyncio.Event`** — a flag with two states, `set`/not-`set`, plus an async `.wait()` that blocks until it becomes set. This is the direct analog of a Go `context.Context`'s `Done()` channel — something a loop can wait on that signals cancellation.
- **`asyncio.wait_for(coro, timeout=...)`** — races a coroutine against a timeout, raising `asyncio.TimeoutError` if the timeout wins. Used here so the loop wakes up periodically to check the stop flag *and* do its real work (`print("tick")`), rather than either blocking on `stop_event.wait()` forever or busy-polling with no wait at all.
- **`asyncio.create_task(worker(...))`** — schedules a coroutine to run concurrently as a `Task`, without blocking the caller. `main()` can keep going (here, `await asyncio.sleep(1)`) while `worker` runs "in the background" on the same event loop.
- **`await task`** — blocks until that task actually finishes, which is how `main()` knows the worker really stopped (not just that the stop flag was set) before the program exits.

## Standard use case

The consumer base class's `run()` loop (`docs/BACKEND_BUILD_STEPS.md` Step 6) checks a `stop_event` the same way, wrapping its `xreadgroup` call's own `block=` timeout so a shutdown request doesn't have to wait for a message to actually arrive first. A real agent's entrypoint script wires OS signals (`SIGTERM`/`SIGINT`, same signals as [go_concepts/07_context.md](../go_concepts/07_context.md)'s Go example) to call `stop_event.set()`, using `asyncio`'s own signal-handling hooks — the mechanism differs from Go's `signal.NotifyContext`, but the shape of the problem it solves is identical.
