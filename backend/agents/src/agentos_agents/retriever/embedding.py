"""Embedding client behind an interface (docs/BACKEND_BUILD_STEPS.md Step 24).

`EmbeddingClient` is an ABC, not a Callable default parameter
(python_concepts/07_callable_dependency_injection.md's distinction) — a
real provider swap (a different model, a self-hosted embedding server) is
a genuine multi-call-site concern here, not just a test-time fake for one
function. `on_call` is a Callable, though: it's a single-function seam
left for Phase K's Langfuse cost/trace tracking (TDD.md §11.1), not
something this step wires up.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable

import httpx

Sleep = Callable[[float], Awaitable[None]]
OnEmbeddingCall = Callable[[str, int, int], None]  # model, input_count, attempt_number


class EmbeddingError(Exception):
    """Raised when an embedding call fails outright, or is still rate
    limited after every retry is exhausted."""


class EmbeddingClient(ABC):
    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text, in the same order."""


class OpenAIEmbeddingClient(EmbeddingClient):
    def __init__(
        self,
        http_client: httpx.AsyncClient,
        api_key: str,
        model: str = "text-embedding-3-small",  # matches migration 0007's vector(1536)
        base_url: str = "https://api.openai.com/v1",
        max_retries: int = 3,
        backoff_seconds: float = 1.0,
        on_call: OnEmbeddingCall | None = None,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self.http_client = http_client
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self.on_call = on_call
        self.sleep = sleep

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        for attempt in range(self.max_retries + 1):
            response = await self.http_client.post(
                f"{self.base_url}/embeddings",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": self.model, "input": texts},
            )
            if self.on_call:
                self.on_call(self.model, len(texts), attempt + 1)

            if response.status_code == 429:
                if attempt < self.max_retries:
                    await self.sleep(self.backoff_seconds * (2**attempt))
                    continue
                raise EmbeddingError(f"rate limited after {attempt + 1} attempts")

            if response.status_code != 200:
                raise EmbeddingError(
                    f"embedding request failed: {response.status_code} {response.text}"
                )

            # OpenAI's response items aren't guaranteed to arrive in
            # input order — each carries its own `index` back specifically
            # so callers can restore it.
            data = response.json()["data"]
            ordered = sorted(data, key=lambda d: d["index"])
            return [d["embedding"] for d in ordered]

        raise AssertionError("unreachable — loop always returns or raises")
