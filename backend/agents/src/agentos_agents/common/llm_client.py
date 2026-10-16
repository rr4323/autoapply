"""LLM client behind an interface — same shape as
retriever/embedding.py's EmbeddingClient (ABC for the swappable provider,
retry-on-429 with an injectable sleep for testability). Not re-documented
here; see python_concepts/06_abstract_base_classes.md and
python_concepts/12_retry_with_injectable_sleep.md.

Lives in common/, not scoring/ (where it started, Step 28) — moved here
once the Generator Agent's guardrail scan (Step 36) needed the exact same
client, the same "second consumer triggers extraction" pattern applied
throughout this project (e.g. common/envelope.utc_timestamp, Step 26).
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable

import httpx

Sleep = Callable[[float], Awaitable[None]]


class LLMError(Exception):
    """Raised when an LLM call fails outright, or is still rate limited
    after every retry is exhausted."""


class LLMClient(ABC):
    @abstractmethod
    async def complete(self, system: str, user: str) -> str:
        """Return the model's raw text response to one user turn."""


class AnthropicLLMClient(LLMClient):
    def __init__(
        self,
        http_client: httpx.AsyncClient,
        api_key: str,
        model: str = "claude-haiku-4-5-20251001",  # cheap tier, TDD.md §11.1's model-tiering
        base_url: str = "https://api.anthropic.com/v1",
        max_tokens: int = 512,
        max_retries: int = 3,
        backoff_seconds: float = 1.0,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self.http_client = http_client
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.max_tokens = max_tokens
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self.sleep = sleep

    async def complete(self, system: str, user: str) -> str:
        for attempt in range(self.max_retries + 1):
            response = await self.http_client.post(
                f"{self.base_url}/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": self.model,
                    "max_tokens": self.max_tokens,
                    "system": system,
                    "messages": [{"role": "user", "content": user}],
                },
            )

            if response.status_code == 429:
                if attempt < self.max_retries:
                    await self.sleep(self.backoff_seconds * (2**attempt))
                    continue
                raise LLMError(f"rate limited after {attempt + 1} attempts")

            if response.status_code != 200:
                raise LLMError(f"LLM request failed: {response.status_code} {response.text}")

            data = response.json()
            try:
                return data["content"][0]["text"]
            except (KeyError, IndexError, TypeError) as e:
                raise LLMError(f"unexpected LLM response shape: {data!r}") from e

        raise AssertionError("unreachable — loop always returns or raises")
