# `asyncio` Basics — `async`/`await`, and Why the Agent Fleet Needs It

## What it is

Python's cooperative concurrency model. Unlike Go's goroutines ([go_concepts/07_context.md](../go_concepts/07_context.md)'s concurrency, backed by the Go runtime scheduling across OS threads), `asyncio` runs everything on **one thread**, and functions only yield control at explicit `await` points. Nothing runs "in the background" unless it's awaiting something (I/O, a timer, another task) — there's no preemption.

## Verified example

```python
async def slow_task(name: str, delay: float) -> str:
    print(f"{name} starting")
    await asyncio.sleep(delay)
    print(f"{name} finished")
    return f"{name} done"

async def main():
    # Sequential — each await blocks until that call finishes
    await slow_task("A", 1)
    await slow_task("B", 1)
    # took ~2.0s

    # Concurrent — both run "at once" on the one thread
    results = await asyncio.gather(slow_task("C", 1), slow_task("D", 1))
    # took ~1.0s
```
```
sequential took 2.0s
concurrent took 1.0s
['C done', 'D done']
```

## Reading the pieces

- **`async def`** — declares a *coroutine function*. Calling it doesn't run the body — it returns a coroutine object that has to be `await`ed (or scheduled as a task) to actually execute.
- **`await`** — "run this, and yield control back to the event loop until it's done." This is the only place execution can switch to something else — there's no equivalent of Go's runtime deciding to preempt a goroutine mid-function.
- **`asyncio.gather(...)`** — runs multiple coroutines concurrently, returns when all are done. This is why `C`/`D` above finish in ~1s instead of 2s — while `C` is inside its `await asyncio.sleep(1)`, the event loop is free to start running `D`.
- **`asyncio.run(main())`** — the top-level entry point; starts the event loop, runs `main()` to completion, then shuts the loop down. Analogous to Go's `main()` itself being the outermost synchronous frame everything else runs under.

## Why the agent fleet is async, not threaded or synchronous

Each of the 8 Python agents (`TDD.md` §3.2) is fundamentally an I/O-bound loop: block waiting for a new message on the bus, then usually make an outbound call (LLM API, DB query, HTTP fetch) before producing its own message. `asyncio` lets one process handle this efficiently without needing a thread per concurrent operation — the consumer loop can be waiting on Redis while, if needed, other coroutines (e.g. a periodic health-check ping) run on the same thread without any locking concerns, since only one thing ever actually executes at a time.

## Standard use case

Every consumer loop in `backend/agents` — the shared base class (`docs/BACKEND_BUILD_STEPS.md` Step 6) and all 8 agents built on it — is `async def run(self)`, calling `await self.redis.xreadgroup(...)` to block (without blocking the whole process) until a message arrives.
