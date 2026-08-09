"""Shared consumer-group message loop for the Python agent fleet.

See docs/TDD.md §3.2/§4 — each agent is its own consumer-group member;
this base class owns the loop mechanics (group creation, reading,
stale-message reclaim, acking, graceful shutdown). Subclasses only
implement handle().
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any

import redis.asyncio as redis

logger = logging.getLogger(__name__)


class Consumer(ABC):
    def __init__(
        self,
        redis_client: redis.Redis,
        topic: str,
        group: str,
        consumer_name: str,
        block_ms: int = 500,
        reclaim_idle_ms: int = 30_000,
    ) -> None:
        self.redis = redis_client
        self.topic = topic
        self.group = group
        self.consumer_name = consumer_name
        self.block_ms = block_ms
        self.reclaim_idle_ms = reclaim_idle_ms
        self._stop_event = asyncio.Event()

    @abstractmethod
    async def handle(self, entry_id: str, fields: dict[str, Any]) -> None:
        """Process one message. Subclasses implement business logic here."""

    def is_duplicate(self, entry_id: str, fields: dict[str, Any]) -> bool:
        """Idempotency hook — stubbed.

        TDD.md §4.2: a real check against application_events (keyed on
        job_id + event_type) lands in a later build step. Until then this
        always returns False — every delivered message is processed.
        """
        return False

    async def _ensure_group(self) -> None:
        try:
            await self.redis.xgroup_create(self.topic, self.group, id="0", mkstream=True)
        except redis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise

    async def _reclaim_stale(self) -> None:
        _cursor, claimed, _deleted = await self.redis.xautoclaim(
            self.topic,
            self.group,
            self.consumer_name,
            min_idle_time=self.reclaim_idle_ms,
        )
        for entry_id, fields in claimed:
            await self._process(entry_id, fields)

    async def _process(self, entry_id: str, fields: dict[str, Any]) -> None:
        if not self.is_duplicate(entry_id, fields):
            await self.handle(entry_id, fields)
        await self.redis.xack(self.topic, self.group, entry_id)

    async def run(self) -> None:
        await self._ensure_group()

        while not self._stop_event.is_set():
            await self._reclaim_stale()

            response = await self.redis.xreadgroup(
                groupname=self.group,
                consumername=self.consumer_name,
                streams={self.topic: ">"},
                count=10,
                block=self.block_ms,
            )
            for _stream, entries in response or []:
                for entry_id, fields in entries:
                    await self._process(entry_id, fields)

        logger.info("consumer stopped", extra={"topic": self.topic, "group": self.group})

    def stop(self) -> None:
        self._stop_event.set()
