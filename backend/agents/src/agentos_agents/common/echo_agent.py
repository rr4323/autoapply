"""A minimal, runnable Consumer used to prove the message bus round-trips
correctly across languages (docs/BACKEND_BUILD_STEPS.md Steps 6-7).

Not a real business agent — it just records what it received. Runnable
directly: `python -m agentos_agents.common.echo_agent`, configured via env
vars so a Go integration test can launch it as a subprocess.
"""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Any

import redis.asyncio as redis

from agentos_agents.common.consumer import Consumer


class EchoConsumer(Consumer):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.received: list[tuple[str, dict[str, Any]]] = []

    async def handle(self, entry_id: str, fields: dict[str, Any]) -> None:
        self.received.append((entry_id, fields))
        print(f"ECHO_RECEIVED {entry_id} job_id={fields.get('job_id', '')}", flush=True)


async def _run(
    redis_addr: str,
    topic: str,
    group: str,
    consumer_name: str,
    max_messages: int,
    timeout_seconds: float,
) -> int:
    host, _, port_str = redis_addr.partition(":")
    client = redis.Redis(host=host, port=int(port_str or 6379), decode_responses=True)
    consumer = EchoConsumer(client, topic, group, consumer_name, block_ms=500)

    async def watch_and_stop() -> None:
        loop = asyncio.get_event_loop()
        deadline = loop.time() + timeout_seconds
        while len(consumer.received) < max_messages:
            if loop.time() > deadline:
                break
            await asyncio.sleep(0.1)
        consumer.stop()

    await asyncio.gather(consumer.run(), watch_and_stop())
    await client.aclose()

    if len(consumer.received) < max_messages:
        print(
            f"ECHO_TIMEOUT received={len(consumer.received)} expected={max_messages}",
            flush=True,
        )
        return 1

    print(f"ECHO_SUCCESS received={len(consumer.received)}", flush=True)
    return 0


def main() -> None:
    exit_code = asyncio.run(
        _run(
            redis_addr=os.environ.get("REDIS_ADDR", "localhost:6379"),
            topic=os.environ.get("BUS_TOPIC", "jd.discovered"),
            group=os.environ.get("BUS_GROUP", "echo-group"),
            consumer_name=os.environ.get("BUS_CONSUMER_NAME", "echo-consumer-1"),
            max_messages=int(os.environ.get("ECHO_MAX_MESSAGES", "1")),
            timeout_seconds=float(os.environ.get("ECHO_TIMEOUT_SECONDS", "10")),
        )
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
