# Redis Streams — `XADD`/`XRANGE` via go-redis

## What it is

A Redis Stream is an append-only log — the data structure our message bus (`TDD.md` §4) is built on. `XADD` appends an entry to a stream (creating the stream if it doesn't exist); `XRANGE` reads entries back out.

## Verified example

```go
client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
ctx := context.Background()

id, err := client.XAdd(ctx, &redis.XAddArgs{
	Stream: "jd.discovered",
	Values: map[string]interface{}{
		"job_id":     "abc-123",
		"event_type": "jd.discovered",
	},
}).Result()
```
```
entry id: 1786292835555-0
```
```go
entries, err := client.XRange(ctx, "jd.discovered", "-", "+").Result()
for _, e := range entries {
	fmt.Printf("entry %s: %v\n", e.ID, e.Values)
}
```
```
entry 1786292835555-0: map[event_type:jd.discovered job_id:abc-123]
```

## Reading the pieces

- **`Stream: "jd.discovered"`** — the stream's key/name. This is a topic in `TDD.md` §2's diagram (T1–T10) — one Redis key per event type.
- **`Values: map[string]interface{}{...}`** — the entry's field-value pairs. Unlike a plain Redis key (one value), a stream entry is itself a small set of named fields — which is why the message envelope's fields (`job_id`, `trace_id`, ...) map naturally onto it directly, one struct field per stream field, no extra JSON-encoding layer needed.
- **`ID` field on `XAddArgs`** — left unset here, which defaults to `"*"`, telling Redis to auto-generate an ID. The returned ID (`1786292835555-0`) is `<millisecond-timestamp>-<sequence-within-that-millisecond>` — IDs are always increasing, which is what gives a stream its ordering guarantee.
- **`XRange(ctx, stream, "-", "+")`** — `"-"` and `"+"` mean "from the very first entry to the very last" — the full range. A real consumer uses `XReadGroup` instead (consumer-group semantics, at-least-once delivery, per §4), which Step 6 builds; `XRange` here is what a test (or a debugging session) uses to just look at what's in a stream.

## Standard use case

Every agent-to-agent handoff in `TDD.md` §2's architecture is one `XADD` (producer) and one `XReadGroup` consumer loop (subscriber) against a stream named after the topic. `docs/BACKEND_BUILD_STEPS.md` Step 5's "done when" — *"Publishing to `jd.discovered` is visible via `XRANGE`"* — is exactly this pattern: after your `Publisher.Publish(...)` call, a plain `redis-cli XRANGE jd.discovered - +` (or the Go client's `XRange`) should show the entry.
