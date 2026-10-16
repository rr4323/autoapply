# Streaming HTTP Responses with `httpx`, Mocked with `respx`

## What it is

`httpx.AsyncClient` is Python's async HTTP client — the natural fit here since the whole agent fleet is `asyncio`-based ([02_asyncio_basics.md](02_asyncio_basics.md)). `client.stream(...)` gives you the response incrementally, chunk by chunk, instead of buffering the whole body in memory first — necessary for enforcing a byte cap on untrusted responses (`TDD.md` §14's "scraped content is data, never instructions" extends to "scraped content shouldn't be allowed to be unboundedly large" either).

## Verified example (from `backend/agents/src/agentos_agents/scraper/fetcher.py`)

```python
async with client.stream("GET", url, timeout=timeout, follow_redirects=True) as response:
    response.raise_for_status()

    content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise FetchError(f"unexpected content-type {content_type!r}")

    chunks: list[bytes] = []
    total = 0
    async for chunk in response.aiter_bytes():
        total += len(chunk)
        if total > max_bytes:
            raise FetchError(f"response exceeded {max_bytes} byte cap")
        chunks.append(chunk)

    return b"".join(chunks).decode(response.encoding or "utf-8", errors="replace")
```
The size check happens **while reading**, not after — a response is rejected the moment it crosses `max_bytes`, so a malicious or broken server can't force this function to buffer gigabytes before the check ever runs.

## Testing it: `respx` mocks at the transport layer

```python
import respx

@respx.mock
async def test_fetch_rejects_oversized_response():
    respx.get(URL).mock(
        return_value=httpx.Response(200, headers={"content-type": "text/html"}, text="x" * 1000)
    )
    async with httpx.AsyncClient() as client:
        with pytest.raises(FetchError, match="byte cap"):
            await fetch_jd_html(URL, client, max_bytes=100)
```
Verified: this and 4 other cases (wrong content-type, HTTP error status, timeout, success) all pass with **zero real network calls**. `respx` intercepts at `httpx`'s transport layer — the same `client.stream(...)` code path under test runs unmodified; only the actual socket I/O is replaced. This is the `httpx`-specific version of the same idea as `fakeredis`/`miniredis` ([04_fakeredis_testing.md](04_fakeredis_testing.md), [go_concepts/13_testing_with_fake_servers.md](../go_concepts/13_testing_with_fake_servers.md)) — a protocol/transport-level fake, not a hand-rolled interface fake, so the real client code is what's actually being exercised.

**`side_effect=` vs. `return_value=`**: `respx.get(URL).mock(return_value=httpx.Response(...))` returns a normal response; `respx.get(URL).mock(side_effect=httpx.TimeoutException(...))` makes the mocked call raise instead — useful for testing error paths (like the timeout test above) without needing a server that's actually slow.

## Standard use case

Any outbound HTTP call in the agent fleet — this fetcher, and later the LLM provider calls the Scoring/Generator Agents make (`IMPLEMENTATION_PLAN.md` §0 names `respx` explicitly for mocking those too). Same pattern every time: real `httpx.AsyncClient` code, `respx.mock` intercepting the transport in tests.
