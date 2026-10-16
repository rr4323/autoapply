"""Publishes envelopes onto Redis Streams — Python counterpart to
backend/api/internal/bus/publisher.go. Same wire shape: one stream field
per Envelope field (not a single marshaled JSON blob), so either
language can read a message the other one wrote.
"""

from __future__ import annotations

import redis.asyncio as redis

from agentos_agents.common.envelope import Envelope


class Publisher:
    def __init__(self, redis_client: redis.Redis) -> None:
        self.redis = redis_client

    async def publish(self, topic: str, envelope: Envelope) -> str:
        entry_id = await self.redis.xadd(topic, envelope.model_dump())
        return entry_id
