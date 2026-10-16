# Retry-with-Backoff, Tested Instantly via an Injectable `sleep`

## What it is

`OpenAIEmbeddingClient.embed_batch` (Step 24) retries on HTTP 429 with exponential backoff — a real `await asyncio.sleep(...)` between attempts in production. A naive test of that logic would actually wait through the backoff (seconds, growing exponentially per retry), making the test suite slow and the timing itself untestable. The fix is the same [Callable-default-parameter pattern](07_callable_dependency_injection.md) already used for DNS resolution: `sleep` is a constructor parameter defaulting to the real `asyncio.sleep`, so tests can swap in a no-op.

## Verified example (from `backend/agents/src/agentos_agents/retriever/embedding.py`)

```python
Sleep = Callable[[float], Awaitable[None]]

class OpenAIEmbeddingClient(EmbeddingClient):
    def __init__(self, ..., sleep: Sleep = asyncio.sleep) -> None:
        ...
        self.sleep = sleep

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        for attempt in range(self.max_retries + 1):
            response = await self.http_client.post(...)
            if response.status_code == 429:
                if attempt < self.max_retries:
                    await self.sleep(self.backoff_seconds * (2**attempt))
                    continue
                raise EmbeddingError(f"rate limited after {attempt + 1} attempts")
            ...
```

Test side:
```python
async def instant_sleep(_seconds: float) -> None:
    pass

async def test_embed_batch_retries_on_429_then_succeeds():
    route = respx.post(URL).mock(side_effect=[httpx.Response(429), httpx.Response(429), embeddings_response(...)])
    client = OpenAIEmbeddingClient(http_client, api_key="k", sleep=instant_sleep)
    result = await client.embed_batch(["only"])
    assert route.call_count == 3
```
Verified: `test_embedding.py`'s full 6-test suite (empty input short-circuits before any call, out-of-order response restoration, retry-then-succeed, retry-exhaustion, no-retry-on-500, the cost/trace hook firing once per attempt) runs in 0.05s — a real 429→429→200 sequence with real (mocked-away) exponential backoff, without the test actually waiting.

## Why an `EmbeddingClient` ABC but a Callable `sleep`, in the same class

Both DI patterns from [07_callable_dependency_injection.md](07_callable_dependency_injection.md)'s comparison table show up in this one file, for different reasons:
- **`EmbeddingClient(ABC)`** — a genuine multi-provider concern (a different embedding model or a self-hosted server is a real swap this project might make), matching `Consumer`'s ABC shape ([06_abstract_base_classes.md](06_abstract_base_classes.md)).
- **`sleep: Sleep = asyncio.sleep`** — one function, needed purely to make retry timing controllable in tests; no second "sleep provider" will ever exist in production.

Picking the lighter pattern where it fits, instead of wrapping `sleep` in its own ABC just for consistency with `EmbeddingClient`, is the same judgment call `url_validator.py`'s `resolver` parameter already made.

## Standard use case

Any retry-with-backoff loop, or anywhere else "real time passing" would otherwise make a test slow or flaky (rate limiters, polling loops, scheduled retries) — inject the wait function, not just the thing being waited on.
