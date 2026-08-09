# Redis Streams Consumer Groups — `redis.asyncio`

## What it is

[go_concepts/12_redis_streams_basics.md](../go_concepts/12_redis_streams_basics.md) covered `XADD`/`XRANGE` — the producer side. This is the consumer side: **consumer groups**, which is what gives Redis Streams the at-least-once delivery and per-message acknowledgment `TDD.md` §4.2 depends on (each agent type is its own consumer group, per §4 — multiple replicas of the same agent load-balance automatically within a group).

## Verified example

```python
import redis.asyncio as redis

r = redis.Redis(host="localhost", port=6379, decode_responses=True)

# Create the group if it doesn't exist yet — "create-if-missing"
try:
    await r.xgroup_create("demo.topic", "demo-group", id="0", mkstream=True)
except redis.ResponseError as e:
    if "BUSYGROUP" not in str(e):
        raise  # some other real error — don't swallow it

await r.xadd("demo.topic", {"job_id": "abc", "msg": "hello"})

# Read as consumer-1 — ">" means "only new, never-delivered entries"
resp = await r.xreadgroup(
    groupname="demo-group", consumername="consumer-1",
    streams={"demo.topic": ">"}, count=10, block=1000,
)
# [['demo.topic', [('1786293646692-0', {'job_id': 'abc', 'msg': 'hello'})]]]

# Check what's delivered-but-not-yet-acked
pending = await r.xpending("demo.topic", "demo-group")
# {'pending': 1, 'min': '...', 'max': '...', 'consumers': [{'name': 'consumer-1', 'pending': 1}]}

# Simulate consumer-1 crashing before it could ack: reclaim as consumer-2
claimed = await r.xautoclaim("demo.topic", "demo-group", "consumer-2", min_idle_time=0)

# Now ack it
entry_id = claimed[1][0][0]
await r.xack("demo.topic", "demo-group", entry_id)
```

## Reading the pieces

- **`xgroup_create(..., id="0", mkstream=True)`** — `id="0"` means the group starts reading from the very beginning of the stream (not just new entries from now on); `mkstream=True` creates the stream itself if it doesn't exist yet, so this call works whether or not anything has published to this topic before. **"Create-if-missing"** (`docs/BACKEND_BUILD_STEPS.md` Step 6's phrase) means calling this every time a consumer starts up, catching the `BUSYGROUP` error Redis returns if the group already exists, and treating that specific error as success, not a failure.
- **`xreadgroup(groupname, consumername, streams={topic: ">"}, block=1000)`** — reads as a named consumer within a group. `">"` = only entries never delivered to this group before. `block=1000` = wait up to 1000ms for a new entry before returning empty, rather than either busy-polling or blocking forever.
- **`xpending`** — entries that were delivered to some consumer in the group but never acked. This is the queue of "might have failed, might just be slow" work.
- **`xautoclaim(topic, group, new_consumer_name, min_idle_time=0)`** — reassigns pending entries idle longer than `min_idle_time` (in ms) to a different consumer name, so they get reprocessed instead of stuck forever behind a crashed consumer. This is the **"retry/claim on pending"** piece of Step 6.
- **`xack(topic, group, entry_id)`** — marks an entry as successfully processed; it drops out of the pending list and won't be redelivered.

## Standard use case

Every one of the 8 agents' `run()` loop is: `xreadgroup` (block for new work) → process → `xack`. A periodic (or startup-time) `xautoclaim` sweep is what makes the fleet resilient to a consumer crashing mid-message — the message doesn't just vanish, another replica in the same group eventually reclaims and reprocesses it. Combined with the idempotency ledger (`TDD.md` §4.2 — keyed on `job_id + event_type`, recorded in `application_events`), a message redelivered this way is safe to reprocess even if the crashed consumer had partially handled it.
