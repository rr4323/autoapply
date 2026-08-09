# `fakeredis` — Python's Protocol Fake for Redis

## What it is

The Python counterpart to [go_concepts/13_testing_with_fake_servers.md](../go_concepts/13_testing_with_fake_servers.md)'s `miniredis`: an in-memory implementation of the Redis protocol, so tests can use the **real `redis.asyncio.Redis` client class** against it — no separate server process, no Docker container, and (unlike an interface-level fake) no risk of the fake quietly diverging from how real Redis actually behaves.

## Verified example

```python
import fakeredis

r = fakeredis.FakeAsyncRedis(decode_responses=True)

await r.xgroup_create("demo.topic", "demo-group", id="0", mkstream=True)
await r.xadd("demo.topic", {"job_id": "abc"})

resp = await r.xreadgroup(
    groupname="demo-group", consumername="c1",
    streams={"demo.topic": ">"}, count=10, block=100,
)
entry_id = resp[0][1][0][0]
await r.xack("demo.topic", "demo-group", entry_id)

pending = await r.xpending("demo.topic", "demo-group")
# {'pending': 0, 'min': None, 'max': None, 'consumers': []}
```

Confirmed: `xgroup_create`, `xadd`, `xreadgroup`, `xack`, `xpending` all behave identically to the real server from [03_redis_streams_consumer_groups.md](03_redis_streams_consumer_groups.md)'s example — same call shapes, same response shapes.

## Why this, not `testcontainers-python`

Same reasoning as the Go side: `docs/IMPLEMENTATION_PLAN.md` §0 reserves `testcontainers` for **integration** tests specifically (a real Postgres/Redis in an actual container). Step 6's required tests — *"ack path, redelivery path, shutdown mid-loop"* — are **unit** tests: fast, no container startup, and `fakeredis.FakeAsyncRedis` gives real-protocol confidence at that speed, same tradeoff `miniredis` makes on the Go side.

## Standard use case

Every consumer-base-class test in `backend/agents` — construct a `FakeAsyncRedis`, `xadd` a message onto it directly (simulating "a producer already published this"), run the consumer against it, then assert on `xpending`/`xack` state exactly like the verified example above.
