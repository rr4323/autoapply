import asyncio
import time
from typing import Any

import fakeredis
import pytest

from agentos_agents.common.consumer import Consumer
from agentos_agents.common.echo_agent import EchoConsumer


@pytest.fixture
def redis_client():
    return fakeredis.FakeAsyncRedis(decode_responses=True)


async def run_briefly(consumer: Consumer, seconds: float = 0.3) -> None:
    task = asyncio.create_task(consumer.run())
    await asyncio.sleep(seconds)
    consumer.stop()
    await asyncio.wait_for(task, timeout=2.0)


async def test_ack_path(redis_client):
    await redis_client.xadd("test.topic", {"job_id": "1"})

    consumer = EchoConsumer(redis_client, "test.topic", "test-group", "c1", block_ms=100)
    await run_briefly(consumer)

    assert len(consumer.received) == 1
    pending = await redis_client.xpending("test.topic", "test-group")
    assert pending["pending"] == 0


async def test_redelivery_path(redis_client):
    entry_id = await redis_client.xadd("test.topic", {"job_id": "2"})

    # Simulate a consumer that read the message and then crashed before acking.
    await redis_client.xgroup_create("test.topic", "test-group", id="0", mkstream=True)
    await redis_client.xreadgroup(
        groupname="test-group",
        consumername="crashed-consumer",
        streams={"test.topic": ">"},
        count=10,
        block=100,
    )
    pending_before = await redis_client.xpending("test.topic", "test-group")
    assert pending_before["pending"] == 1

    consumer = EchoConsumer(
        redis_client,
        "test.topic",
        "test-group",
        "c1",
        block_ms=100,
        reclaim_idle_ms=0,  # reclaim immediately, regardless of real idle time
    )
    await run_briefly(consumer)

    assert any(eid == entry_id for eid, _ in consumer.received)
    pending_after = await redis_client.xpending("test.topic", "test-group")
    assert pending_after["pending"] == 0


async def test_shutdown_mid_loop(redis_client):
    consumer = EchoConsumer(redis_client, "empty.topic", "test-group", "c1", block_ms=300)

    start = time.monotonic()
    task = asyncio.create_task(consumer.run())
    await asyncio.sleep(0.05)  # let it enter the blocking xreadgroup call
    consumer.stop()
    await asyncio.wait_for(task, timeout=2.0)
    elapsed = time.monotonic() - start

    assert task.done()
    assert elapsed < 1.0  # bounded by block_ms, not stuck forever


async def test_idempotency_hook_skips_handle(redis_client):
    await redis_client.xadd("test.topic", {"job_id": "3"})

    class AlwaysDuplicateConsumer(EchoConsumer):
        async def is_duplicate(self, entry_id: str, fields: dict[str, Any]) -> bool:
            return True

    consumer = AlwaysDuplicateConsumer(redis_client, "test.topic", "test-group", "c1", block_ms=100)
    await run_briefly(consumer)

    assert consumer.received == []  # handle() never called for a duplicate
    pending = await redis_client.xpending("test.topic", "test-group")
    assert pending["pending"] == 0  # but it was still acked
