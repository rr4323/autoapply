# Abstract Base Classes — Python's Explicit Contracts

## What it is

Python is duck-typed by default — no interfaces, no compile-time checks at all. `abc.ABC` + `@abstractmethod` is Python's **opt-in** way to say "any subclass of this *must* implement these methods, enforced at instantiation time." This is the closest Python equivalent to what Go's interfaces give you for free — but the mechanism is the opposite direction: Go checks structurally and implicitly ([go_concepts/04_interfaces.md](../go_concepts/04_interfaces.md) — no `implements` keyword, satisfied automatically); Python requires explicit inheritance from `ABC`, and only then enforces the missing-method contract.

## Verified example

```python
from abc import ABC, abstractmethod

class Agent(ABC):
    @abstractmethod
    async def handle(self, message: str) -> None:
        """Subclasses must implement this."""

    async def run_once(self, message: str) -> None:
        print(f"received: {message}")
        await self.handle(message)
        print("acked")

class EchoAgent(Agent):
    async def handle(self, message: str) -> None:
        print(f"echo: {message}")
```
```
received: hello
echo: hello
acked
cannot instantiate abstract class: Can't instantiate abstract class Agent with abstract method handle
```
`EchoAgent` works — it implements `handle`. Trying to instantiate `Agent()` directly fails immediately with `TypeError`, before any code inside it even runs, because `handle` was declared `@abstractmethod` and never overridden.

## The design this enables: shared loop, swappable logic

`Agent.run_once` (the *concrete* method) contains the reusable plumbing — logging, the ack — and calls `self.handle(...)`, which is deferred to whatever subclass gets instantiated. This is exactly the shape the consumer base class needs: **one shared `run()` loop implementing `xreadgroup`/idempotency-check/`xack`, with `handle()` left abstract for each of the 8 agents to fill in with their actual business logic.**

## Standard use case

`docs/BACKEND_BUILD_STEPS.md` Step 6's consumer base class: an abstract `Consumer` class owns the whole message-loop mechanics (create-if-missing, read, dedupe check, ack, reclaim-on-idle, graceful shutdown), and each of the 8 real agents (Scraper, Retriever, Scoring, ...) is a small subclass that only implements `async def handle(self, entry_id, fields)` with its own logic — never touching the loop/ack/retry code at all.
