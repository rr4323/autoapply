# A Go-Side Redis Streams Consumer — Mirroring Python's, in Go Idiom

## What it is

Every consumer so far ([12_redis_streams_basics.md](12_redis_streams_basics.md) onward) has been Python — Go only ever published. Step 32 (Policy Engine bus wiring) is the first time Go itself needs to consume: `application.scored` in, `policy.decision` out. `internal/bus/consumer.go`'s `Consumer` is structurally the same loop as `agentos_agents.common.consumer.Consumer` (group create → reclaim stale → `XReadGroup` → process → ack), translated into Go's idioms rather than copied line-for-line.

## Verified example (from `backend/api/internal/bus/consumer.go`)

```go
type Handler func(ctx context.Context, entryID string, env Envelope) error

func (c *Consumer) Run(ctx context.Context) error {
	if err := c.ensureGroup(ctx); err != nil {
		return fmt.Errorf("bus: failed to ensure consumer group: %w", err)
	}
	for {
		if ctx.Err() != nil {
			return nil
		}
		if err := c.reclaimStale(ctx); err != nil && ctx.Err() == nil {
			slog.Error("bus: reclaim stale messages failed", "topic", c.Topic, "error", err)
		}
		streams, err := c.Redis.XReadGroup(ctx, &redis.XReadGroupArgs{
			Group: c.Group, Consumer: c.ConsumerName,
			Streams: []string{c.Topic, ">"}, Count: 10, Block: c.BlockDuration,
		}).Result()
		if err != nil {
			if ctx.Err() != nil {
				return nil
			}
			if errors.Is(err, redis.Nil) {
				continue // block timeout, no new messages
			}
			slog.Error("bus: xreadgroup failed", "topic", c.Topic, "error", err)
			continue
		}
		for _, stream := range streams {
			for _, msg := range stream.Messages {
				c.process(ctx, msg)
			}
		}
	}
}
```

## Three places this genuinely differs from the Python version, on purpose

**1. `context.Context` cancellation, not `asyncio.Event`.** Python's `Consumer.stop()` sets an `asyncio.Event`, checked at the top of the loop. Go already has the idiomatic tool for this ([07_context.md](07_context.md)) — `c.Redis.XReadGroup(ctx, ...)` itself respects `ctx`'s cancellation mid-call (go-redis cancels the underlying network request), so `Run` exits promptly even while blocked inside a call, not just between iterations. Verified in `TestConsumer_ShutdownMidLoop`: cancellation during a 300ms blocking read still exits in well under a second.

**2. A failed handler leaves the message unacked, deliberately, via a real error return.** Python's `_process` always acks after calling `handle()` — if `handle()` raises, the exception propagates uncaught and the whole `run()` loop dies without ever reaching the ack line, which is really just an accident of not having a try/except there, not a designed behavior. Go's `Handler` returning `error` makes the equivalent choice explicit and intentional:
```go
if err := c.Handle(ctx, msg.ID, env); err != nil {
	slog.Error("bus: handler failed, message left unacked for redelivery", "entry_id", msg.ID, "error", err)
	return // no ack — XAUTOCLAIM will redeliver it later
}
c.ack(ctx, msg.ID)
```
`TestConsumer_HandlerErrorLeavesMessageUnacked` verifies this directly: `XPending` still shows the message after a handler returns an error.

**3. `IsDuplicate` is a field (a function value), not a method to override.** Python's idiom is subclassing `Consumer` and overriding `is_duplicate`/`handle` ([06_abstract_base_classes.md](06_abstract_base_classes.md)'s ABC pattern). Go has no inheritance; `Consumer.Handle Handler` and `Consumer.IsDuplicate IsDuplicate` are struct fields holding function values — composition instead of subclassing, the same shape as [08_testable_interfaces.md](08_testable_interfaces.md)'s `Pinger`, just at the level of a single function rather than a whole interface.

## Standard use case

Any Go service that needs to consume its own Redis Stream — every future Go-side consumer (the Verifier Agent's pre-submit callback wiring, Phase G) reaches for this same `Consumer` type rather than reimplementing the loop.
